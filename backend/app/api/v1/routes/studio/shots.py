"""Shot 相关 CRUD：Shot / ShotDetail / ShotDialogLine / 资源 Link。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.dependencies import get_db
from app.services.studio.entities import (
    entity_spec,
    normalize_entity_type,
    resolve_thumbnail_infos,
    resolve_thumbnails,
)
from app.models.studio import (
    Chapter,
    Character,
    Costume,
    Project,
    Prop,
    Scene,
    Shot,
    Actor,
    ProjectActorLink,
    ProjectCostumeLink,
    ProjectPropLink,
    ProjectSceneLink,
    ShotDetail,
    ShotDialogLine,
    ShotCharacterLink,
    ShotFrameImage,
)
from app.schemas.common import ApiResponse, PaginatedData, paginated_response, success_response
from app.schemas.studio.shots import (
    ProjectActorLinkRead,
    ProjectAssetLinkCreate,
    ProjectCostumeLinkRead,
    ShotLinkedAssetItem,
    ShotCreate,
    ShotDetailCreate,
    ShotDetailRead,
    ShotDetailUpdate,
    ShotDialogLineCreate,
    ShotDialogLineRead,
    ShotDialogLineUpdate,
    ProjectPropLinkRead,
    ShotRead,
    ProjectSceneLinkRead,
    ShotUpdate,
    ShotFrameImageCreate,
    ShotFrameImageRead,
    ShotFrameImageUpdate,
)
from app.utils.project_links import upsert_project_link

router = APIRouter()
details_router = APIRouter()
dialog_router = APIRouter()
links_router = APIRouter()
frames_router = APIRouter()

SHOT_ORDER_FIELDS = {"index", "title", "status", "created_at", "updated_at"}
DETAIL_ORDER_FIELDS = {"id"}
DIALOG_ORDER_FIELDS = {"index", "id", "created_at", "updated_at"}
LINK_ORDER_FIELDS = {"id", "created_at", "updated_at"}
FRAME_IMAGE_ORDER_FIELDS = {"id", "frame_type", "created_at", "updated_at"}


async def _ensure_chapter(db: AsyncSession, chapter_id: str) -> None:
    if await db.get(Chapter, chapter_id) is None:
        raise HTTPException(status_code=400, detail="Chapter not found")


async def _ensure_project(db: AsyncSession, project_id: str) -> None:
    if await db.get(Project, project_id) is None:
        raise HTTPException(status_code=400, detail="Project not found")


async def _ensure_chapter_optional(db: AsyncSession, chapter_id: str | None) -> None:
    if chapter_id is None:
        return
    await _ensure_chapter(db, chapter_id)


async def _ensure_shot_optional(db: AsyncSession, shot_id: str | None) -> None:
    if shot_id is None:
        return
    await _ensure_shot(db, shot_id)


async def _ensure_shot(db: AsyncSession, shot_id: str) -> None:
    if await db.get(Shot, shot_id) is None:
        raise HTTPException(status_code=400, detail="Shot not found")


async def _ensure_scene_optional(db: AsyncSession, scene_id: str | None) -> None:
    if scene_id is None:
        return
    if await db.get(Scene, scene_id) is None:
        raise HTTPException(status_code=400, detail="Scene not found")


async def _ensure_character_optional(db: AsyncSession, character_id: str | None) -> None:
    if character_id is None:
        return
    if await db.get(Character, character_id) is None:
        raise HTTPException(status_code=400, detail="Character not found")


async def _ensure_actor(db: AsyncSession, actor_id: str) -> None:
    if await db.get(Actor, actor_id) is None:
        raise HTTPException(status_code=400, detail="Actor not found")


async def _ensure_prop(db: AsyncSession, prop_id: str) -> None:
    if await db.get(Prop, prop_id) is None:
        raise HTTPException(status_code=400, detail="Prop not found")


async def _ensure_costume(db: AsyncSession, costume_id: str) -> None:
    if await db.get(Costume, costume_id) is None:
        raise HTTPException(status_code=400, detail="Costume not found")


# ---------- Shot ----------


@router.get(
    "",
    response_model=ApiResponse[PaginatedData[ShotRead]],
    summary="镜头列表（分页）",
)
async def list_shots(
    db: AsyncSession = Depends(get_db),
    chapter_id: str | None = Query(None, description="按章节过滤"),
    q: str | None = Query(None, description="关键字，过滤 title/script_excerpt"),
    order: str | None = Query(None),
    is_desc: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[ShotRead]]:
    stmt = select(Shot)
    if chapter_id is not None:
        stmt = stmt.where(Shot.chapter_id == chapter_id)
    stmt = apply_keyword_filter(stmt, q=q, fields=[Shot.title, Shot.script_excerpt])
    stmt = apply_order(stmt, model=Shot, order=order, is_desc=is_desc, allow_fields=SHOT_ORDER_FIELDS, default="index")
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response([ShotRead.model_validate(x) for x in items], page=page, page_size=page_size, total=total)


@router.post(
    "",
    response_model=ApiResponse[ShotRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建镜头",
)
async def create_shot(
    body: ShotCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotRead]:
    exists = await db.get(Shot, body.id)
    if exists is not None:
        raise HTTPException(status_code=400, detail=f"Shot with id={body.id} already exists")
    await _ensure_chapter(db, body.chapter_id)
    obj = Shot(**body.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return success_response(ShotRead.model_validate(obj), code=201)


@router.get(
    "/{shot_id}",
    response_model=ApiResponse[ShotRead],
    summary="获取镜头",
)
async def get_shot(
    shot_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotRead]:
    obj = await db.get(Shot, shot_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    return success_response(ShotRead.model_validate(obj))


@router.patch(
    "/{shot_id}",
    response_model=ApiResponse[ShotRead],
    summary="更新镜头",
)
async def update_shot(
    shot_id: str,
    body: ShotUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotRead]:
    obj = await db.get(Shot, shot_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    update_data = body.model_dump(exclude_unset=True)
    if "chapter_id" in update_data:
        await _ensure_chapter(db, update_data["chapter_id"])
    for k, v in update_data.items():
        setattr(obj, k, v)
    await db.flush()
    await db.refresh(obj)
    return success_response(ShotRead.model_validate(obj))


@router.delete(
    "/{shot_id}",
    response_model=ApiResponse[None],
    summary="删除镜头",
)
async def delete_shot(
    shot_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    obj = await db.get(Shot, shot_id)
    if obj is None:
        return success_response(None)
    await db.delete(obj)
    await db.flush()
    return success_response(None)


@router.get(
    "/{shot_id}/linked-assets",
    response_model=ApiResponse[PaginatedData[ShotLinkedAssetItem]],
    summary="获取镜头关联的角色/道具/场景/服装（分页）",
)
async def list_shot_linked_assets(
    shot_id: str,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[ShotLinkedAssetItem]]:
    await _ensure_shot(db, shot_id)

    # 1) Collect linked entity ids (links-only as requested)
    character_ids = (await db.execute(
        select(ShotCharacterLink.character_id).where(ShotCharacterLink.shot_id == shot_id)
    )).scalars().all()
    prop_ids = (await db.execute(
        select(ProjectPropLink.prop_id).where(ProjectPropLink.shot_id == shot_id)
    )).scalars().all()
    scene_ids = (await db.execute(
        select(ProjectSceneLink.scene_id).where(ProjectSceneLink.shot_id == shot_id)
    )).scalars().all()
    costume_ids = (await db.execute(
        select(ProjectCostumeLink.costume_id).where(ProjectCostumeLink.shot_id == shot_id)
    )).scalars().all()

    # de-dup & drop nulls
    character_ids = [x for x in dict.fromkeys(character_ids) if x]
    prop_ids = [x for x in dict.fromkeys(prop_ids) if x]
    scene_ids = [x for x in dict.fromkeys(scene_ids) if x]
    costume_ids = [x for x in dict.fromkeys(costume_ids) if x]

    # 2) Load names
    character_rows = []
    if character_ids:
        character_rows = (await db.execute(
            select(Character.id, Character.name).where(Character.id.in_(character_ids))
        )).all()
    prop_rows = []
    if prop_ids:
        prop_rows = (await db.execute(
            select(Prop.id, Prop.name).where(Prop.id.in_(prop_ids))
        )).all()
    scene_rows = []
    if scene_ids:
        scene_rows = (await db.execute(
            select(Scene.id, Scene.name).where(Scene.id.in_(scene_ids))
        )).all()
    costume_rows = []
    if costume_ids:
        costume_rows = (await db.execute(
            select(Costume.id, Costume.name).where(Costume.id.in_(costume_ids))
        )).all()

    character_name = {str(r[0]): str(r[1]) for r in character_rows}
    prop_name = {str(r[0]): str(r[1]) for r in prop_rows}
    scene_name = {str(r[0]): str(r[1]) for r in scene_rows}
    costume_name = {str(r[0]): str(r[1]) for r in costume_rows}

    # 3) Resolve thumbnail + image_id
    character_thumb = await resolve_thumbnail_infos(
        db,
        image_model=entity_spec("character").image_model,
        parent_field_name="character_id",
        parent_ids=list(character_name.keys()),
    )
    prop_thumb = await resolve_thumbnail_infos(
        db,
        image_model=entity_spec("prop").image_model,
        parent_field_name="prop_id",
        parent_ids=list(prop_name.keys()),
    )
    scene_thumb = await resolve_thumbnail_infos(
        db,
        image_model=entity_spec("scene").image_model,
        parent_field_name="scene_id",
        parent_ids=list(scene_name.keys()),
    )
    costume_thumb = await resolve_thumbnail_infos(
        db,
        image_model=entity_spec("costume").image_model,
        parent_field_name="costume_id",
        parent_ids=list(costume_name.keys()),
    )

    # 4) Build items (stable order: character/prop/scene/costume, then name)
    items: list[ShotLinkedAssetItem] = []
    for cid, name in character_name.items():
        info = character_thumb.get(cid) or {}
        items.append(
            ShotLinkedAssetItem(
                type="character",
                id=cid,
                image_id=info.get("image_id"),
                file_id=info.get("file_id"),
                name=name,
                thumbnail=str(info.get("thumbnail") or ""),
            )
        )
    for pid, name in prop_name.items():
        info = prop_thumb.get(pid) or {}
        items.append(
            ShotLinkedAssetItem(
                type="prop",
                id=pid,
                image_id=info.get("image_id"),
                file_id=info.get("file_id"),
                name=name,
                thumbnail=str(info.get("thumbnail") or ""),
            )
        )
    for sid, name in scene_name.items():
        info = scene_thumb.get(sid) or {}
        items.append(
            ShotLinkedAssetItem(
                type="scene",
                id=sid,
                image_id=info.get("image_id"),
                file_id=info.get("file_id"),
                name=name,
                thumbnail=str(info.get("thumbnail") or ""),
            )
        )
    for coid, name in costume_name.items():
        info = costume_thumb.get(coid) or {}
        items.append(
            ShotLinkedAssetItem(
                type="costume",
                id=coid,
                image_id=info.get("image_id"),
                file_id=info.get("file_id"),
                name=name,
                thumbnail=str(info.get("thumbnail") or ""),
            )
        )

    items.sort(key=lambda x: (x.type, x.name, x.id))
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return paginated_response(items[start:end], page=page, page_size=page_size, total=total)


# ---------- ShotDetail ----------


@details_router.get(
    "",
    response_model=ApiResponse[PaginatedData[ShotDetailRead]],
    summary="镜头细节列表（分页）",
)
async def list_shot_details(
    db: AsyncSession = Depends(get_db),
    shot_id: str | None = Query(None, description="按镜头过滤（id 同 shot_id）"),
    order: str | None = Query(None),
    is_desc: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[ShotDetailRead]]:
    stmt = select(ShotDetail)
    if shot_id is not None:
        stmt = stmt.where(ShotDetail.id == shot_id)
    stmt = apply_order(stmt, model=ShotDetail, order=order, is_desc=is_desc, allow_fields=DETAIL_ORDER_FIELDS, default="id")
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response([ShotDetailRead.model_validate(x) for x in items], page=page, page_size=page_size, total=total)


@details_router.post(
    "",
    response_model=ApiResponse[ShotDetailRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建镜头细节",
)
async def create_shot_detail(
    body: ShotDetailCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotDetailRead]:
    exists = await db.get(ShotDetail, body.id)
    if exists is not None:
        raise HTTPException(status_code=400, detail="ShotDetail already exists")
    await _ensure_shot(db, body.id)
    await _ensure_scene_optional(db, body.scene_id)
    obj = ShotDetail(**body.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return success_response(ShotDetailRead.model_validate(obj), code=201)


@details_router.get(
    "/{shot_id}",
    response_model=ApiResponse[ShotDetailRead],
    summary="获取镜头细节",
)
async def get_shot_detail(
    shot_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotDetailRead]:
    obj = await db.get(ShotDetail, shot_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ShotDetail not found")
    return success_response(ShotDetailRead.model_validate(obj))


@details_router.patch(
    "/{shot_id}",
    response_model=ApiResponse[ShotDetailRead],
    summary="更新镜头细节",
)
async def update_shot_detail(
    shot_id: str,
    body: ShotDetailUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotDetailRead]:
    obj = await db.get(ShotDetail, shot_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ShotDetail not found")
    update_data = body.model_dump(exclude_unset=True)
    if "scene_id" in update_data:
        await _ensure_scene_optional(db, update_data["scene_id"])
    for k, v in update_data.items():
        setattr(obj, k, v)
    await db.flush()
    await db.refresh(obj)
    return success_response(ShotDetailRead.model_validate(obj))


@details_router.delete(
    "/{shot_id}",
    response_model=ApiResponse[None],
    summary="删除镜头细节",
)
async def delete_shot_detail(
    shot_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    obj = await db.get(ShotDetail, shot_id)
    if obj is None:
        return success_response(None)
    await db.delete(obj)
    await db.flush()
    return success_response(None)


# ---------- ShotDialogLine ----------


@dialog_router.get(
    "",
    response_model=ApiResponse[PaginatedData[ShotDialogLineRead]],
    summary="镜头对话行列表（分页）",
)
async def list_shot_dialog_lines(
    db: AsyncSession = Depends(get_db),
    shot_detail_id: str | None = Query(None, description="按镜头细节过滤"),
    q: str | None = Query(None, description="关键字，过滤 text"),
    order: str | None = Query(None),
    is_desc: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[ShotDialogLineRead]]:
    stmt = select(ShotDialogLine)
    if shot_detail_id is not None:
        stmt = stmt.where(ShotDialogLine.shot_detail_id == shot_detail_id)
    stmt = apply_keyword_filter(stmt, q=q, fields=[ShotDialogLine.text])
    stmt = apply_order(stmt, model=ShotDialogLine, order=order, is_desc=is_desc, allow_fields=DIALOG_ORDER_FIELDS, default="index")
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response([ShotDialogLineRead.model_validate(x) for x in items], page=page, page_size=page_size, total=total)


@dialog_router.post(
    "",
    response_model=ApiResponse[ShotDialogLineRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建镜头对话行",
)
async def create_shot_dialog_line(
    body: ShotDialogLineCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotDialogLineRead]:
    if await db.get(ShotDetail, body.shot_detail_id) is None:
        raise HTTPException(status_code=400, detail="ShotDetail not found")
    await _ensure_character_optional(db, body.speaker_character_id)
    await _ensure_character_optional(db, body.target_character_id)
    obj = ShotDialogLine(**body.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return success_response(ShotDialogLineRead.model_validate(obj), code=201)


@dialog_router.patch(
    "/{line_id}",
    response_model=ApiResponse[ShotDialogLineRead],
    summary="更新镜头对话行",
)
async def update_shot_dialog_line(
    line_id: int,
    body: ShotDialogLineUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotDialogLineRead]:
    obj = await db.get(ShotDialogLine, line_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ShotDialogLine not found")
    update_data = body.model_dump(exclude_unset=True)
    if "speaker_character_id" in update_data:
        await _ensure_character_optional(db, update_data["speaker_character_id"])
    if "target_character_id" in update_data:
        await _ensure_character_optional(db, update_data["target_character_id"])
    for k, v in update_data.items():
        setattr(obj, k, v)
    await db.flush()
    await db.refresh(obj)
    return success_response(ShotDialogLineRead.model_validate(obj))


@dialog_router.delete(
    "/{line_id}",
    response_model=ApiResponse[None],
    summary="删除镜头对话行",
)
async def delete_shot_dialog_line(
    line_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    obj = await db.get(ShotDialogLine, line_id)
    if obj is None:
        return success_response(None)
    await db.delete(obj)
    await db.flush()
    return success_response(None)


# ---------- ShotFrameImage ----------


@frames_router.get(
    "",
    response_model=ApiResponse[PaginatedData[ShotFrameImageRead]],
    summary="镜头分镜帧图片列表（分页）",
)
async def list_shot_frame_images(
    db: AsyncSession = Depends(get_db),
    shot_detail_id: str | None = Query(None, description="按镜头细节过滤"),
    order: str | None = Query(None),
    is_desc: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[ShotFrameImageRead]]:
    stmt = select(ShotFrameImage)
    if shot_detail_id is not None:
        stmt = stmt.where(ShotFrameImage.shot_detail_id == shot_detail_id)
    stmt = apply_order(
        stmt,
        model=ShotFrameImage,
        order=order,
        is_desc=is_desc,
        allow_fields=FRAME_IMAGE_ORDER_FIELDS,
        default="id",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response(
        [ShotFrameImageRead.model_validate(x) for x in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@frames_router.post(
    "",
    response_model=ApiResponse[ShotFrameImageRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建镜头分镜帧图片",
)
async def create_shot_frame_image(
    body: ShotFrameImageCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotFrameImageRead]:
    if await db.get(ShotDetail, body.shot_detail_id) is None:
        raise HTTPException(status_code=400, detail="ShotDetail not found")
    obj = ShotFrameImage(**body.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return success_response(ShotFrameImageRead.model_validate(obj), code=201)


@frames_router.patch(
    "/{image_id}",
    response_model=ApiResponse[ShotFrameImageRead],
    summary="更新镜头分镜帧图片",
)
async def update_shot_frame_image(
    image_id: int,
    body: ShotFrameImageUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ShotFrameImageRead]:
    obj = await db.get(ShotFrameImage, image_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="ShotFrameImage not found")
    update_data = body.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(obj, k, v)
    await db.flush()
    await db.refresh(obj)
    return success_response(ShotFrameImageRead.model_validate(obj))


@frames_router.delete(
    "/{image_id}",
    response_model=ApiResponse[None],
    summary="删除镜头分镜帧图片",
)
async def delete_shot_frame_image(
    image_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    obj = await db.get(ShotFrameImage, image_id)
    if obj is None:
        return success_response(None)
    await db.delete(obj)
    await db.flush()
    return success_response(None)


# ---------- Links（镜头引用资产） ----------


@links_router.get(
    "/{entity_type}",
    response_model=ApiResponse[PaginatedData[Any]],
    summary="项目-章节-镜头-实体关联列表（分页）",
)
async def list_project_entity_links(
    entity_type: str,
    db: AsyncSession = Depends(get_db),
    project_id: str | None = Query(None),
    chapter_id: str | None = Query(None),
    shot_id: str | None = Query(None),
    asset_id: str | None = Query(None),
    order: str | None = Query(None),
    is_desc: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
) -> ApiResponse[PaginatedData[Any]]:
    return await _list_project_asset_links(
        entity_type=entity_type,
        db=db,
        project_id=project_id,
        chapter_id=chapter_id,
        shot_id=shot_id,
        asset_id=asset_id,
        order=order,
        is_desc=is_desc,
        page=page,
        page_size=page_size,
    )


def _link_spec(entity_type: str) -> dict[str, Any]:
    t = normalize_entity_type(entity_type)
    if t == "actor":
        return {"model": ProjectActorLink, "field": "actor_id", "read_model": ProjectActorLinkRead}
    if t == "scene":
        return {"model": ProjectSceneLink, "field": "scene_id", "read_model": ProjectSceneLinkRead}
    if t == "prop":
        return {"model": ProjectPropLink, "field": "prop_id", "read_model": ProjectPropLinkRead}
    if t == "costume":
        return {"model": ProjectCostumeLink, "field": "costume_id", "read_model": ProjectCostumeLinkRead}
    raise HTTPException(status_code=400, detail="entity_type must be one of: actor/scene/prop/costume")


async def _list_project_asset_links(
    *,
    entity_type: str,
    db: AsyncSession,
    project_id: str | None,
    chapter_id: str | None,
    shot_id: str | None,
    asset_id: str | None,
    order: str | None,
    is_desc: bool,
    page: int,
    page_size: int,
) -> ApiResponse[PaginatedData[Any]]:
    spec = _link_spec(entity_type)
    model = spec["model"]
    field_name = spec["field"]

    stmt = select(model)
    if project_id is not None:
        stmt = stmt.where(model.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(model.chapter_id == chapter_id)
    if shot_id is not None:
        stmt = stmt.where(model.shot_id == shot_id)
    if asset_id is not None:
        stmt = stmt.where(getattr(model, field_name) == asset_id)
    stmt = apply_order(stmt, model=model, order=order, is_desc=is_desc, allow_fields=LINK_ORDER_FIELDS, default="id")
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)

    es = entity_spec(entity_type)
    ids = [getattr(x, field_name) for x in items if getattr(x, field_name, None)]
    thumbnails = await resolve_thumbnails(
        db,
        image_model=es.image_model,
        parent_field_name=es.id_field,
        parent_ids=ids,
    )
    read_model = spec["read_model"]
    payload = [
        read_model.model_validate(x).model_copy(update={"thumbnail": thumbnails.get(getattr(x, field_name), "")})
        for x in items
    ]
    return paginated_response(payload, page=page, page_size=page_size, total=total)


@links_router.post(
    "/actor",
    response_model=ApiResponse[ProjectActorLinkRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建项目-章节-镜头-演员关联",
)
async def create_project_actor_link(
    body: ProjectAssetLinkCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectActorLinkRead]:
    await _ensure_actor(db, body.asset_id)
    obj = await upsert_project_link(
        db,
        model=ProjectActorLink,
        asset_field="actor_id",
        asset_id=body.asset_id,
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        shot_id=body.shot_id,
    )
    return success_response(ProjectActorLinkRead.model_validate(obj), code=201)



@links_router.delete(
    "/actor/{link_id}",
    response_model=ApiResponse[None],
    summary="删除项目-章节-镜头-演员关联",
)
async def delete_project_actor_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    obj = await db.get(ProjectActorLink, link_id)
    if obj is None:
        return success_response(None)
    await db.delete(obj)
    await db.flush()
    return success_response(None)


@links_router.post(
    "/scene",
    response_model=ApiResponse[ProjectSceneLinkRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建项目-章节-镜头-场景关联",
)
async def create_project_scene_link(
    body: ProjectAssetLinkCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectSceneLinkRead]:
    await _ensure_scene_optional(db, body.asset_id)
    obj = await upsert_project_link(
        db,
        model=ProjectSceneLink,
        asset_field="scene_id",
        asset_id=body.asset_id,
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        shot_id=body.shot_id,
    )
    return success_response(ProjectSceneLinkRead.model_validate(obj), code=201)



@links_router.delete(
    "/scene/{link_id}",
    response_model=ApiResponse[None],
    summary="删除项目-章节-镜头-场景关联",
)
async def delete_project_scene_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    obj = await db.get(ProjectSceneLink, link_id)
    if obj is None:
        return success_response(None)
    await db.delete(obj)
    await db.flush()
    return success_response(None)


@links_router.post(
    "/prop",
    response_model=ApiResponse[ProjectPropLinkRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建项目-章节-镜头-道具关联",
)
async def create_project_prop_link(
    body: ProjectAssetLinkCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectPropLinkRead]:
    await _ensure_prop(db, body.asset_id)
    obj = await upsert_project_link(
        db,
        model=ProjectPropLink,
        asset_field="prop_id",
        asset_id=body.asset_id,
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        shot_id=body.shot_id,
    )
    return success_response(ProjectPropLinkRead.model_validate(obj), code=201)



@links_router.delete(
    "/prop/{link_id}",
    response_model=ApiResponse[None],
    summary="删除项目-章节-镜头-道具关联",
)
async def delete_project_prop_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    obj = await db.get(ProjectPropLink, link_id)
    if obj is None:
        return success_response(None)
    await db.delete(obj)
    await db.flush()
    return success_response(None)


@links_router.post(
    "/costume",
    response_model=ApiResponse[ProjectCostumeLinkRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建项目-章节-镜头-服装关联",
)
async def create_project_costume_link(
    body: ProjectAssetLinkCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProjectCostumeLinkRead]:
    await _ensure_costume(db, body.asset_id)
    obj = await upsert_project_link(
        db,
        model=ProjectCostumeLink,
        asset_field="costume_id",
        asset_id=body.asset_id,
        project_id=body.project_id,
        chapter_id=body.chapter_id,
        shot_id=body.shot_id,
    )
    return success_response(ProjectCostumeLinkRead.model_validate(obj), code=201)


@links_router.delete(
    "/costume/{link_id}",
    response_model=ApiResponse[None],
    summary="删除项目-章节-镜头-服装关联",
)
async def delete_project_costume_link(
    link_id: int,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    obj = await db.get(ProjectCostumeLink, link_id)
    if obj is None:
        return success_response(None)
    await db.delete(obj)
    await db.flush()
    return success_response(None)

