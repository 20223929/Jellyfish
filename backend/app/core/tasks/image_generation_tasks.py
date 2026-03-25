"""图片生成任务（Task）：对接 OpenAI Images API 与火山引擎（方舟） ImageGenerations。

设计目标：
- 作为 `BaseTask` 实现接入 `TaskManager` 的 async_polling 流程；
- 提供最小统一输入：prompt / model / size / n / response_format；
- 输出统一的图片列表（URL 或 base64），供上层自行落库为 FileItem。
- 供应商无关逻辑在 `AbstractImageGenerationTask`；OpenAI / 火山在子类中实现
  `_create_task` 与 `_poll_and_get_result`（当前均为单次 HTTP 同步响应，无真实轮询）。
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.task_manager.types import BaseTask
from app.core.tasks.video_generation_tasks import ProviderConfig, ProviderKey

# 说明：多数部署/本地默认只展示 uvicorn.error 的 WARNING+。
# 为了确保“HTTP 请求详情”在当前环境可见，这里使用 uvicorn.error 并用 warning 级别输出。
logger = logging.getLogger("uvicorn.error")


ResponseFormat = Literal["url", "b64_json"]


class InputImageRef(BaseModel):
    """参考图片引用：统一映射到 OpenAI images[*] 与火山 image[]。"""

    model_config = ConfigDict(extra="forbid")

    file_id: Optional[str] = Field(
        None,
        description="文件 ID（用于 OpenAI File API；火山可忽略）",
    )
    image_url: Optional[str] = Field(
        None,
        description="完整 URL 或 base64 data URL；火山 image[] 建议使用该字段",
    )

    @model_validator(mode="after")
    def _require_one(self) -> "InputImageRef":
        if not self.file_id and not self.image_url:
            raise ValueError("InputImageRef 需提供 file_id 或 image_url 至少其一")
        return self


class ImageGenerationInput(BaseModel):
    """图片生成输入：文本 prompt 为必填，其余参数透传给供应商。"""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., description="文本提示词")
    images: list[InputImageRef] = Field(
        default_factory=list,
        description="参考图片列表：存在时 OpenAI 走 /images/edits，火山映射为 image[]",
    )
    model: Optional[str] = Field(None, description="模型名称（如 gpt-image-1.5 / doubao-seedream-*）")
    size: Optional[str] = Field(
        None,
        description="分辨率，如 1024x1024 / 1024x1536 等；不同供应商可选项不同",
    )
    n: int = Field(
        1,
        ge=1,
        le=10,
        description="生成图片数量；部分模型仅支持 n=1（调用方需结合文档约束）",
    )
    seed: Optional[int] = Field(
        None,
        description="随机种子；火山 ImageGenerations 支持该参数，OpenAI 目前忽略",
    )
    response_format: ResponseFormat = Field(
        "url",
        description="返回格式：url 或 b64_json（OpenAI 语义）；火山引擎可忽略或仅支持 url",
    )

    @model_validator(mode="after")
    def _strip_and_validate_prompt(self) -> "ImageGenerationInput":
        self.prompt = self.prompt.strip()
        if not self.prompt:
            raise ValueError("prompt 不能为空")
        return self


class ImageItem(BaseModel):
    """单张图片结果。"""

    url: Optional[str] = Field(None, description="图片 URL")
    b64_json: Optional[str] = Field(None, description="base64 编码内容（不含 data URI 前缀）")

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _require_one_field(self) -> "ImageItem":
        if not self.url and not self.b64_json:
            raise ValueError("Either url or b64_json must be set")
        return self


class ImageGenerationResult(BaseModel):
    """图片生成统一结果。"""

    model_config = ConfigDict(extra="ignore")

    images: list[ImageItem] = Field(..., description="图片列表")
    provider: ProviderKey = Field(..., description="供应商标识：openai | volcengine")
    provider_task_id: Optional[str] = Field(
        None,
        description="供应商内部任务 ID（若存在），用于调试/追踪",
    )
    status: Optional[str] = Field(
        None,
        description="供应商任务状态（同步接口通常为 succeeded/created 等）",
    )

    @model_validator(mode="after")
    def _require_images(self) -> "ImageGenerationResult":
        if not self.images:
            raise ValueError("images 不能为空")
        return self


def _redact_headers(h: dict[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for k, v in (h or {}).items():
        lk = k.lower()
        if lk in {"authorization", "x-api-key", "api-key"}:
            redacted[k] = "***redacted***"
        else:
            redacted[k] = v
    return redacted


def _safe_body_for_log_openai(body: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(body or {})
    if "prompt" in out and isinstance(out["prompt"], str):
        p = out["prompt"].strip()
        out["prompt"] = (p[:300] + "...(truncated)") if len(p) > 300 else p
    imgs = out.get("images")
    if isinstance(imgs, list):
        brief: list[dict[str, Any]] = []
        for it in imgs[:5]:
            if not isinstance(it, dict):
                continue
            image_url = it.get("image_url")
            file_id = it.get("file_id")
            brief.append(
                {
                    "has_image_url": bool(image_url),
                    "image_url_prefix": (str(image_url)[:80] + "...")
                    if isinstance(image_url, str) and len(image_url) > 80
                    else image_url,
                    "has_file_id": bool(file_id),
                }
            )
        out["images"] = {
            "count": len(imgs),
            "sample": brief,
        }
    return out


class AbstractImageGenerationTask(BaseTask, ABC):
    """图片生成抽象基类：初始化、状态、错误处理；子类实现 `_create_task` + `_poll_and_get_result`。

    当前 OpenAI / 火山均为单次 HTTP 同步返回：`_create_task` 完成请求并写入
    `self._http_json`；`_poll_and_get_result` 仅解析，无 sleep 轮询。
    """

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        input_: ImageGenerationInput,
        timeout_s: float = 60.0,
    ) -> None:
        self._cfg = provider_config
        self._input = input_
        self._timeout_s = timeout_s
        self._provider_task_id: str | None = None
        self._http_json: dict[str, Any] | None = None
        self._result: ImageGenerationResult | None = None
        self._error: str = ""

    @abstractmethod
    async def _create_task(self) -> None:
        """发起供应商请求；成功后将 JSON 放入 `self._http_json`（同步接口）。"""

    @abstractmethod
    async def _poll_and_get_result(self) -> ImageGenerationResult:
        """由 `self._http_json` 解析为 `ImageGenerationResult`（当前无轮询循环）。"""

    async def run(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any] | None:  # type: ignore[override]
        try:
            await self._create_task()
            self._result = await self._poll_and_get_result()
        except Exception as exc:  # noqa: BLE001
            self._error = str(exc)
            self._result = None
        return None

    async def status(self) -> dict[str, Any]:  # type: ignore[override]
        return {
            "task": "image_generation",
            "provider": self._cfg.provider,
            "provider_task_id": self._provider_task_id,
            "done": await self.is_done(),
            "has_result": self._result is not None,
            "error": self._error,
            "status": self._result.status if self._result else None,
        }

    async def is_done(self) -> bool:  # type: ignore[override]
        return self._result is not None or bool(self._error)

    async def get_result(self) -> ImageGenerationResult | None:  # type: ignore[override]
        return self._result


class OpenAIImageGenerationTask(AbstractImageGenerationTask):
    """OpenAI Images API：无参考图 POST /images/generations；有参考图 POST /images/edits。"""

    async def _create_task(self) -> None:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for image generation tasks") from e

        base_url = (self._cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            if self._input.images:
                body: dict[str, Any] = {
                    "prompt": self._input.prompt,
                    "n": self._input.n,
                }
                if self._input.model:
                    body["model"] = self._input.model
                if self._input.size:
                    body["size"] = self._input.size

                body["images"] = [
                    {
                        **({"file_id": ref.file_id} if ref.file_id else {}),
                        **({"image_url": ref.image_url} if ref.image_url else {}),
                    }
                    for ref in self._input.images
                ]

                url = f"{base_url}/images/edits"
                t0 = time.perf_counter()
                logger.warning(
                    "image_generation_http_request provider=%s method=POST url=%s headers=%s body=%s",
                    "openai",
                    url,
                    _redact_headers(headers),
                    json.dumps(_safe_body_for_log_openai(body), ensure_ascii=False),
                )
                r = await client.post(url, headers=headers, json=body)
            else:
                body = {
                    "prompt": self._input.prompt,
                    "n": self._input.n,
                    "response_format": self._input.response_format,
                }
                if self._input.model:
                    body["model"] = self._input.model
                if self._input.size:
                    body["size"] = self._input.size

                url = f"{base_url}/images/generations"
                t0 = time.perf_counter()
                logger.warning(
                    "image_generation_http_request provider=%s method=POST url=%s headers=%s body=%s",
                    "openai",
                    url,
                    _redact_headers(headers),
                    json.dumps(_safe_body_for_log_openai(body), ensure_ascii=False),
                )
                r = await client.post(url, headers=headers, json=body)

            dt_ms = int((time.perf_counter() - t0) * 1000)
            resp_text = ""
            try:
                resp_text = r.text or ""
            except Exception:  # noqa: BLE001
                resp_text = ""
            logger.warning(
                "image_generation_http_response provider=%s status=%s elapsed_ms=%s headers=%s body=%s",
                "openai",
                r.status_code,
                dt_ms,
                dict(r.headers),
                (resp_text[:2000] + "...(truncated)") if len(resp_text) > 2000 else resp_text,
            )

            r.raise_for_status()
            self._http_json = r.json()

    async def _poll_and_get_result(self) -> ImageGenerationResult:
        data = self._http_json or {}
        raw_items = data.get("data") or []
        images: list[ImageItem] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            b64 = item.get("b64_json")
            if not url and not b64:
                continue
            images.append(ImageItem(url=url, b64_json=b64))

        if not images:
            raise RuntimeError(f"OpenAI images response has no usable data: {data!r}")

        return ImageGenerationResult(
            images=images,
            provider="openai",
            provider_task_id=None,
            status=str(data.get("status") or "succeeded"),
        )


class VolcengineImageGenerationTask(AbstractImageGenerationTask):
    """火山引擎方舟 ImageGenerations：POST /images/generations（同步返回）。"""

    async def _create_task(self) -> None:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for image generation tasks") from e

        base_url = (self._cfg.base_url or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
        headers = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {
            "prompt": self._input.prompt,
            "n": self._input.n,
        }
        if self._input.model:
            body["model"] = self._input.model
        if self._input.size:
            body["size"] = self._input.size
        if self._input.seed is not None:
            body["seed"] = int(self._input.seed)
        if self._input.images:
            body["image"] = [
                ref.image_url or ref.file_id
                for ref in self._input.images
                if (ref.image_url or ref.file_id)
            ]
        if self._input.response_format:
            body["response_format"] = self._input.response_format

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            url = f"{base_url}/images/generations"
            t0 = time.perf_counter()
            logger.warning(
                "image_generation_http_request provider=%s method=POST url=%s headers=%s body=%s",
                "volcengine",
                url,
                {"Authorization": "***redacted***", "Content-Type": headers.get("Content-Type", "application/json")},
                json.dumps(
                    {
                        **(
                            {
                                "prompt": (
                                    (body.get("prompt", "")[:300] + "...(truncated)")
                                    if isinstance(body.get("prompt"), str) and len(body.get("prompt", "")) > 300
                                    else body.get("prompt")
                                )
                            }
                        ),
                        **{k: v for k, v in body.items() if k != "prompt" and k != "image"},
                        "image": {"count": len(body.get("image") or [])}
                        if isinstance(body.get("image"), list)
                        else body.get("image"),
                    },
                    ensure_ascii=False,
                ),
            )
            r = await client.post(url, headers=headers, json=body)
            dt_ms = int((time.perf_counter() - t0) * 1000)
            resp_text = ""
            try:
                resp_text = r.text or ""
            except Exception:  # noqa: BLE001
                resp_text = ""
            logger.warning(
                "image_generation_http_response provider=%s status=%s elapsed_ms=%s headers=%s body=%s",
                "volcengine",
                r.status_code,
                dt_ms,
                dict(r.headers),
                (resp_text[:2000] + "...(truncated)") if len(resp_text) > 2000 else resp_text,
            )
            r.raise_for_status()
            self._http_json = r.json()

    async def _poll_and_get_result(self) -> ImageGenerationResult:
        data = self._http_json or {}
        raw_items = data.get("data") or []
        images: list[ImageItem] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("image_url")
            b64 = item.get("b64_json")
            if not url and not b64:
                continue
            images.append(ImageItem(url=url, b64_json=b64))

        if not images:
            raise RuntimeError(f"Volcengine ImageGenerations response has no usable data: {data!r}")

        self._provider_task_id = str(data.get("id") or data.get("task_id") or "")

        return ImageGenerationResult(
            images=images,
            provider="volcengine",
            provider_task_id=self._provider_task_id or None,
            status=str(data.get("status") or "succeeded"),
        )


class ImageGenerationTask(BaseTask):
    """按 provider 分派到 OpenAI / 火山实现；对外构造函数与原先一致。"""

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        input_: ImageGenerationInput,
        timeout_s: float = 60.0,
    ) -> None:
        if provider_config.provider == "openai":
            self._impl: AbstractImageGenerationTask = OpenAIImageGenerationTask(
                provider_config=provider_config,
                input_=input_,
                timeout_s=timeout_s,
            )
        elif provider_config.provider == "volcengine":
            self._impl = VolcengineImageGenerationTask(
                provider_config=provider_config,
                input_=input_,
                timeout_s=timeout_s,
            )
        else:
            raise ValueError(f"Unsupported provider: {provider_config.provider!r}")

    async def run(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any] | None:  # type: ignore[override]
        return await self._impl.run(*args, **kwargs)

    async def status(self) -> dict[str, Any]:  # type: ignore[override]
        return await self._impl.status()

    async def is_done(self) -> bool:  # type: ignore[override]
        return await self._impl.is_done()

    async def get_result(self) -> ImageGenerationResult | None:  # type: ignore[override]
        return await self._impl.get_result()
