"""视频生成任务（Task）：对接 OpenAI Videos API 与火山引擎（方舟）内容生成任务。

说明：
- 本模块提供 BaseTask 协议实现，便于接入 TaskManager/路由的 async_polling 模式。
- 任务输入支持：文本 prompt，以及可选的首帧/尾帧/关键帧参考图（base64 或 data URL）。
- 任务输出为：视频 url 和/或 file_id（若上层将视频落库为 FileItem）。
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.task_manager.types import BaseTask

ProviderKey = Literal["openai", "volcengine"]


def _strip_optional_b64(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s if s else None


def _to_image_data_url(value: str) -> str:
    """将参考图规范为 data URL，供 OpenAI image_url 或火山 url 字段使用。"""
    v = value.strip()
    if v.startswith("data:image/"):
        return v
    return f"data:image/png;base64,{v}"


class VideoGenerationInput(BaseModel):
    """视频生成输入：支持文本提示词 + 可选的三种帧参考图（纯 base64 或 data URL）。"""

    model_config = ConfigDict(extra="forbid")

    prompt: Optional[str] = Field(None, description="文本提示词；可与参考图二选一或同时存在")

    first_frame_base64: Optional[str] = Field(None, description="首帧图：纯 base64 或 data:image/...;base64,...")
    last_frame_base64: Optional[str] = Field(None, description="尾帧图：纯 base64 或 data URL")
    key_frame_base64: Optional[str] = Field(None, description="关键帧图：纯 base64 或 data URL")

    # 通用可选参数（供应商可选择支持/忽略）
    model: Optional[str] = Field(None, description="视频模型名称（可选，供应商透传）")
    size: Optional[str] = Field(None, description="分辨率，如 720x1280（可选，供应商透传）")
    seconds: Optional[int] = Field(None, description="时长（秒）（可选，供应商透传）")

    @model_validator(mode="after")
    def require_prompt_or_any_reference(self) -> "VideoGenerationInput":
        has_prompt = bool((self.prompt or "").strip())
        has_ref = any(
            [
                _strip_optional_b64(self.first_frame_base64),
                _strip_optional_b64(self.last_frame_base64),
                _strip_optional_b64(self.key_frame_base64),
            ]
        )
        if not has_prompt and not has_ref:
            raise ValueError("Require prompt or at least one reference frame (base64)")
        return self


class VideoGenerationResult(BaseModel):
    """视频生成结果：返回视频 URL 和/或 file_id。"""

    model_config = ConfigDict(extra="forbid")

    url: Optional[str] = Field(None, description="生成视频可下载 URL")
    file_id: Optional[str] = Field(None, description="落库后的 FileItem.id（type=video）")
    provider_task_id: Optional[str] = Field(None, description="供应商侧任务/视频 ID（用于调试/追踪）")
    provider: Optional[ProviderKey] = Field(None, description="供应商标识")
    status: Optional[str] = Field(None, description="供应商任务状态")

    @model_validator(mode="after")
    def require_url_or_file_id(self) -> "VideoGenerationResult":
        if not self.url and not self.file_id:
            raise ValueError("Either url or file_id must be set")
        return self


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """供应商配置：由调用方注入，避免在 settings 中硬编码。"""

    provider: ProviderKey
    api_key: str
    base_url: str | None = None


def _volcengine_ratio(size: str | None) -> str:
    """方舟 Seedance 等使用 ratio；分辨率字符串（如 720x1280）则回退为 adaptive。"""
    if not size or not str(size).strip():
        return "adaptive"
    s = str(size).strip()
    if s.lower() == "adaptive" or ":" in s:
        return s
    return "adaptive"


def _build_volcengine_content(input_: VideoGenerationInput) -> list[dict[str, Any]]:
    """按方舟视频生成文档组装 content：text + image_url(role=first_frame|last_frame|key_frame)。"""
    items: list[dict[str, Any]] = []
    prompt = (input_.prompt or "").strip()
    if prompt:
        items.append({"type": "text", "text": prompt})

    ff = _strip_optional_b64(input_.first_frame_base64)
    if ff:
        items.append(
            {
                "type": "image_url",
                "role": "first_frame",
                "image_url": {"url": _to_image_data_url(ff)},
            }
        )
    lf = _strip_optional_b64(input_.last_frame_base64)
    if lf:
        items.append(
            {
                "type": "image_url",
                "role": "last_frame",
                "image_url": {"url": _to_image_data_url(lf)},
            }
        )
    kf = _strip_optional_b64(input_.key_frame_base64)
    if kf:
        items.append(
            {
                "type": "image_url",
                "role": "key_frame",
                "image_url": {"url": _to_image_data_url(kf)},
            }
        )
    return items


def _pick_openai_input_reference(input_: VideoGenerationInput) -> dict[str, str] | None:
    """OpenAI 仅支持单一 input_reference；优先级：key > first > last。"""

    for raw in (
        _strip_optional_b64(input_.key_frame_base64),
        _strip_optional_b64(input_.first_frame_base64),
        _strip_optional_b64(input_.last_frame_base64),
    ):
        if raw:
            return {"image_url": _to_image_data_url(raw)}
    return None


class AbstractVideoGenerationTask(BaseTask, ABC):
    """视频生成任务基类：公共状态与 run/status/is_done/get_result。"""

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 2.0,
        timeout_s: float = 120.0,
    ) -> None:
        self._cfg = provider_config
        self._input = input_
        self._poll_interval_s = poll_interval_s
        self._timeout_s = timeout_s
        self._provider_task_id: str | None = None
        self._result: VideoGenerationResult | None = None
        self._error: str = ""

    async def _sleep_poll(self) -> None:
        await asyncio.sleep(self._poll_interval_s)

    @abstractmethod
    async def _create_task(self) -> None:
        """发起供应商创建任务请求，并设置 self._provider_task_id。"""

    @abstractmethod
    async def _poll_and_get_result(self) -> VideoGenerationResult:
        """轮询至终态并解析为 VideoGenerationResult。"""

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
            "task": "video_generation",
            "provider": self._cfg.provider,
            "provider_task_id": self._provider_task_id,
            "done": await self.is_done(),
            "has_result": self._result is not None,
            "error": self._error,
            "status": self._result.status if self._result else None,
        }

    async def is_done(self) -> bool:  # type: ignore[override]
        return self._result is not None or bool(self._error)

    async def get_result(self) -> VideoGenerationResult | None:  # type: ignore[override]
        return self._result


class OpenAIVideoGenerationTask(AbstractVideoGenerationTask):
    """OpenAI Videos API：POST /videos -> 轮询 GET /videos/{id}。"""

    async def _create_task(self) -> None:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from e

        base_url = (self._cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }

        body: dict[str, Any] = {"prompt": self._input.prompt or ""}
        if self._input.model:
            body["model"] = self._input.model
        if self._input.size:
            body["size"] = self._input.size
        if self._input.seconds:
            body["seconds"] = str(int(self._input.seconds))

        ref = _pick_openai_input_reference(self._input)
        if ref:
            body["input_reference"] = ref

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            r = await client.post(f"{base_url}/videos", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            video_id = str(data.get("id") or "")
            if not video_id:
                raise RuntimeError(f"OpenAI /videos missing id: {data!r}")
            self._provider_task_id = video_id

    async def _poll_and_get_result(self) -> VideoGenerationResult:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from e

        base_url = (self._cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        video_id = self._provider_task_id or ""
        if not video_id:
            raise RuntimeError("OpenAI poll missing provider task id")

        headers = {"Authorization": f"Bearer {self._cfg.api_key}"}
        status_val = ""
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            while True:
                rr = await client.get(f"{base_url}/videos/{video_id}", headers=headers)
                rr.raise_for_status()
                meta = rr.json()
                status_val = str(meta.get("status") or "")
                if status_val in ("completed", "failed"):
                    if status_val == "failed":
                        raise RuntimeError(f"OpenAI video failed: {meta.get('error')!r}")
                    break
                await self._sleep_poll()

        return VideoGenerationResult(
            url=f"{base_url}/videos/{video_id}/content",
            file_id=None,
            provider_task_id=video_id,
            provider="openai",
            status=status_val or "completed",
        )


class VolcengineVideoGenerationTask(AbstractVideoGenerationTask):
    """火山引擎（方舟）内容生成任务。

    创建任务请求体与官方示例一致：content[]（text / image_url+role）、duration、model、ratio。
    """

    async def _create_task(self) -> None:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from e

        base_url = (self._cfg.base_url or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
        headers = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }

        content = _build_volcengine_content(self._input)
        if not content:
            raise RuntimeError("Volcengine video requires non-empty content (prompt and/or reference frames)")

        body: dict[str, Any] = {
            "content": content,
            "ratio": _volcengine_ratio(self._input.size),
        }
        if self._input.model:
            body["model"] = self._input.model
        if self._input.seconds is not None:
            body["duration"] = int(self._input.seconds)

        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            r = await client.post(f"{base_url}/contents/generations/tasks", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
            task_id = str(data.get("id") or data.get("task_id") or "")
            if not task_id:
                raise RuntimeError(f"Volcengine create missing id: {data!r}")
            self._provider_task_id = task_id

    async def _poll_and_get_result(self) -> VideoGenerationResult:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from e

        base_url = (self._cfg.base_url or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
        task_id = self._provider_task_id or ""
        if not task_id:
            raise RuntimeError("Volcengine poll missing provider task id")

        headers = {
            "Authorization": f"Bearer {self._cfg.api_key}",
            "Content-Type": "application/json",
        }
        status_val = ""
        video_url: str | None = None
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            while True:
                rr = await client.get(f"{base_url}/contents/generations/tasks/{task_id}", headers=headers)
                rr.raise_for_status()
                meta = rr.json()
                status_val = str(meta.get("status") or "")
                content = meta.get("content") or {}
                if isinstance(content, dict):
                    vu = content.get("video_url")
                    if isinstance(vu, str) and vu:
                        video_url = vu
                if status_val in ("succeeded", "failed", "cancelled"):
                    if status_val != "succeeded":
                        raise RuntimeError(f"Volcengine task not succeeded: status={status_val!r} meta={meta!r}")
                    break
                await self._sleep_poll()

        if not video_url:
            video_url = f"{base_url}/contents/generations/tasks/{task_id}"

        return VideoGenerationResult(
            url=video_url,
            file_id=None,
            provider_task_id=task_id,
            provider="volcengine",
            status=status_val or "succeeded",
        )


class VideoGenerationTask(BaseTask):
    """按 provider 分派到 OpenAI / 火山实现；对外构造函数签名保持不变。"""

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 2.0,
        timeout_s: float = 120.0,
    ) -> None:
        if provider_config.provider == "openai":
            self._impl: AbstractVideoGenerationTask = OpenAIVideoGenerationTask(
                provider_config=provider_config,
                input_=input_,
                poll_interval_s=poll_interval_s,
                timeout_s=timeout_s,
            )
        elif provider_config.provider == "volcengine":
            self._impl = VolcengineVideoGenerationTask(
                provider_config=provider_config,
                input_=input_,
                poll_interval_s=poll_interval_s,
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

    async def get_result(self) -> VideoGenerationResult | None:  # type: ignore[override]
        return await self._impl.get_result()
