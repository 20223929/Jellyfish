from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.core.task_manager import SqlAlchemyTaskStore
from app.core.task_manager.types import DeliveryMode
from app.models.task import GenerationTask, GenerationTaskStatus
from app.services.film.generated_video import run_video_generation_task
from app.services.film.shot_frame_prompt_tasks import run_shot_frame_prompt_task
from app.services.studio.image_task_runner import run_image_generation_task


@pytest.mark.asyncio
async def test_run_video_generation_task_marks_cancelled_before_execute(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "video-worker-cancel.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import app.models.task  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_local() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.create(
            payload={"task_kind": "video_generation", "run_args": {"shot_id": "shot-1"}},
            mode=DeliveryMode.async_polling,
            task_kind="video_generation",
        )
        await store.request_cancel(task.id, "用户取消")
        await db.commit()

    monkeypatch.setattr("app.services.film.generated_video.async_session_maker", session_local)

    await run_video_generation_task(task_id=task.id, run_args={"shot_id": "shot-1"})

    async with session_local() as db:
        row = await db.get(GenerationTask, task.id)
        assert row is not None
        assert row.status == GenerationTaskStatus.cancelled
        assert bool(row.cancel_requested) is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_run_image_generation_task_marks_cancelled_before_execute(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "image-worker-cancel.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import app.models.task  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_local() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.create(
            payload={
                "task_kind": "image_generation",
                "run_args": {"relation_type": "character", "relation_entity_id": "char-1"},
            },
            mode=DeliveryMode.async_polling,
            task_kind="image_generation",
        )
        await store.request_cancel(task.id, "用户取消")
        await db.commit()

    monkeypatch.setattr("app.services.studio.image_task_runner.async_session_maker", session_local)

    await run_image_generation_task(
        task_id=task.id,
        run_args={"relation_type": "character", "relation_entity_id": "char-1"},
    )

    async with session_local() as db:
        row = await db.get(GenerationTask, task.id)
        assert row is not None
        assert row.status == GenerationTaskStatus.cancelled
        assert bool(row.cancel_requested) is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_run_shot_frame_prompt_task_marks_cancelled_before_execute(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "shot-frame-worker-cancel.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import app.models.task  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_local() as db:
        store = SqlAlchemyTaskStore(db)
        task = await store.create(
            payload={"task_kind": "shot_frame_prompt", "run_args": {"shot_id": "shot-1", "frame_type": "first"}},
            mode=DeliveryMode.async_polling,
            task_kind="shot_frame_prompt",
        )
        await store.request_cancel(task.id, "用户取消")
        await db.commit()

    monkeypatch.setattr("app.services.film.shot_frame_prompt_tasks.async_session_maker", session_local)

    await run_shot_frame_prompt_task(task_id=task.id, run_args={"shot_id": "shot-1", "frame_type": "first"})

    async with session_local() as db:
        row = await db.get(GenerationTask, task.id)
        assert row is not None
        assert row.status == GenerationTaskStatus.cancelled
        assert bool(row.cancel_requested) is True

    await engine.dispose()
