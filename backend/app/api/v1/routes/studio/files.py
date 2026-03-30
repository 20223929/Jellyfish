"""文件素材相关路由：上传 / 下载 / 列表 / 详情。"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.utils import apply_keyword_filter, apply_order, paginate
from app.core import storage
from app.dependencies import get_db
from app.models.studio import FileItem, FileType
from app.schemas.common import ApiResponse, PaginatedData, paginated_response, success_response
from app.schemas.studio import FileDetailRead, FileRead, FileUpdate, FileUsageRead, FileUsageWrite
from app.services.studio.file_usages import list_files_by_scope_paginated, upsert_file_usage

router = APIRouter()

FILE_ORDER_FIELDS = {"name", "created_at", "updated_at"}


@router.get(
    "",
    response_model=ApiResponse[PaginatedData[FileRead]],
    summary="文件列表（分页）",
)
async def list_files_api(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None, description="关键字，过滤 name"),
    order: str | None = Query(None),
    is_desc: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    project_id: str | None = Query(None, description="按 file_usages 限定项目；提供后仅返回该项目下有关联记录的文件"),
    chapter_title: str | None = Query(None, description="章节标题（精确匹配，与 project_id 联用）"),
    shot_title: str | None = Query(None, description="镜头标题（精确匹配，与 project_id 联用）"),
) -> ApiResponse[PaginatedData[FileRead]]:
    if chapter_title is not None or shot_title is not None:
        if not project_id:
            raise HTTPException(
                status_code=400,
                detail="project_id is required when chapter_title or shot_title is set",
            )

    if project_id is not None:
        items, total = await list_files_by_scope_paginated(
            db,
            project_id=project_id,
            chapter_title=chapter_title,
            shot_title=shot_title,
            q=q,
            order=order,
            is_desc=is_desc,
            page=page,
            page_size=page_size,
        )
        return paginated_response(
            [FileRead.model_validate(x) for x in items],
            page=page,
            page_size=page_size,
            total=total,
        )

    stmt = select(FileItem)
    stmt = apply_keyword_filter(stmt, q=q, fields=[FileItem.name])
    stmt = apply_order(
        stmt,
        model=FileItem,
        order=order,
        is_desc=is_desc,
        allow_fields=FILE_ORDER_FIELDS,
        default="created_at",
    )
    items, total = await paginate(db, stmt=stmt, page=page, page_size=page_size)
    return paginated_response(
        [FileRead.model_validate(x) for x in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/upload",
    response_model=ApiResponse[FileRead],
    status_code=status.HTTP_201_CREATED,
    summary="上传文件并创建 FileItem 记录",
)
async def upload_file_api(
    file: UploadFile = File(..., description="要上传的二进制文件"),
    name: str | None = None,
    db: AsyncSession = Depends(get_db),
    project_id: str | None = Form(None, description="可选：写入 file_usages 的项目 ID"),
    chapter_id: str | None = Form(None),
    shot_id: str | None = Form(None),
    usage_kind: str | None = Form(None, description="与 project_id 同时提供时写入 file_usages"),
    source_ref: str | None = Form(None),
) -> ApiResponse[FileRead]:

    if not file.filename:
        raise HTTPException(status_code=400, detail="上传文件缺少文件名")

    # 从后缀推断文件类型
    _, ext = os.path.splitext(file.filename.lower())
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        file_type = FileType.image
    elif ext in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        file_type = FileType.video
    else:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '未知后缀'}")

    # 名称：未传 name 时使用“去掉后缀的文件名”
    if name:
        display_name = name
    else:
        base, _ = os.path.splitext(file.filename)
        display_name = base or file.filename

    content = await file.read()

    # 这里存“逻辑 key”，不再包含 project_id/chapter_id，归属由 file_usages 区分。
    key = f"files/{file.filename}"
    info = await storage.upload_file(
        key=key,
        data=content,
        content_type=file.content_type,
        extra_args={"ACL": "public-read"},
    )

    # 使用 UUID 作为对外 file_id，storage_key 单独存储
    file_id = str(uuid.uuid4())

    obj = await db.get(FileItem, file_id)
    if obj is None:
        obj = FileItem(
            id=file_id,
            type=file_type,
            name=display_name,
            thumbnail=info.url,
            tags=[],
            storage_key=key,
        )
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
    else:
        obj.type = file_type
        obj.name = display_name
        if not obj.thumbnail:
            obj.thumbnail = info.url
        await db.flush()
        await db.refresh(obj)

    if project_id and usage_kind:
        await upsert_file_usage(
            db,
            file_id=obj.id,
            project_id=project_id,
            chapter_id=chapter_id,
            shot_id=shot_id,
            usage_kind=usage_kind,
            source_ref=source_ref,
        )

    return success_response(FileRead.model_validate(obj), code=201)


@router.get(
    "/{file_id}/download",
    summary="下载文件二进制内容",
)
async def download_file_api(
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(FileItem, file_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="File not found")

    content = await storage.download_file(key=obj.storage_key)

    # 使用存储 key 的原始文件名（包含扩展名）作为下载文件名
    filename = Path(obj.storage_key).name or "download"

    # 根据扩展名设置合理的 Content-Type，兼容常见图片/视频类型
    ext = Path(filename).suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        media_type = "image/jpeg"
    elif ext == ".png":
        media_type = "image/png"
    elif ext == ".webp":
        media_type = "image/webp"
    elif ext == ".gif":
        media_type = "image/gif"
    elif ext == ".mp4":
        media_type = "video/mp4"
    elif ext == ".mov":
        media_type = "video/quicktime"
    elif ext in {".mkv", ".avi", ".webm"}:
        media_type = "video/" + ext.lstrip(".")
    else:
        media_type = "application/octet-stream"

    # Content-Disposition 中的文件名需要是 ASCII；使用 RFC 5987 形式避免中文导致的编码错误。
    safe_filename = filename
    content_disposition = f"attachment; filename*=UTF-8''{quote(safe_filename)}"
    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": content_disposition},
    )


@router.get(
    "/{file_id}/storage-info",
    response_model=ApiResponse[dict],
    summary="获取对象存储详情（head_object）",
)
async def get_file_storage_info_api(
    file_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    obj = await db.get(FileItem, file_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="File not found")

    info = await storage.get_file_info(key=obj.storage_key)
    return success_response(
        {
            "key": info.key,
            "url": info.url,
            "size": info.size,
            "content_type": info.content_type,
            "etag": info.etag,
        }
    )


@router.get(
    "/{file_id}",
    response_model=ApiResponse[FileDetailRead],
    summary="获取文件详情（元信息 + file_usages）",
)
async def get_file_detail(
    file_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FileDetailRead]:
    stmt = select(FileItem).options(selectinload(FileItem.usages)).where(FileItem.id == file_id)
    res = await db.execute(stmt)
    obj = res.scalars().first()
    if obj is None:
        raise HTTPException(status_code=404, detail="File not found")
    usages = [FileUsageRead.model_validate(u) for u in (obj.usages or [])]
    base = FileRead.model_validate(obj)
    return success_response(FileDetailRead(**base.model_dump(), usages=usages))


@router.patch(
    "/{file_id}",
    response_model=ApiResponse[FileRead],
    summary="更新文件元信息",
)
async def update_file_meta(
    file_id: str,
    body: FileUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FileRead]:
    obj = await db.get(FileItem, file_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="File not found")

    data = body.model_dump(exclude_unset=True)
    usage_payload = data.pop("usage", None)
    for k, v in data.items():
        setattr(obj, k, v)
    if usage_payload is not None:
        u = FileUsageWrite.model_validate(usage_payload)
        await upsert_file_usage(
            db,
            file_id=file_id,
            project_id=u.project_id,
            chapter_id=u.chapter_id,
            shot_id=u.shot_id,
            usage_kind=u.usage_kind,
            source_ref=u.source_ref,
        )
    await db.flush()
    await db.refresh(obj)
    return success_response(FileRead.model_validate(obj))


@router.delete(
    "/{file_id}",
    response_model=ApiResponse[None],
    summary="删除文件（记录 + 存储对象）",
)
async def delete_file_api(
    file_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    obj = await db.get(FileItem, file_id)
    if obj is None:
        return success_response(None)

    try:
        await storage.delete_file(key=obj.storage_key)
    except Exception:
        ...

    await db.delete(obj)
    await db.flush()
    return success_response(None)
