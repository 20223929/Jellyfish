"""与 LLM 相关的 Pydantic Schema（Provider/Model/ModelSettings）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.llm import LogLevel, ModelCategoryKey, ProviderStatus


class ProviderBase(BaseModel):
    """供应商通用字段（不含敏感字段）。"""

    name: str = Field(..., description="供应商名称")
    base_url: str = Field(..., description="API Base URL")
    description: str = Field("", description="说明")
    status: ProviderStatus = Field(
        ProviderStatus.testing,
        description="状态：active/testing/disabled",
    )
    created_by: str = Field("", description="创建人")


class ProviderCreate(ProviderBase):
    """创建供应商时的请求体，允许填写敏感字段。"""

    id: str = Field(..., description="供应商 ID")
    api_key: str = Field("", description="API Key（敏感，不在响应中回显）")
    api_secret: str = Field("", description="API Secret（敏感，不在响应中回显）")


class ProviderUpdate(BaseModel):
    """更新供应商时的可选字段。"""

    name: str | None = Field(None, description="供应商名称")
    base_url: str | None = Field(None, description="API Base URL")
    description: str | None = Field(None, description="说明")
    status: ProviderStatus | None = Field(
        None,
        description="状态：active/testing/disabled",
    )
    api_key: str | None = Field(None, description="API Key（敏感，不在响应中回显）")
    api_secret: str | None = Field(None, description="API Secret（敏感，不在响应中回显）")


class ProviderRead(ProviderBase):
    """对外返回的供应商信息（不包含 api_key/api_secret）。"""

    id: str = Field(..., description="供应商 ID")

    class Config:
        from_attributes = True


class ModelBase(BaseModel):
    """模型通用字段。"""

    name: str = Field(..., description="模型名称")
    category: ModelCategoryKey = Field(..., description="模型类别：text/image/video")
    provider_id: str = Field(..., description="所属供应商 ID")
    params: dict[str, Any] = Field(default_factory=dict, description="模型参数（JSON）")
    description: str = Field("", description="说明")
    is_default: bool = Field(False, description="是否默认")
    created_by: str = Field("", description="创建人")


class ModelCreate(ModelBase):
    """创建模型请求体。"""

    id: str = Field(..., description="模型 ID")


class ModelUpdate(BaseModel):
    """更新模型请求体（全部可选）。"""

    name: str | None = Field(None, description="模型名称")
    category: ModelCategoryKey | None = Field(None, description="模型类别")
    provider_id: str | None = Field(None, description="所属供应商 ID")
    params: dict[str, Any] | None = Field(None, description="模型参数（JSON）")
    description: str | None = Field(None, description="说明")
    is_default: bool | None = Field(None, description="是否默认")


class ModelRead(ModelBase):
    """对外返回的模型信息。"""

    id: str = Field(..., description="模型 ID")

    class Config:
        from_attributes = True


class ModelSettingsBase(BaseModel):
    """模型全局设置通用字段。"""

    default_text_model_id: str | None = Field(None, description="默认文本模型 ID")
    default_image_model_id: str | None = Field(None, description="默认图片模型 ID")
    default_video_model_id: str | None = Field(None, description="默认视频模型 ID")
    api_timeout: int = Field(30, description="API 超时（秒）")
    log_level: LogLevel = Field(LogLevel.info, description="日志级别")


class ModelSettingsUpdate(ModelSettingsBase):
    """更新或保存模型全局设置请求体。"""

    pass


class ModelSettingsRead(ModelSettingsBase):
    """对外返回的模型全局设置。"""

    id: int = Field(..., description="设置行 ID（通常为 1）")

    class Config:
        from_attributes = True

