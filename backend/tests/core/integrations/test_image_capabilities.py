"""图片能力映射单测。"""

from __future__ import annotations

import pytest

from app.core.contracts.image_generation import ImageGenerationInput
from app.core.integrations.image_capabilities import (
    ImageModelCapability,
    clear_image_model_capability_overrides,
    register_image_model_capability,
    resolve_image_capability,
    validate_image_options,
)


def test_resolve_image_capability_prefers_longest_prefix() -> None:
    clear_image_model_capability_overrides(provider="openai")
    register_image_model_capability(
        provider="openai",
        model_prefix="gpt-image",
        capability=ImageModelCapability(supports_seed=False),
    )
    register_image_model_capability(
        provider="openai",
        model_prefix="gpt-image-1.5",
        capability=ImageModelCapability(supports_seed=True, supports_watermark=False),
    )
    try:
        cap = resolve_image_capability(provider="openai", model="gpt-image-1.5-pro")
        assert cap.supports_seed is True
        assert cap.supports_watermark is False
    finally:
        clear_image_model_capability_overrides(provider="openai")


def test_validate_image_options_rejects_capability_mismatch() -> None:
    clear_image_model_capability_overrides(provider="volcengine")
    register_image_model_capability(
        provider="volcengine",
        model_prefix="seedream",
        capability=ImageModelCapability(supports_watermark=False),
    )
    try:
        inp = ImageGenerationInput(prompt="test", model="seedream-v3", watermark=True)
        with pytest.raises(ValueError) as exc_info:
            validate_image_options(provider="volcengine", model=inp.model, input_=inp)
        assert "watermark is not supported" in str(exc_info.value)
    finally:
        clear_image_model_capability_overrides(provider="volcengine")
