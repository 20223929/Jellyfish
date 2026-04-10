"""镜头视频提示词上下文包与渲染服务。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from langchain_core.prompts import PromptTemplate as LcPromptTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.studio import Chapter, PromptCategory, PromptTemplate, Shot, ShotDetail
from app.schemas.studio.shots import (
    ShotPromptAssetRef,
    ShotPromptCameraInfo,
    ShotVideoPromptPackRead,
    ShotVideoPromptPreviewRead,
)
from app.services.common import entity_not_found
from app.services.studio.shot_assets_overview import get_shot_assets_overview


DEFAULT_VIDEO_NEGATIVE_PROMPT = (
    "不要新增无关人物；不要改变角色身份、服装颜色和场景地点；"
    "不要出现文字水印、肢体畸形、镜头跳变和画面闪烁。"
)


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw or "")


def _asset_ref_from_overview_item(item: Any) -> ShotPromptAssetRef:
    return ShotPromptAssetRef(
        type=item.type,
        name=item.name,
        description=item.description or "",
        file_id=item.file_id,
        thumbnail=item.thumbnail,
    )


def _pack_variables(pack: ShotVideoPromptPackRead) -> dict[str, Any]:
    """为 DB 模板暴露稳定变量名。

    同时保留扁平变量和 `pack`，让模板可以逐步迁移到更结构化的写法。
    """
    data = pack.model_dump()
    return {
        "pack": data,
        "shot_id": pack.shot_id,
        "shot_title": pack.title,
        "title": pack.title,
        "script_excerpt": pack.script_excerpt,
        "action_beats": "\n".join(pack.action_beats),
        "dialogue_summary": pack.dialogue_summary,
        "characters": pack.characters,
        "character_names": "、".join(item.name for item in pack.characters),
        "scene": pack.scene,
        "scene_name": pack.scene.name if pack.scene else "",
        "props": pack.props,
        "prop_names": "、".join(item.name for item in pack.props),
        "costumes": pack.costumes,
        "costume_names": "、".join(item.name for item in pack.costumes),
        "camera": pack.camera,
        "camera_shot": pack.camera.camera_shot,
        "angle": pack.camera.angle,
        "movement": pack.camera.movement,
        "duration": pack.camera.duration or "",
        "atmosphere": pack.atmosphere,
        "visual_style": pack.visual_style,
        "style": pack.style,
        "negative_prompt": pack.negative_prompt,
    }


def _render_template(content: str, variables: dict[str, Any]) -> str:
    template = LcPromptTemplate.from_template(template=content, template_format="jinja2")
    render_vars = {name: variables.get(name, "") for name in template.input_variables}
    return template.format(**render_vars).strip()


def _fallback_video_prompt(pack: ShotVideoPromptPackRead) -> str:
    style_text = "，".join(x for x in [pack.visual_style, pack.style] if x)
    camera_text = " / ".join(x for x in [pack.camera.camera_shot, pack.camera.angle, pack.camera.movement] if x)
    parts = [
        f"镜头标题：{pack.title}",
        f"剧本摘录：{pack.script_excerpt}",
        f"画面风格：{style_text}",
        f"镜头语言：{camera_text}",
        f"时长：{pack.camera.duration} 秒" if pack.camera.duration else "",
        f"场景：{pack.scene.name if pack.scene else ''}",
        f"角色：{'、'.join(item.name for item in pack.characters)}",
        f"道具：{'、'.join(item.name for item in pack.props)}",
        f"服装：{'、'.join(item.name for item in pack.costumes)}",
        f"对白摘要：{pack.dialogue_summary}",
        f"氛围：{pack.atmosphere}",
        f"负面约束：{pack.negative_prompt}",
    ]
    return "\n".join(part for part in parts if part.split("：", 1)[-1].strip())


async def _resolve_video_prompt_template(
    db: AsyncSession,
    *,
    template_id: str | None,
) -> PromptTemplate | None:
    if template_id:
        template = await db.get(PromptTemplate, template_id)
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("PromptTemplate"))
        if template.category != PromptCategory.video_prompt:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PromptTemplate is not video_prompt category")
        return template

    stmt = (
        select(PromptTemplate)
        .where(PromptTemplate.category == PromptCategory.video_prompt)
        .order_by(PromptTemplate.is_default.desc(), PromptTemplate.updated_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def build_shot_video_prompt_pack(
    db: AsyncSession,
    *,
    shot_id: str,
) -> ShotVideoPromptPackRead:
    stmt = (
        select(Shot)
        .options(
            selectinload(Shot.detail).selectinload(ShotDetail.dialog_lines),
            selectinload(Shot.chapter).selectinload(Chapter.project),
        )
        .where(Shot.id == shot_id)
    )
    shot = (await db.execute(stmt)).scalar_one_or_none()
    if shot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=entity_not_found("Shot"))

    detail = shot.detail
    project = getattr(getattr(shot, "chapter", None), "project", None)
    overview = await get_shot_assets_overview(db, shot_id=shot_id)

    characters: list[ShotPromptAssetRef] = []
    props: list[ShotPromptAssetRef] = []
    costumes: list[ShotPromptAssetRef] = []
    scene: ShotPromptAssetRef | None = None
    for item in overview.items:
        if not item.is_linked:
            continue
        ref = _asset_ref_from_overview_item(item)
        if item.type == "character":
            characters.append(ref)
        elif item.type == "prop":
            props.append(ref)
        elif item.type == "costume":
            costumes.append(ref)
        elif item.type == "scene" and scene is None:
            scene = ref

    dialog_lines = list(getattr(detail, "dialog_lines", []) or []) if detail is not None else []
    dialogue_summary = "\n".join(
        f"{line.speaker_name or '角色'}：{line.text}" if line.speaker_name else line.text
        for line in sorted(dialog_lines, key=lambda x: (x.index, x.id))
        if line.text
    )

    return ShotVideoPromptPackRead(
        shot_id=shot.id,
        title=shot.title or "",
        script_excerpt=shot.script_excerpt or "",
        action_beats=[],
        dialogue_summary=dialogue_summary,
        characters=characters,
        scene=scene,
        props=props,
        costumes=costumes,
        camera=ShotPromptCameraInfo(
            camera_shot=_enum_value(getattr(detail, "camera_shot", None)),
            angle=_enum_value(getattr(detail, "angle", None)),
            movement=_enum_value(getattr(detail, "movement", None)),
            duration=getattr(detail, "duration", None),
        ),
        atmosphere=str(getattr(detail, "atmosphere", "") or ""),
        visual_style=_enum_value(getattr(project, "visual_style", None)),
        style=_enum_value(getattr(project, "style", None)),
        negative_prompt=DEFAULT_VIDEO_NEGATIVE_PROMPT,
    )


async def render_shot_video_prompt_preview(
    db: AsyncSession,
    *,
    shot_id: str,
    template_id: str | None = None,
) -> ShotVideoPromptPreviewRead:
    pack = await build_shot_video_prompt_pack(db, shot_id=shot_id)
    template = await _resolve_video_prompt_template(db, template_id=template_id)
    warnings: list[str] = []
    if template is None:
        warnings.append("未配置视频提示词模板，已使用系统默认拼装提示词")
        rendered_prompt = _fallback_video_prompt(pack)
    else:
        rendered_prompt = _render_template(template.content, _pack_variables(pack))
        if not rendered_prompt:
            warnings.append("视频提示词模板渲染结果为空，已使用系统默认拼装提示词")
            rendered_prompt = _fallback_video_prompt(pack)

    return ShotVideoPromptPreviewRead(
        shot_id=shot_id,
        template_id=template.id if template else None,
        template_name=template.name if template else None,
        rendered_prompt=rendered_prompt,
        pack=pack,
        warnings=warnings,
    )
