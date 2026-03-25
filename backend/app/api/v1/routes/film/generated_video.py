from __future__ import annotations

import base64
import mimetypes
from collections.abc import Iterable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.db import async_session_maker
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.core.tasks import ProviderConfig, VideoGenerationInput, VideoGenerationTask
from app.dependencies import get_db
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.models.studio import FileItem, Shot, ShotDetail, ShotFrameImage, ShotFrameType
from app.schemas.common import ApiResponse, success_response

from .common import TaskCreated, _CreateOnlyTask, bind_task
from .video_request import VideoGenerationTaskRequest

router = APIRouter()


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

    shot = await db.get(Shot, body.shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    shot_detail = await db.get(ShotDetail, body.shot_id)
    if shot_detail is None:
        raise HTTPException(status_code=404, detail="Shot detail not found")
    if shot_detail.duration is None or shot_detail.duration <= 0:
        raise HTTPException(status_code=400, detail="Shot duration is not configured; please set shot duration first")

    required_by_mode: dict[str, tuple[ShotFrameType, ...]] = {
        "first": (ShotFrameType.first,),
        "last": (ShotFrameType.last,),
        "key": (ShotFrameType.key,),
        "first_last": (ShotFrameType.first, ShotFrameType.last),
        "first_last_key": (ShotFrameType.first, ShotFrameType.last, ShotFrameType.key),
        "text_only": (),
    }
    required_frames = required_by_mode[body.reference_mode]

    frame_map: dict[ShotFrameType, ShotFrameImage] = {}
    if required_frames:
        stmt = select(ShotFrameImage).where(
            ShotFrameImage.shot_detail_id == body.shot_id,
            ShotFrameImage.frame_type.in_(required_frames),
        )
        rows = (await db.execute(stmt)).scalars().all()
        frame_map = {r.frame_type: r for r in rows}

    def _missing_frames(required: Iterable[ShotFrameType]) -> list[ShotFrameType]:
        missing: list[ShotFrameType] = []
        for ft in required:
            row = frame_map.get(ft)
            if row is None or not row.file_id:
                missing.append(ft)
        return missing

    if body.reference_mode != "text_only":
        missing = _missing_frames(required_frames)
        if missing:
            missing_name = ",".join(m.value for m in missing)
            raise HTTPException(
                status_code=400,
                detail=f"Required frame image is missing: {missing_name}; please generate it first",
            )

    file_ids = {row.file_id for row in frame_map.values() if row.file_id}
    file_items: dict[str, FileItem] = {}
    if file_ids:
        file_stmt = select(FileItem).where(FileItem.id.in_(file_ids))
        file_rows = (await db.execute(file_stmt)).scalars().all()
        file_items = {f.id: f for f in file_rows}

    async def _frame_base64(ft: ShotFrameType) -> str | None:
        row = frame_map.get(ft)
        if row is None or not row.file_id:
            return None
        file_obj = file_items.get(row.file_id)
        if file_obj is None or not file_obj.storage_key:
            raise HTTPException(
                status_code=400,
                detail=f"Required frame image is missing: {ft.value}; please generate it first",
            )
        try:
            content = await storage.download_file(key=file_obj.storage_key)
        except Exception:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"Required frame image is missing: {ft.value}; please generate it first",
            ) from None
        if not content:
            raise HTTPException(
                status_code=400,
                detail=f"Required frame image is missing: {ft.value}; please generate it first",
            )

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
            content_type = "image/png"

        image_format = content_type.split("/", 1)[1].split(";", 1)[0].strip().lower() or "png"
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:image/{image_format};base64,{encoded}"

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
    final_prompt = (body.prompt or "").strip() or prompt_by_mode[body.reference_mode]
    if body.reference_mode == "text_only" and not final_prompt:
        raise HTTPException(status_code=400, detail="prompt is required when reference_mode=text_only")

    run_args: dict = {
        "provider": provider_cfg.provider,
        "api_key": provider_cfg.api_key,
        "base_url": provider_cfg.base_url,
        "input": {
            "prompt": final_prompt,
            "first_frame_base64": await _frame_base64(ShotFrameType.first),
            "last_frame_base64": await _frame_base64(ShotFrameType.last),
            "key_frame_base64": await _frame_base64(ShotFrameType.key),
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
    await bind_task(
        db,
        task_id=task_record.id,
        target_type="shot",
        target_id=body.shot_id,
        relation_type="video",
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

                await store2.set_result(task_id, result.model_dump())
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

