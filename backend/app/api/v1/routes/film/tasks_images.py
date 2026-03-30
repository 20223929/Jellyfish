from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.language_models.chat_models import BaseChatModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.chains.agents import (
    ShotFirstFramePromptAgent,
    ShotKeyFramePromptAgent,
    ShotLastFramePromptAgent,
)
from app.core.db import async_session_maker
from app.core.task_manager import DeliveryMode, SqlAlchemyTaskStore, TaskManager
from app.core.task_manager.types import TaskStatus
from app.dependencies import get_db, get_llm
from app.models.studio import Shot, ShotDetail
from app.models.task_links import GenerationTaskLink
from app.schemas.common import ApiResponse, success_response

from .common import (
    ShotFramePromptRequest,
    TaskCreated,
    _CreateOnlyTask,
)
from .image_requests import ShotFrameImageTaskRequest

router = APIRouter()


@router.post(
    "/tasks/shot-frame-prompts",
    response_model=ApiResponse[TaskCreated],
    status_code=201,
    summary="镜头分镜帧提示词生成（任务版）",
)
async def create_shot_frame_prompt_task(
    body: ShotFramePromptRequest,
    llm: BaseChatModel = Depends(get_llm),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreated]:
    frame_type = (body.frame_type or "").strip().lower()
    if frame_type not in {"first", "last", "key"}:
        raise HTTPException(status_code=400, detail="frame_type must be one of first/last/key")
    if frame_type == "first":
        relation_type = "shot_first_frame_prompt"
    elif frame_type == "last":
        relation_type = "shot_last_frame_prompt"
    else:
        relation_type = "shot_key_frame_prompt"

    store = SqlAlchemyTaskStore(db)
    tm = TaskManager(store=store, strategies={})

    shot_stmt = (
        select(Shot)
        .options(
            selectinload(Shot.detail).selectinload(ShotDetail.dialog_lines),
        )
        .where(Shot.id == body.shot_id)
    )
    shot = (await db.execute(shot_stmt)).scalar_one_or_none()
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    if shot.detail is None:
        raise HTTPException(status_code=404, detail="Shot detail not found")

    detail = shot.detail
    dialog_summary = "\n".join(line.text for line in (detail.dialog_lines or []) if line.text)
    input_dict = {
        "script_excerpt": shot.script_excerpt or "",
        "title": shot.title or "",
        "camera_shot": detail.camera_shot.value if hasattr(detail.camera_shot, "value") else str(detail.camera_shot),
        "angle": detail.angle.value if hasattr(detail.angle, "value") else str(detail.angle),
        "movement": detail.movement.value if hasattr(detail.movement, "value") else str(detail.movement),
        "atmosphere": detail.atmosphere or "",
        "mood_tags": detail.mood_tags or [],
        "vfx_type": detail.vfx_type.value if hasattr(detail.vfx_type, "value") else str(detail.vfx_type),
        "vfx_note": detail.vfx_note or "",
        "duration": detail.duration,
        "scene_id": detail.scene_id,
        "dialog_summary": dialog_summary,
    }
    run_args: dict = {
        "shot_id": body.shot_id,
        "frame_type": frame_type,
        "input": input_dict,
    }

    task_record = await tm.create(task=_CreateOnlyTask(), mode=DeliveryMode.async_polling, run_args=run_args)
    db.add(
        GenerationTaskLink(
            task_id=task_record.id,
            resource_type="prompt",
            relation_type=relation_type,
            relation_entity_id=body.shot_id,
        )
    )

    async def _runner(task_id: str, args: dict) -> None:
        async with async_session_maker() as session:
            try:
                store2 = SqlAlchemyTaskStore(session)
                await store2.set_status(task_id, TaskStatus.running)
                await store2.set_progress(task_id, 10)
                # 先提交 running 状态，避免长耗时执行期间任务一直显示 pending。
                await session.commit()

                ft = str(args.get("frame_type") or "")
                shot_id = str(args.get("shot_id") or "")
                inp = dict(args.get("input") or {})

                if ft == "first":
                    agent = ShotFirstFramePromptAgent(llm)
                elif ft == "last":
                    agent = ShotLastFramePromptAgent(llm)
                else:
                    agent = ShotKeyFramePromptAgent(llm)
                result = await agent.aextract(**inp)

                if not shot_id:
                    raise RuntimeError("Missing shot_id in run args")
                shot_detail = await session.get(ShotDetail, shot_id)
                if shot_detail is None:
                    raise RuntimeError("Shot detail not found when persisting prompt")

                if ft == "first":
                    shot_detail.first_frame_prompt = result.prompt
                elif ft == "last":
                    shot_detail.last_frame_prompt = result.prompt
                else:
                    shot_detail.key_frame_prompt = result.prompt

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


