from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin
from app.models.types import (
    CameraAngle,
    CameraMovement,
    CameraShotType,
    DialogueLineMode,
    ShotFrameType,
    ShotStatus,
    VFXType,
)


class Shot(Base,TimestampMixin):
    """镜头表（基础信息）。

    说明：
    - 目前未混入 `TimestampMixin`，避免在高频生成/更新流程中引入额外写放大；如需要审计可再补。
    - 细节放在 `ShotDetail` 以保持主表字段稳定。
    """

    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="镜头 ID")
    chapter_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属章节 ID",
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False, comment="镜头序号（章节内唯一）")
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="镜头标题")
    thumbnail: Mapped[str] = mapped_column(String(1024), nullable=False, default="", comment="缩略图 URL/路径")
    status: Mapped[ShotStatus] = mapped_column(
        String(32),
        nullable=False,
        default=ShotStatus.pending,
        comment="镜头状态",
    )
    script_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="剧本摘录")
    generated_video_file_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="已生成视频关联的文件 ID（FileItem，type=video）",
    )

    chapter: Mapped["Chapter"] = relationship(back_populates="shots")
    generated_video_file: Mapped["FileItem | None"] = relationship(
        foreign_keys=[generated_video_file_id]
    )
    detail: Mapped["ShotDetail"] = relationship(
        back_populates="shot",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    actor_links: Mapped[list["ProjectActorLink"]] = relationship(
        back_populates="shot",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectActorLink.id",
    )
    scene_links: Mapped[list["ProjectSceneLink"]] = relationship(
        back_populates="shot",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectSceneLink.id",
    )
    prop_links: Mapped[list["ProjectPropLink"]] = relationship(
        back_populates="shot",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectPropLink.id",
    )
    costume_links: Mapped[list["ProjectCostumeLink"]] = relationship(
        back_populates="shot",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectCostumeLink.id",
    )
    character_links: Mapped[list["ShotCharacterLink"]] = relationship(
        back_populates="shot",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ShotCharacterLink.index",
    )

    __table_args__ = (
        UniqueConstraint("chapter_id", "index", name="uq_shots_chapter_index"),
        Index("ix_shots_status", "status"),
        Index("ix_shots_chapter_title", "chapter_id", "title"),
    )


class ShotDetail(Base,TimestampMixin):
    """镜头细节（1:1）。

    设计点：
    - 与 `Shot` 共享主键，确保一条镜头最多一份细节，且删除镜头时细节级联删除。
    - `mood_tags` 用 JSON 存 list[str]，与前端 mock 对齐。

    应用层保证：
    - `scene_id` 所指场景应与镜头所属项目一致或为全局场景，避免跨项目引用。
    """

    __tablename__ = "shot_details"

    # 与 Shot 共享主键（1:1）：用外键作为主键，强制一对一。
    id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("shots.id", ondelete="CASCADE"),
        primary_key=True,
        comment="镜头 ID（与 shots.id 共享主键）",
    )
    camera_shot: Mapped[CameraShotType] = mapped_column(
        String(16),
        nullable=False,
        comment="景别（存 code：ECU/CU/MCU/MS/MLS/LS/ELS；展示可用 schemas.SHOT_TYPE_ZH）",
    )
    angle: Mapped[CameraAngle] = mapped_column(
        String(16),
        nullable=False,
        comment="机位角度（存 code：EYE_LEVEL/HIGH_ANGLE/...；展示可用 schemas.CAMERA_ANGLE_ZH）",
    )
    movement: Mapped[CameraMovement] = mapped_column(
        String(16),
        nullable=False,
        comment="运镜方式（存 code：STATIC/PAN/...；展示可用 schemas.CAMERA_MOVEMENT_ZH）",
    )
    scene_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("scenes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="关联场景 ID（可空）；应用层需保证与镜头所属项目一致或全局",
    )
    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="时长（秒）；镜头唯一时长来源")
    mood_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, comment="情绪标签（JSON 数组）")
    atmosphere: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="氛围描述")
    follow_atmosphere: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否沿用氛围")
    has_bgm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否包含 BGM")
    vfx_type: Mapped[VFXType] = mapped_column(
        String(32),
        nullable=False,
        default=VFXType.none,
        comment="视效类型（存 code；展示可用 schemas.VFX_TYPE_ZH）",
    )
    vfx_note: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="视效说明（简短可执行）")
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="分镜整体描述（用于提示词补充）",
    )
    prompt_template_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        nullable=True,
        comment="分镜提示词模板 ID（可选）",
    )
    first_frame_prompt: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="镜头分镜首帧提示词",
    )
    last_frame_prompt: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="镜头分镜尾帧提示词",
    )
    key_frame_prompt: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="镜头分镜关键帧提示词",
    )

    shot: Mapped["Shot"] = relationship(back_populates="detail")
    scene: Mapped["Scene | None"] = relationship()
    frame_images: Mapped[list["ShotFrameImage"]] = relationship(
        back_populates="shot_detail",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ShotFrameImage.id",
    )
    dialog_lines: Mapped[list["ShotDialogLine"]] = relationship(
        back_populates="shot_detail",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ShotDialogLine.index",
    )

    prompt_template: Mapped["PromptTemplate | None"] = relationship()

    __table_args__ = (
        Index("ix_shot_details_camera_shot", "camera_shot"),
        Index("ix_shot_details_angle", "angle"),
        Index("ix_shot_details_prompt_template_id", "prompt_template_id"),
    )


class ShotFrameImage(Base, TimestampMixin):
    """镜头分镜帧图片（首帧/尾帧/关键帧）。每镜头每类型一条记录，通过 file_id 关联 files 表。

    应用层保证：
    - 同一 shot_detail_id + frame_type 至多一条记录（表唯一约束）。
    """

    __tablename__ = "shot_frame_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="图片行 ID")
    shot_detail_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("shot_details.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属镜头细节 ID",
    )
    frame_type: Mapped[ShotFrameType] = mapped_column(
        String(16),
        nullable=False,
        index=True,
        comment="帧类型：first/last/key",
    )
    file_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="关联的文件 ID（FileItem）",
    )
    width: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="宽（px）")
    height: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="高（px）")
    format: Mapped[str] = mapped_column(String(32), nullable=False, default="png", comment="格式")

    shot_detail: Mapped["ShotDetail"] = relationship(back_populates="frame_images")

    __table_args__ = (
        UniqueConstraint("shot_detail_id", "frame_type", name="uq_shot_frame_images_detail_type"),
    )


class ShotDialogLine(Base,TimestampMixin):
    """镜头对话行。

    设计点：
    - 前端 mock 里 `dialog` 为数组，这里拆表以支持排序、检索与后续对齐字幕/配音等能力。
    - `shot_detail_id + index` 唯一，保证行号稳定。

    应用层保证：
    - `speaker_character_id` / `target_character_id` 所指角色应与该镜头所属章节/项目一致，避免跨项目引用。
    """

    __tablename__ = "shot_dialog_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="对话行自增 ID")
    shot_detail_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("shot_details.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属镜头细节 ID",
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="行号（镜头内排序）")
    text: Mapped[str] = mapped_column(Text, nullable=False, comment="台词内容")
    line_mode: Mapped[DialogueLineMode] = mapped_column(
        String(16),
        nullable=False,
        default=DialogueLineMode.dialogue,
        comment="对白模式（DIALOGUE/VOICE_OVER/OFF_SCREEN/PHONE；对齐 schemas.DIALOGUE_LINE_MODE_ZH）",
    )
    speaker_character_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="说话角色 ID；应用层需保证与镜头所属项目一致",
    )
    target_character_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="听者角色 ID；应用层需保证与镜头所属项目一致",
    )

    speaker_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="说话角色名称（用于从提取结果回填角色关联；可空）",
    )
    target_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="听者角色名称（用于从提取结果回填角色关联；可空）",
    )

    shot_detail: Mapped["ShotDetail"] = relationship(back_populates="dialog_lines")
    speaker_character: Mapped["Character | None"] = relationship(foreign_keys=[speaker_character_id])
    target_character: Mapped["Character | None"] = relationship(foreign_keys=[target_character_id])

    __table_args__ = (
        UniqueConstraint("shot_detail_id", "index", name="uq_shot_dialog_lines_shot_index"),
    )


class ShotCharacterLink(Base,TimestampMixin):
    """镜头引用角色（多对多）。

    应用层保证：
    - 所引用角色应与镜头所属项目一致（角色表本身归属项目，写入时校验可避免跨项目引用）。
    """

    __tablename__ = "shot_character_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="关联行 ID")
    shot_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("shots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="镜头 ID",
    )
    character_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="角色 ID",
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="镜头内角色排序")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="备注（可选）")

    shot: Mapped["Shot"] = relationship(back_populates="character_links")
    character: Mapped["Character"] = relationship(back_populates="shot_links")

    __table_args__ = (
        UniqueConstraint("shot_id", "character_id", name="uq_shot_character_links_shot_character"),
        UniqueConstraint("shot_id", "index", name="uq_shot_character_links_shot_index"),
    )


__all__ = [
    "Shot",
    "ShotDetail",
    "ShotFrameImage",
    "ShotDialogLine",
    "ShotCharacterLink",
]

