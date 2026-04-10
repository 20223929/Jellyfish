from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import Base
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.models.studio import (
    CameraAngle,
    CameraMovement,
    CameraShotType,
    Chapter,
    Project,
    ProjectStyle,
    ProjectVisualStyle,
    Shot,
    ShotDetail,
    ShotFrameImage,
    ShotFrameType,
    VFXType,
)
from app.services.film.generated_video import (
    build_run_args,
    preview_prompt_and_images,
    provider_key_from_db_name,
    resolve_default_video_model,
    validate_images_count,
)
from app.services.studio import get_shot_video_readiness


async def _build_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    session_local = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_local(), engine


async def _seed_shot_graph(db: AsyncSession) -> None:
    project = Project(
        id="p1",
        name="项目一",
        description="",
        style=ProjectStyle.real_people_city,
        visual_style=ProjectVisualStyle.live_action,
    )
    chapter = Chapter(id="c1", project_id="p1", index=1, title="第一章")
    shot = Shot(id="s1", chapter_id="c1", index=1, title="镜头一", script_excerpt="角色推门而入。")
    detail = ShotDetail(
        id="s1",
        camera_shot=CameraShotType.ms,
        angle=CameraAngle.eye_level,
        movement=CameraMovement.static,
        duration=6,
        follow_atmosphere=True,
        vfx_type=VFXType.none,
        first_frame_prompt="首帧提示词",
        last_frame_prompt="尾帧提示词",
        key_frame_prompt="关键帧提示词",
    )
    db.add_all([project, chapter, shot, detail])
    await db.commit()


@pytest.mark.asyncio
async def test_validate_images_count_rejects_wrong_count() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_images_count("first_last", ["only-one"])

    assert exc_info.value.status_code == 400
    assert "requires exactly 2 images" in exc_info.value.detail


def test_provider_key_from_db_name_supports_known_aliases() -> None:
    assert provider_key_from_db_name("OpenAI") == "openai"
    assert provider_key_from_db_name("火山引擎") == "volcengine"
    assert provider_key_from_db_name("Doubao Video") == "volcengine"


@pytest.mark.asyncio
async def test_resolve_default_video_model_requires_video_category() -> None:
    db, engine = await _build_session()
    async with db:
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k")
        wrong_model = Model(id="m1", name="gpt-4o-mini", category=ModelCategoryKey.text, provider_id="p1")
        settings = ModelSettings(id=1, default_video_model_id="m1")
        db.add_all([provider, wrong_model, settings])
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await resolve_default_video_model(db)

        assert exc_info.value.status_code == 503
        assert "not video category" in exc_info.value.detail
    await engine.dispose()


@pytest.mark.asyncio
async def test_preview_prompt_and_images_uses_auto_frame_ids() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        db.add_all(
            [
                ShotFrameImage(shot_detail_id="s1", frame_type=ShotFrameType.first, file_id="f1", format="png"),
                ShotFrameImage(shot_detail_id="s1", frame_type=ShotFrameType.last, file_id="f2", format="png"),
            ]
        )
        await db.commit()

        prompt, images, detail = await preview_prompt_and_images(
            db,
            shot_id="s1",
            reference_mode="first_last",
            prompt=None,
        )

        assert "镜头标题：镜头一" in prompt
        assert "剧本摘录：角色推门而入。" in prompt
        assert images == ["f1", "f2"]
        assert detail.duration == 6
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_maps_reference_images(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1")
        settings = ModelSettings(id=1, default_video_model_id="m_video")
        db.add_all([provider, model, settings])
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        run_args = await build_run_args(
            db,
            shot_id="s1",
            reference_mode="first_last",
            prompt="最终视频提示词",
            images=["img-first", "img-last"],
            size="720x1280",
        )

        assert run_args["provider"] == "openai"
        assert run_args["api_key"] == "k"
        assert run_args["input"]["model"] == "sora-mini"
        assert run_args["input"]["first_frame_base64"] == "data:image/png;base64,img-first"
        assert run_args["input"]["last_frame_base64"] == "data:image/png;base64,img-last"
        assert run_args["input"]["key_frame_base64"] is None
        assert run_args["input"]["seconds"] == 6
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_run_args_uses_prompt_pack_when_prompt_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1")
        settings = ModelSettings(id=1, default_video_model_id="m_video")
        db.add_all([provider, model, settings])
        await db.commit()

        async def _fake_file_id_to_data_url(_db: AsyncSession, *, file_id: str) -> str:
            return f"data:image/png;base64,{file_id}"

        monkeypatch.setattr(
            "app.services.film.generated_video.file_id_to_data_url",
            _fake_file_id_to_data_url,
        )

        run_args = await build_run_args(
            db,
            shot_id="s1",
            reference_mode="text_only",
            prompt=None,
            images=[],
            size=None,
        )

        assert "镜头标题：镜头一" in run_args["input"]["prompt"]
        assert run_args["prompt_preview"]["shot_id"] == "s1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_shot_video_readiness_reports_ready_for_text_only() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        shot = await db.get(Shot, "s1")
        assert shot is not None
        shot.last_extracted_at = datetime.now(timezone.utc)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1")
        settings = ModelSettings(id=1, default_video_model_id="m_video")
        db.add_all([provider, model, settings])
        await db.flush()

        readiness = await get_shot_video_readiness(db, shot_id="s1", reference_mode="text_only")

        assert readiness.ready is True
        assert {item.key: item.ok for item in readiness.checks}["extraction_ready"] is True
        assert {item.key: item.ok for item in readiness.checks}["reference_frames_ready"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_shot_video_readiness_reports_missing_reference_frame() -> None:
    db, engine = await _build_session()
    async with db:
        await _seed_shot_graph(db)
        shot = await db.get(Shot, "s1")
        assert shot is not None
        shot.last_extracted_at = datetime.now(timezone.utc)
        provider = Provider(id="p1", name="OpenAI", base_url="https://api.openai.com/v1", api_key="k")
        model = Model(id="m_video", name="sora-mini", category=ModelCategoryKey.video, provider_id="p1")
        settings = ModelSettings(id=1, default_video_model_id="m_video")
        db.add_all([provider, model, settings])
        await db.flush()

        readiness = await get_shot_video_readiness(db, shot_id="s1", reference_mode="first")

        checks = {item.key: item for item in readiness.checks}
        assert readiness.ready is False
        assert checks["reference_frames_ready"].ok is False
        assert "first" in checks["reference_frames_ready"].message
    await engine.dispose()
