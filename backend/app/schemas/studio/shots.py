"""镜头相关 schemas：Shot / ShotDetail / ShotDialogLine / Link 表。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.studio import (
    CameraAngle,
    CameraMovement,
    CameraShotType,
    DialogueLineMode,
    ShotFrameType,
    ShotStatus,
    VFXType,
)


class ShotBase(BaseModel):
    id: str = Field(..., description="镜头 ID")
    chapter_id: str = Field(..., description="所属章节 ID")
    index: int = Field(..., description="镜头序号（章节内唯一）")
    title: str = Field(..., description="镜头标题")
    thumbnail: str = Field("", description="缩略图 URL/路径")
    status: ShotStatus = Field(ShotStatus.pending, description="镜头状态")
    script_excerpt: str = Field("", description="剧本摘录")
    generated_video_file_id: str | None = Field(
        None,
        description="已生成视频关联的文件 ID（files.id，type=video）",
    )


class ShotCreate(ShotBase):
    pass


class ShotUpdate(BaseModel):
    chapter_id: str | None = None
    index: int | None = None
    title: str | None = None
    thumbnail: str | None = None
    status: ShotStatus | None = None
    script_excerpt: str | None = None
    generated_video_file_id: str | None = None


class ShotRead(ShotBase):
    class Config:
        from_attributes = True


class ShotDetailBase(BaseModel):
    id: str = Field(..., description="镜头 ID（与 shots.id 共享主键）")
    camera_shot: CameraShotType = Field(..., description="景别")
    angle: CameraAngle = Field(..., description="机位角度")
    movement: CameraMovement = Field(..., description="运镜方式")
    scene_id: str | None = Field(None, description="关联场景 ID（可空）")
    duration: int = Field(0, description="时长（秒）")
    mood_tags: list[str] = Field(default_factory=list, description="情绪标签")
    atmosphere: str = Field("", description="氛围描述")
    follow_atmosphere: bool = Field(True, description="是否沿用氛围")
    has_bgm: bool = Field(False, description="是否包含 BGM")
    vfx_type: VFXType = Field(VFXType.none, description="视效类型")
    vfx_note: str = Field("", description="视效说明")
    first_frame_prompt: str = Field(
        "",
        description="镜头分镜首帧提示词",
    )
    last_frame_prompt: str = Field(
        "",
        description="镜头分镜尾帧提示词",
    )
    key_frame_prompt: str = Field(
        "",
        description="镜头分镜关键帧提示词",
    )


class ShotDetailCreate(ShotDetailBase):
    pass


class ShotDetailUpdate(BaseModel):
    camera_shot: CameraShotType | None = None
    angle: CameraAngle | None = None
    movement: CameraMovement | None = None
    scene_id: str | None = None
    duration: int | None = None
    mood_tags: list[str] | None = None
    atmosphere: str | None = None
    follow_atmosphere: bool | None = None
    has_bgm: bool | None = None
    vfx_type: VFXType | None = None
    vfx_note: str | None = None
    first_frame_prompt: str | None = None
    last_frame_prompt: str | None = None
    key_frame_prompt: str | None = None


class ShotDetailRead(ShotDetailBase):
    class Config:
        from_attributes = True


class ShotDialogLineBase(BaseModel):
    id: int = Field(..., description="对话行 ID")
    shot_detail_id: str = Field(..., description="所属镜头细节 ID")
    index: int = Field(0, description="行号（镜头内排序）")
    text: str = Field(..., description="台词内容")
    line_mode: DialogueLineMode = Field(DialogueLineMode.dialogue, description="对白模式")
    speaker_character_id: str | None = Field(None, description="说话角色 ID")
    target_character_id: str | None = Field(None, description="听者角色 ID")
    speaker_name: str | None = Field(None, description="说话角色名称（用于回填关联；可空）")
    target_name: str | None = Field(None, description="听者角色名称（用于回填关联；可空）")


class ShotDialogLineCreate(BaseModel):
    shot_detail_id: str
    index: int = 0
    text: str
    line_mode: DialogueLineMode = DialogueLineMode.dialogue
    speaker_character_id: str | None = None
    target_character_id: str | None = None
    speaker_name: str | None = None
    target_name: str | None = None


class ShotDialogLineUpdate(BaseModel):
    index: int | None = None
    text: str | None = None
    line_mode: DialogueLineMode | None = None
    speaker_character_id: str | None = None
    target_character_id: str | None = None
    speaker_name: str | None = None
    target_name: str | None = None


class ShotDialogLineRead(ShotDialogLineBase):
    class Config:
        from_attributes = True


class ProjectLinkBase(BaseModel):
    id: int = Field(..., description="关联行 ID")
    project_id: str = Field(..., description="项目 ID")
    chapter_id: str | None = Field(None, description="章节 ID（可空）")
    shot_id: str | None = Field(None, description="镜头 ID（可空）")


class ProjectAssetLinkCreate(BaseModel):
    project_id: str
    chapter_id: str | None = None
    shot_id: str | None = None
    asset_id: str


class ProjectActorLinkRead(ProjectLinkBase):
    actor_id: str
    thumbnail: str = Field("", description="演员缩略图下载地址")

    class Config:
        from_attributes = True


class ProjectSceneLinkRead(ProjectLinkBase):
    scene_id: str
    thumbnail: str = Field("", description="场景缩略图下载地址")

    class Config:
        from_attributes = True


class ProjectPropLinkRead(ProjectLinkBase):
    prop_id: str
    thumbnail: str = Field("", description="道具缩略图下载地址")

    class Config:
        from_attributes = True


class ProjectCostumeLinkRead(ProjectLinkBase):
    costume_id: str
    thumbnail: str = Field("", description="服装缩略图下载地址")

    class Config:
        from_attributes = True


class ShotFrameImageBase(BaseModel):
    id: int = Field(..., description="图片行 ID")
    shot_detail_id: str = Field(..., description="所属镜头细节 ID")
    frame_type: ShotFrameType = Field(..., description="帧类型：first/last/key")
    file_id: str | None = Field(None, description="关联的 FileItem ID（可为空，允许先创建占位）")
    width: int | None = Field(None, description="宽(px)")
    height: int | None = Field(None, description="高(px)")
    format: str = Field("png", description="格式")


class ShotFrameImageCreate(BaseModel):
    shot_detail_id: str
    frame_type: ShotFrameType
    file_id: str | None = None
    width: int | None = None
    height: int | None = None
    format: str = "png"


class ShotFrameImageUpdate(BaseModel):
    frame_type: ShotFrameType | None = None
    file_id: str | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None


class ShotFrameImageRead(ShotFrameImageBase):
    class Config:
        from_attributes = True


ShotLinkedAssetType = Literal["character", "prop", "scene", "costume"]


class ShotLinkedAssetItem(BaseModel):
    """按分镜聚合返回的关联资产条目（角色/道具/场景/服装）。"""

    type: ShotLinkedAssetType = Field(..., description="实体类型：character/prop/scene/costume")
    id: str = Field(..., description="实体 ID（如 character_id/prop_id/scene_id/costume_id）")
    image_id: int | None = Field(
        None,
        description="最佳缩略图对应的 image 行 ID（如 PropImage.id）；无图则为 null",
    )
    file_id: str | None = Field(
        None,
        description="最佳缩略图对应的文件 ID（files.id）；用于参考图输入；无图则为 null",
    )
    name: str = Field(..., description="实体名称")
    thumbnail: str = Field("", description="缩略图下载地址（/api/v1/studio/files/{file_id}/download）")

