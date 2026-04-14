"""视频生成能力约束与参数映射辅助。"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd

from app.core.contracts.provider import ProviderKey
from app.core.contracts.video_generation import VideoGenerationInput

ALLOWED_RATIOS = {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9"}


@dataclass(frozen=True, slots=True)
class VideoModelCapability:
    """供应商/模型能力约束。"""

    supports_seed: bool = True
    supports_watermark: bool = True
    allowed_ratios: set[str] | None = None
    allowed_sizes: set[str] | None = None
    min_seconds: int | None = 1
    max_seconds: int | None = None


def register_video_model_capability(
    *,
    provider: ProviderKey,
    model_prefix: str,
    capability: VideoModelCapability,
) -> None:
    """兼容入口：注册模型能力覆盖（按前缀匹配，大小写不敏感）。"""
    if provider == "openai":
        from app.core.integrations.openai.video_capabilities import register_openai_video_capability

        register_openai_video_capability(model_prefix=model_prefix, capability=capability)
        return
    from app.core.integrations.volcengine.video_capabilities import register_volcengine_video_capability

    register_volcengine_video_capability(model_prefix=model_prefix, capability=capability)


def clear_video_model_capability_overrides(*, provider: ProviderKey | None = None) -> None:
    """兼容入口：清空能力覆盖；供测试或重置场景使用。"""
    from app.core.integrations.openai.video_capabilities import clear_openai_video_capability_overrides
    from app.core.integrations.volcengine.video_capabilities import clear_volcengine_video_capability_overrides

    if provider is None:
        clear_openai_video_capability_overrides()
        clear_volcengine_video_capability_overrides()
        return
    if provider == "openai":
        clear_openai_video_capability_overrides()
        return
    clear_volcengine_video_capability_overrides()


def resolve_video_capability(*, provider: ProviderKey, model: str | None) -> VideoModelCapability:
    if provider == "openai":
        from app.core.integrations.openai.video_capabilities import resolve_openai_video_capability

        return resolve_openai_video_capability(model)
    from app.core.integrations.volcengine.video_capabilities import resolve_volcengine_video_capability

    return resolve_volcengine_video_capability(model)


def infer_ratio_from_size(size: str | None) -> str | None:
    if not size:
        return None
    value = size.strip().lower()
    if not value:
        return None
    if ":" in value:
        return value if value in ALLOWED_RATIOS else None
    if "x" not in value:
        return None
    left, right = value.split("x", 1)
    if not left.isdigit() or not right.isdigit():
        return None
    width = int(left)
    height = int(right)
    if width <= 0 or height <= 0:
        return None
    factor = gcd(width, height)
    ratio = f"{width // factor}:{height // factor}"
    return ratio if ratio in ALLOWED_RATIOS else None


def resolve_effective_ratio(input_: VideoGenerationInput) -> str | None:
    if input_.ratio:
        return input_.ratio
    return infer_ratio_from_size(input_.size)


def validate_video_options(
    *,
    provider: ProviderKey,
    model: str | None,
    input_: VideoGenerationInput,
) -> None:
    cap = resolve_video_capability(provider=provider, model=model)
    inferred_ratio = infer_ratio_from_size(input_.size)
    if input_.ratio and cap.allowed_ratios is not None and input_.ratio not in cap.allowed_ratios:
        raise ValueError(
            f"Unsupported ratio for provider={provider} model={model or '<default>'}: {input_.ratio}. "
            f"Allowed: {sorted(cap.allowed_ratios)}"
        )
    if input_.ratio and inferred_ratio and inferred_ratio != input_.ratio:
        raise ValueError(
            f"ratio conflicts with size: ratio={input_.ratio}, size={input_.size} (implies {inferred_ratio})"
        )
    if input_.size and cap.allowed_sizes is not None and input_.size not in cap.allowed_sizes:
        raise ValueError(
            f"Unsupported size for provider={provider} model={model or '<default>'}: {input_.size}. "
            f"Allowed: {sorted(cap.allowed_sizes)}"
        )
    if input_.seconds is not None:
        if cap.min_seconds is not None and input_.seconds < cap.min_seconds:
            raise ValueError(f"seconds must be >= {cap.min_seconds}")
        if cap.max_seconds is not None and input_.seconds > cap.max_seconds:
            raise ValueError(f"seconds must be <= {cap.max_seconds}")
    if input_.seed is not None and not cap.supports_seed:
        raise ValueError(f"seed is not supported by provider={provider} model={model or '<default>'}")
    if input_.watermark is not None and not cap.supports_watermark:
        raise ValueError(f"watermark is not supported by provider={provider} model={model or '<default>'}")
