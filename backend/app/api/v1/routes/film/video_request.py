from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

class VideoGenerationTaskRequest(BaseModel):
    """视频生成任务请求：基于 shot_id 自动组装参考帧与时长。"""

    shot_id: str = Field(..., description="镜头 ID")
    reference_mode: Literal["first", "last", "key", "first_last", "first_last_key", "text_only"] = Field(
        ...,
        description="参考模式：first | last | key | first_last | first_last_key | text_only",
    )
    # 文本模式必填；非文本模式可选作为补充描述
    prompt: str | None = Field(None, description="视频提示词（text_only 必填）")

    size: str | None = Field(None, description="分辨率（可选），如 720x1280")
    # seconds 由 ShotDetail.duration 自动确定；请求体不再接收覆盖值。

