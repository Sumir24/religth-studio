"""
RELIGHT STUDIO — RS-PRODUCT-1.1
Unit & Integration Tests: Photographic Lighting Presets
"""

import pytest
import numpy as np
from relight_studio.controller import StudioAppController
from studio3a.scene import RenderQuality


@pytest.fixture
def controller():
    ctrl = StudioAppController()
    return ctrl


def test_lighting_presets_values(controller):
    """Verifies that each lighting preset sets physical 3D and radiometric values."""
    presets = ["key_softbox", "fill_softbox", "rim_strip", "top_light", "side_light"]
    
    for p in presets:
        lid = controller.apply_lighting_preset(p)
        light = controller.current_scene.get_light(lid)
        assert light is not None
        assert light.enabled is True
        assert light.cast_shadows is True
        assert light.width > 0.0
        assert light.height > 0.0
        assert light.intensity > 0.0
        assert 3000.0 <= light.temperature_kelvin <= 8000.0


def test_lighting_presets_photographic_differentiation(controller):
    """Verifies that applying different presets produces distinct photographic relighting results."""
    # Key light render
    controller.apply_lighting_preset("key_softbox")
    res_key = controller.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    img_key = res_key["relit_srgb"]

    # Rim light render
    controller.apply_lighting_preset("rim_strip")
    res_rim = controller.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    img_rim = res_rim["relit_srgb"]

    # They must not be identical
    abs_diff = np.mean(np.abs(img_key - img_rim))
    assert abs_diff > 0.01, f"Expected distinct relighting between key and rim, got diff={abs_diff}"


def test_lighting_preset_undo(controller):
    """Verifies undo reverts a preset change back to previous light state."""
    controller.apply_lighting_preset("key_softbox")
    light = controller.current_scene.get_light(controller.selected_object_id)
    key_intensity = light.intensity

    controller.apply_lighting_preset("rim_strip")
    light = controller.current_scene.get_light(controller.selected_object_id)
    assert light.intensity != key_intensity

    # Undo
    controller.undo()
    light = controller.current_scene.get_light(controller.selected_object_id)
    assert light.intensity == key_intensity
