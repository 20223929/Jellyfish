"""image_tasks 接口响应壳测试。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi.testclient import TestClient

from app.api.v1.routes.studio import image_tasks as route
from app.dependencies import get_db
from app.main import app


class _DummyDB:
    async def get(self, *_args, **_kwargs):
        return None


def _override_db(db: _DummyDB):
    async def _get_db() -> AsyncGenerator[_DummyDB, None]:
        yield db

    return _get_db


def test_create_actor_image_task_requires_prompt(client: TestClient) -> None:
    db = _DummyDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/studio/image-tasks/actors/actor-1/image-tasks",
            json={"image_id": 1, "prompt": "   ", "images": []},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {
        "code": 400,
        "message": "prompt is required for actor generation",
        "data": None,
        "meta": None,
    }


def test_render_actor_image_prompt_returns_success_envelope(client: TestClient, monkeypatch) -> None:
    db = _DummyDB()

    async def _fake_build(*_args, **_kwargs):
        return "渲染后的演员提示词", ["file-1", "file-2"], object()

    monkeypatch.setattr(route, "_build_actor_prompt_and_refs_service", _fake_build)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/studio/image-tasks/actors/actor-1/render-prompt",
            json={"image_id": 1, "images": []},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"]["prompt"] == "渲染后的演员提示词"
    assert body["data"]["images"] == ["file-1", "file-2"]


def test_create_shot_frame_image_task_requires_prompt(client: TestClient) -> None:
    db = _DummyDB()
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/studio/image-tasks/shot/shot-1/frame-image-tasks",
            json={"frame_type": "first", "prompt": "   ", "images": []},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json() == {
        "code": 400,
        "message": "prompt is required for shot frame generation",
        "data": None,
        "meta": None,
    }


def test_render_shot_frame_prompt_returns_success_envelope_when_prompt_given(client: TestClient, monkeypatch) -> None:
    db = _DummyDB()

    async def _fake_resolve(*_args, **_kwargs):
        return ["file-1", "file-2"], ["角色正面", "场景远景"]

    monkeypatch.setattr(route, "_resolve_reference_file_ids_and_names_from_linked_items_service", _fake_resolve)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/studio/image-tasks/shot/shot-1/frame-render-prompt",
            json={
                "frame_type": "first",
                "prompt": "生成一个紧张的首帧画面",
                "images": [],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"]["images"] == ["file-1", "file-2"]
    assert "图1: 角色正面" in body["data"]["prompt"]
    assert "生成一个紧张的首帧画面" in body["data"]["prompt"]


def test_render_shot_frame_prompt_allows_empty_prompt(client: TestClient, monkeypatch) -> None:
    db = _DummyDB()

    async def _fake_resolve(*_args, **_kwargs):
        return ["file-1"], ["角色正面"]

    async def _fake_build(*_args, **_kwargs):
        return "自动生成的首帧提示词", ["file-1"], object()

    monkeypatch.setattr(route, "_resolve_reference_file_ids_and_names_from_linked_items_service", _fake_resolve)
    monkeypatch.setattr(route, "_build_shot_frame_prompt_and_refs_service", _fake_build)
    app.dependency_overrides[get_db] = _override_db(db)
    try:
        response = client.post(
            "/api/v1/studio/image-tasks/shot/shot-1/frame-render-prompt",
            json={
                "frame_type": "first",
                "prompt": "",
                "images": [],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"]["prompt"] == "自动生成的首帧提示词"
    assert body["data"]["images"] == ["file-1"]
