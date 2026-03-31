"""Studio 业务服务。"""

from app.services.studio.entities import (
    StudioEntitiesService,
    download_url,
    entity_spec,
    normalize_entity_type,
    resolve_thumbnails,
    resolve_thumbnail_infos,
)

__all__ = [
    "StudioEntitiesService",
    "download_url",
    "entity_spec",
    "normalize_entity_type",
    "resolve_thumbnails",
    "resolve_thumbnail_infos",
]

# image_tasks 依赖存储/第三方 SDK（如 boto3）；在某些轻量环境中可能未安装。
# 为了让不依赖该能力的模块（如 entities / shots）可正常导入，这里做可选导入。
try:
    from app.services.studio.image_tasks import (  # noqa: F401
        asset_prompt_category,
        build_prompt_with_template,
        is_front_view,
        load_provider_config,
        map_view_angle_for_prompt,
        resolve_front_image_ref,
        resolve_image_model,
        resolve_ordered_image_refs,
        shot_frame_prompt_category,
    )

    __all__ += [
        "asset_prompt_category",
        "build_prompt_with_template",
        "is_front_view",
        "load_provider_config",
        "map_view_angle_for_prompt",
        "resolve_front_image_ref",
        "resolve_image_model",
        "resolve_ordered_image_refs",
        "shot_frame_prompt_category",
    ]
except Exception:  # noqa: BLE001
    pass
