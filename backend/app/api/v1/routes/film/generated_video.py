from __future__ import annotations

import base64
import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.db import async_session_maker
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.core.tasks import (
    ProviderConfig,
    VideoGenerationInput,
    VideoGenerationResult,
    VideoGenerationTask,
)
from app.dependencies import get_db
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.models.task_links import GenerationTaskLink
from app.models.studio import FileItem, Shot, ShotDetail, ShotFrameImage, ShotFrameType
from app.models.types import FileUsageKind
from app.services.studio.file_usages import sync_usage_from_shot_context
from app.schemas.common import ApiResponse, success_response
from app.utils.files import create_file_from_url_or_b64

from .common import TaskCreated, _CreateOnlyTask
from .video_request import VideoGenerationTaskRequest

router = APIRouter()


class VideoPromptPreviewResponse(BaseModel):
    prompt: str = Field(..., description="最终用于视频生成的提示词")
    images: list[str] = Field(default_factory=list, description="关联参考图 file_id 列表")


REQUIRED_FRAMES_BY_MODE: dict[str, tuple[ShotFrameType, ...]] = {
    "first": (ShotFrameType.first,),
    "last": (ShotFrameType.last,),
    "key": (ShotFrameType.key,),
    "first_last": (ShotFrameType.first, ShotFrameType.last),
    "first_last_key": (ShotFrameType.first, ShotFrameType.last, ShotFrameType.key),
    "text_only": (),
}


def _required_image_count(reference_mode: str) -> int:
    return len(REQUIRED_FRAMES_BY_MODE[reference_mode])


def _validate_images_count(reference_mode: str, images: list[str]) -> None:
    expected = _required_image_count(reference_mode)
    actual = len(images or [])
    if actual != expected:
        raise HTTPException(
            status_code=400,
            detail=f"reference_mode={reference_mode} requires exactly {expected} images, got {actual}",
        )


async def _validate_shot_and_duration(db: AsyncSession, shot_id: str) -> ShotDetail:
    shot = await db.get(Shot, shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    shot_detail = await db.get(ShotDetail, shot_id)
    if shot_detail is None:
        raise HTTPException(status_code=404, detail="Shot detail not found")
    if shot_detail.duration is None or shot_detail.duration <= 0:
        raise HTTPException(status_code=400, detail="Shot duration is not configured; please set shot duration first")
    return shot_detail


async def _file_id_to_data_url(db: AsyncSession, *, file_id: str) -> str:
    file_obj = await db.get(FileItem, file_id)
    if file_obj is None or not file_obj.storage_key:
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")
    try:
        content = await storage.download_file(key=file_obj.storage_key)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}") from None
    if not content:
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")

    content_type: str | None = None
    try:
        info = await storage.get_file_info(key=file_obj.storage_key)
        content_type = (info.content_type or "").strip().lower() or None
    except Exception:  # noqa: BLE001
        content_type = None
    if not content_type:
        guessed_type, _ = mimetypes.guess_type(file_obj.storage_key)
        content_type = (guessed_type or "").strip().lower() or None
    if not content_type or not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"Invalid image file_id: {file_id}")

    image_format = content_type.split("/", 1)[1].split(";", 1)[0].strip().lower() or "png"
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:image/{image_format};base64,{encoded}"


async def _preview_prompt_and_images_by_old_logic(
    db: AsyncSession,
    *,
    shot_id: str,
    reference_mode: str,
    prompt: str | None,
) -> tuple[str, list[str], ShotDetail]:
    shot_detail = await _validate_shot_and_duration(db, shot_id)
    required_frames = REQUIRED_FRAMES_BY_MODE[reference_mode]

    frame_map: dict[ShotFrameType, ShotFrameImage] = {}
    if required_frames:
        stmt = select(ShotFrameImage).where(
            ShotFrameImage.shot_detail_id == shot_id,
            ShotFrameImage.frame_type.in_(required_frames),
        )
        rows = (await db.execute(stmt)).scalars().all()
        frame_map = {r.frame_type: r for r in rows}

        missing: list[ShotFrameType] = []
        for ft in required_frames:
            row = frame_map.get(ft)
            if row is None or not row.file_id:
                missing.append(ft)
        if missing:
            missing_name = ",".join(m.value for m in missing)
            raise HTTPException(
                status_code=400,
                detail=f"Required frame image is missing: {missing_name}; please generate it first",
            )

    prompt_by_mode = {
        "first": (shot_detail.first_frame_prompt or "").strip(),
        "last": (shot_detail.last_frame_prompt or "").strip(),
        "key": (shot_detail.key_frame_prompt or "").strip(),
        "first_last": "\n".join(
            p
            for p in [
                (shot_detail.first_frame_prompt or "").strip(),
                (shot_detail.last_frame_prompt or "").strip(),
            ]
            if p
        ),
        "first_last_key": "\n".join(
            p
            for p in [
                (shot_detail.first_frame_prompt or "").strip(),
                (shot_detail.last_frame_prompt or "").strip(),
                (shot_detail.key_frame_prompt or "").strip(),
            ]
            if p
        ),
        "text_only": "",
    }
    final_prompt = (prompt or "").strip() or prompt_by_mode[reference_mode]
    if reference_mode == "text_only" and not final_prompt:
        raise HTTPException(status_code=400, detail="prompt is required when reference_mode=text_only")

    image_ids = [str(frame_map[ft].file_id) for ft in required_frames if frame_map.get(ft) and frame_map[ft].file_id]
    return final_prompt, image_ids, shot_detail


def _provider_key_from_db_name(name: str) -> str:
    """将 Provider.name 映射为任务层 ProviderKey（openai | volcengine）。"""
    n = (name or "").strip()
    n_lower = n.lower()
    if n_lower == "openai":
        return "openai"
    if n == "火山引擎" or "volc" in n_lower or "doubao" in n_lower or "bytedance" in n_lower:
        return "volcengine"
    raise HTTPException(
        status_code=503,
        detail=f"Unsupported provider name: {name!r}. Expected: openai, 火山引擎.",
    )


async def _resolve_default_video_model(db: AsyncSession) -> Model:
    settings_row = await db.get(ModelSettings, 1)
    model_id = settings_row.default_video_model_id if settings_row else None
    if not model_id:
        raise HTTPException(
            status_code=503,
            detail="No default video model configured; please set ModelSettings.default_video_model_id first",
        )
    model = await db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=503, detail=f"Configured default video model not found: {model_id}")
    if model.category != ModelCategoryKey.video:
        raise HTTPException(
            status_code=503,
            detail=f"Configured default video model is not video category: {model_id} (category={model.category})",
        )
    return model


async def _load_provider_config_by_model(db: AsyncSession, model: Model) -> ProviderConfig:
    provider = await db.get(Provider, model.provider_id)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail=f"Provider not found for model.provider_id={model.provider_id}",
        )
    provider_key = _provider_key_from_db_name(provider.name)
    api_key = (provider.api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=f"Provider api_key is empty for provider_id={provider.id}",
        )
    base_url = (provider.base_url or "").strip() or None
    return ProviderConfig(provider=provider_key, api_key=api_key, base_url=base_url)  # type: ignore[arg-type]


async def _persist_generated_video_to_shot(
    session: AsyncSession,
    *,
    task_id: str,
    shot_id: str,
    result: VideoGenerationResult,
    provider: str,
    api_key: str,
) -> FileItem:
    """将供应商返回的视频下载后写入对象存储，创建 FileItem，并回填 GenerationTaskLink 与 Shot。"""

    url = (result.url or "").strip()
    if not url:
        raise RuntimeError("Video generation result has no download url")

    url_headers: dict[str, str] | None = None
    if provider == "openai":
        url_headers = {"Authorization": f"Bearer {api_key}"}

    file_obj = await create_file_from_url_or_b64(
        session,
        url=url,
        name=f"shot-{shot_id}-video",
        prefix=f"generated-videos/shots/{shot_id}",
        url_request_headers=url_headers,
        httpx_timeout=600.0,
    )

    link_stmt = (
        select(GenerationTaskLink)
        .where(
            GenerationTaskLink.task_id == task_id,
            GenerationTaskLink.resource_type == "video",
            GenerationTaskLink.relation_type == "video",
            GenerationTaskLink.relation_entity_id == shot_id,
        )
        .limit(1)
    )
    link_row = (await session.execute(link_stmt)).scalars().first()
    if link_row is not None:
        link_row.file_id = file_obj.id

    shot = await session.get(Shot, shot_id)
    if shot is not None:
        shot.generated_video_file_id = file_obj.id

    await sync_usage_from_shot_context(
        session,
        file_id=file_obj.id,
        shot_id=shot_id,
        usage_kind=FileUsageKind.generated_video,
        source_ref=f"shot:{shot_id}:generated_video",
    )

    return file_obj


@router.post(
    "/tasks/video/preview-prompt",
    response_model=ApiResponse[VideoPromptPreviewResponse],
    status_code=200,
    summary="视频提示词预览",
)
async def preview_video_generation_prompt(
    body: VideoGenerationTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VideoPromptPreviewResponse]:
    """预览视频生成的提示词与自动关联参考图。"""
    prompt, images, _shot_detail = await _preview_prompt_and_images_by_old_logic(
        db,
        shot_id=body.shot_id,
        reference_mode=body.reference_mode,
        prompt=body.prompt,
    )
    return success_response(VideoPromptPreviewResponse(prompt=prompt, images=images))


@router.post(
    "/tasks/video",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="视频生成（任务版）",
)
async def create_video_generation_task(
    body: VideoGenerationTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    """创建视频生成任务并后台执行，结果通过 /tasks/{task_id}/result 获取。"""

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})
    model = await _resolve_default_video_model(db)
    provider_cfg = await _load_provider_config_by_model(db, model)

    shot_detail = await _validate_shot_and_duration(db, body.shot_id)
    _validate_images_count(body.reference_mode, body.images)
    final_prompt = (body.prompt or "").strip()
    if not final_prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    required_frames = REQUIRED_FRAMES_BY_MODE[body.reference_mode]
    frame_data_urls = [await _file_id_to_data_url(db, file_id=file_id) for file_id in body.images]
    frame_map = {ft: frame_data_urls[i] for i, ft in enumerate(required_frames)}

    run_args: dict = {
        "shot_id": body.shot_id,
        "provider": provider_cfg.provider,
        "api_key": provider_cfg.api_key,
        "base_url": provider_cfg.base_url,
        "input": {
            "prompt": final_prompt,
            "first_frame_base64": frame_map.get(ShotFrameType.first),
            "last_frame_base64": frame_map.get(ShotFrameType.last),
            "key_frame_base64": frame_map.get(ShotFrameType.key),
            "model": model.name,
            "size": body.size,
            "seconds": shot_detail.duration,
        },
    }

    task_record = await tm.create(
        task=_CreateOnlyTask(),
        mode=DeliveryMode.async_polling,
        run_args=run_args,
    )
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="video",
            relation_type="video",
            relation_entity_id=body.shot_id,
        )
    )

    # 确保任务记录已提交，避免后台 runner 新 session 查询不到任务行而无法更新状态。
    await db.commit()

    async def _runner(task_id: str, args: dict) -> None:
        async with async_session_maker() as session:
            try:
                store2 = SqlAlchemyTaskStore(session)
                await store2.set_status(task_id, TaskStatus.running)
                await store2.set_progress(task_id, 10)
                await session.commit()

                provider = str(args.get("provider") or "")
                api_key = str(args.get("api_key") or "")
                base_url = args.get("base_url")
                input_dict = dict(args.get("input") or {})

                task = VideoGenerationTask(
                    provider_config=ProviderConfig(
                        provider=provider,  # type: ignore[arg-type]
                        api_key=api_key,
                        base_url=base_url,
                    ),
                    input_=VideoGenerationInput.model_validate(input_dict),
                )
                await task.run()
                result = await task.get_result()
                if result is None:
                    # 同步透传底层任务中的具体错误，便于排查。
                    status_dict = await task.status()  # type: ignore[assignment]
                    detailed_error = ""
                    if isinstance(status_dict, dict):
                        detailed_error = str(status_dict.get("error") or "")
                    msg = detailed_error or "Video generation task returned no result"
                    raise RuntimeError(msg)

                shot_id_run = str(args.get("shot_id") or "")
                if not shot_id_run:
                    raise RuntimeError("run_args missing shot_id for video persistence")

                file_obj = await _persist_generated_video_to_shot(
                    session,
                    task_id=task_id,
                    shot_id=shot_id_run,
                    result=result,
                    provider=provider,
                    api_key=api_key,
                )

                result_payload = result.model_dump()
                result_payload["file_id"] = file_obj.id
                await store2.set_result(task_id, result_payload)
                await store2.set_progress(task_id, 100)
                await store2.set_status(task_id, TaskStatus.succeeded)
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                async with async_session_maker() as s2:
                    store3 = SqlAlchemyTaskStore(s2)
                    await store3.set_error(task_id, str(exc))
                    await store3.set_status(task_id, TaskStatus.failed)
                    await s2.commit()

    import asyncio

    asyncio.create_task(_runner(task_record.id, run_args))
    return success_response(TaskCreated(task_id=task_record.id), code=201)

