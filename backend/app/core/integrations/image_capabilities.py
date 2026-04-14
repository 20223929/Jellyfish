"""图片生成能力约束与参数校验辅助。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.contracts.image_generation import ImageGenerationInput
from app.core.contracts.provider import ProviderKey


@dataclass(frozen=True, slots=True)
class ImageModelCapability:
    """供应商/模型图片能力约束。"""

    supports_seed: bool = True
    supports_watermark: bool = True
    allowed_sizes: set[str] | None = None
    min_n: int | None = 1
    max_n: int | None = 10


def register_image_model_capability(
    *,
    provider: ProviderKey,
    model_prefix: str,
    capability: ImageModelCapability,
) -> None:
    """兼容入口：注册模型能力覆盖（按前缀匹配，大小写不敏感）。"""
    if provider == "openai":
        from app.core.integrations.openai.image_capabilities import register_openai_image_capability

        register_openai_image_capability(model_prefix=model_prefix, capability=capability)
        return
    from app.core.integrations.volcengine.image_capabilities import register_volcengine_image_capability

    register_volcengine_image_capability(model_prefix=model_prefix, capability=capability)


def clear_image_model_capability_overrides(*, provider: ProviderKey | None = None) -> None:
    """兼容入口：清空能力覆盖；供测试或重置场景使用。"""
    from app.core.integrations.openai.image_capabilities import clear_openai_image_capability_overrides
    from app.core.integrations.volcengine.image_capabilities import clear_volcengine_image_capability_overrides

    if provider is None:
        clear_openai_image_capability_overrides()
        clear_volcengine_image_capability_overrides()
        return
    if provider == "openai":
        clear_openai_image_capability_overrides()
        return
    clear_volcengine_image_capability_overrides()


def resolve_image_capability(*, provider: ProviderKey, model: str | None) -> ImageModelCapability:
    if provider == "openai":
        from app.core.integrations.openai.image_capabilities import resolve_openai_image_capability

        return resolve_openai_image_capability(model)
    from app.core.integrations.volcengine.image_capabilities import resolve_volcengine_image_capability

    return resolve_volcengine_image_capability(model)


def validate_image_options(
    *,
    provider: ProviderKey,
    model: str | None,
    input_: ImageGenerationInput,
) -> None:
    cap = resolve_image_capability(provider=provider, model=model)
    if input_.size and cap.allowed_sizes is not None and input_.size not in cap.allowed_sizes:
        raise ValueError(
            f"Unsupported size for provider={provider} model={model or '<default>'}: {input_.size}. "
            f"Allowed: {sorted(cap.allowed_sizes)}"
        )
    if cap.min_n is not None and input_.n < cap.min_n:
        raise ValueError(f"n must be >= {cap.min_n}")
    if cap.max_n is not None and input_.n > cap.max_n:
        raise ValueError(f"n must be <= {cap.max_n}")
    if input_.seed is not None and not cap.supports_seed:
        raise ValueError(f"seed is not supported by provider={provider} model={model or '<default>'}")
    if input_.watermark is not None and not cap.supports_watermark:
        raise ValueError(f"watermark is not supported by provider={provider} model={model or '<default>'}")
