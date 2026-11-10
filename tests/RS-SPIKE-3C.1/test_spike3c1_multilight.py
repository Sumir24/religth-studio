"""
RELIGHT STUDIO — RS-SPIKE-3C.1: MULTI-LIGHT ARCHITECTURE REGRESSION SUITE
==========================================================================
Automated verification suite for multi-light scene architecture and additive transport:
  1. Multi-light scene state manipulation, validation invariants & undo/redo
  2. Legacy scene schema migration (v3.0.0 -> v3.1.0)
  3. Additive illumination linearity & superposition (2.000000x identical lights)
  4. Strict shadow independence on Metal GPU (exact 0.0000000000 bitwise mutation)
  5. Per-light shadow toggle validation
  6. CPU-to-Metal parity across 1, 2, 3, and 4 lights (Soft IoU >= 0.93, SDE <= 1.0px, MAE <= 0.001)
  7. Multi-light photographic fidelity on real plate (Foreground DCI >= 0.8800)
  8. Extreme exposure gamut safety and finite float invariant
"""

import math
import copy
import numpy as np
import pytest
from PIL import Image

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, RenderSettingsData, ProxyType, ReceiverType,
    EnergyConvention, RenderQuality, SceneStateManager
)
from studio3a.renderer import RenderBackend as CPURenderBackend
from studio3a.reconstruction import compute_DCI
from metal2.renderer import MetalRenderBackend
from metal2.run_benchmarks import generate_scene_fixture
from metal2.shadow_evaluation import compute_soft_iou, compute_continuous_sde


# ===========================================================================
# 1. SCENE STATE MODEL & MANIPULATION INVARIANTS
# ===========================================================================

def test_multilight_scene_bounds_and_invariants():
    """Verifies that StudioScene enforces 1 <= lights <= 8 and unique IDs."""
    scene = StudioScene()
    assert len(scene.lights) == 1
    assert scene.active_light_id == scene.lights[0].id

    # Adding up to 8 lights
    for _ in range(7):
        scene.add_light()
    assert len(scene.lights) == 8

    # Attempting to add 9th light raises ValueError
    with pytest.raises(ValueError, match="Maximum number of lights"):
        scene.add_light()

    # Attempting to delete lights down to 1
    for _ in range(7):
        scene.remove_light(scene.lights[-1].id)
    assert len(scene.lights) == 1

    # Attempting to delete the last remaining light raises ValueError
    with pytest.raises(ValueError, match="Cannot remove the last remaining light"):
        scene.remove_light(scene.lights[0].id)


def test_multilight_undo_redo_stack():
    """Verifies that multi-light operations record atomic snapshots in SceneStateManager."""
    sm = SceneStateManager(StudioScene())
    assert len(sm.current_scene.lights) == 1

    # Action 1: Add light
    sm.current_scene.add_light()
    sm.push_state(sm.current_scene)
    assert len(sm.current_scene.lights) == 2

    # Action 2: Duplicate light
    l2_id = sm.current_scene.lights[1].id
    sm.current_scene.duplicate_light(l2_id)
    sm.push_state(sm.current_scene)
    assert len(sm.current_scene.lights) == 3

    # Undo Action 2
    assert sm.undo()
    assert len(sm.current_scene.lights) == 2

    # Undo Action 1
    assert sm.undo()
    assert len(sm.current_scene.lights) == 1

    # Redo Action 1
    assert sm.redo()
    assert len(sm.current_scene.lights) == 2

    # Redo Action 2
    assert sm.redo()
    assert len(sm.current_scene.lights) == 3


def test_legacy_v3_schema_migration():
    """Verifies that legacy scenes lacking cast_shadows or stable IDs migrate cleanly."""
    legacy_json = '''
    {
      "metadata": {"version": "3.0.0", "name": "Legacy Scene"},
      "camera": {"width": 384, "height": 256},
      "lights": [
        {
          "position": [1.0, 1.5, 1.0],
          "intensity": 1.5
        }
      ]
    }
    '''
    scene = StudioScene.from_json(legacy_json)
    assert scene.metadata.version in ("3.1.0", "3.2.0")
    assert len(scene.lights) == 1
    assert scene.lights[0].cast_shadows is True
    assert scene.lights[0].id is not None
    assert scene.active_light_id == scene.lights[0].id


# ===========================================================================
# 2. RADIOMETRIC LINEARITY & SUPERPOSITION
# ===========================================================================

def test_multilight_additive_linearity_and_superposition():
    """Verifies that 2 identical lights double unshadowed and illuminated irradiance."""
    scene1, img, depth, norm, fg, rec, _ = generate_scene_fixture("cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE)
    metal_b = MetalRenderBackend()

    r1 = metal_b.render(scene1, img, depth, norm, fg, quality=RenderQuality.PREVIEW)

    scene2 = StudioScene.from_json(scene1.to_json())
    l2 = scene2.add_light()
    l2.position = list(scene2.lights[0].position)
    l2.rotation_deg = list(scene2.lights[0].rotation_deg)
    l2.width = scene2.lights[0].width
    l2.height = scene2.lights[0].height
    l2.intensity = scene2.lights[0].intensity
    l2.color_rgb = list(scene2.lights[0].color_rgb)
    l2.temperature_kelvin = scene2.lights[0].temperature_kelvin
    l2.energy_convention = scene2.lights[0].energy_convention

    r2 = metal_b.render(scene2, img, depth, norm, fg, quality=RenderQuality.PREVIEW)

    ratio = np.mean(r2["direct_irradiance"][fg] / np.maximum(r1["direct_irradiance"][fg], 1e-6))
    assert math.isclose(ratio, 2.0, rel_tol=1e-4), f"Superposition ratio was {ratio:.6f}, expected 2.000000"


def test_multilight_shadow_independence_zero_mutation():
    """Verifies that disabling Light 2 leaves Light 1 completely untouched (0.0000000000 diff)."""
    scene1, img, depth, norm, fg, rec, _ = generate_scene_fixture("cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE)
    metal_b = MetalRenderBackend()

    r1 = metal_b.render(scene1, img, depth, norm, fg, quality=RenderQuality.FINAL)

    scene2 = StudioScene.from_json(scene1.to_json())
    l2 = scene2.add_light()
    l2.position = [-1.5, 1.2, 1.0]
    l2.rotation_deg = [-25.0, -35.0, 0.0]
    l2.intensity = 1.0

    # Disable Light 2
    scene2.toggle_light(l2.id, enabled=False)
    r2_dis = metal_b.render(scene2, img, depth, norm, fg, quality=RenderQuality.FINAL)

    diff_relit = float(np.max(np.abs(r1["relit_srgb"] - r2_dis["relit_srgb"])))
    diff_vis = float(np.max(np.abs(r1["direct_visibility"] - r2_dis["direct_visibility"])))

    assert diff_relit == 0.0, f"Shadow independence violated! Relit diff: {diff_relit:.10e}"
    assert diff_vis == 0.0, f"Shadow independence violated! Vis diff: {diff_vis:.10e}"


def test_per_light_cast_shadow_toggle():
    """Verifies that disabling cast_shadows on Light 2 maintains its irradiance without casting shadows."""
    scene, img, depth, norm, fg, rec, _ = generate_scene_fixture("cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE)
    metal_b = MetalRenderBackend()

    l2 = scene.add_light()
    l2.position = [-1.2, 1.5, 1.0]
    l2.intensity = 1.0
    l2.cast_shadows = True

    r_shadow = metal_b.render(scene, img, depth, norm, fg, quality=RenderQuality.PREVIEW)

    # Disable shadows on Light 2
    scene.toggle_light_shadows(l2.id, cast_shadows=False)
    r_noshadow = metal_b.render(scene, img, depth, norm, fg, quality=RenderQuality.PREVIEW)

    # Irradiance on unshadowed foreground must remain identical
    irr_diff = float(np.max(np.abs(r_shadow["direct_irradiance"][fg] - r_noshadow["direct_irradiance"][fg])))
    assert irr_diff < 1e-4

    # Visibility on receiver should be higher when light 2 does not cast shadows
    mean_vis_shadow = float(np.mean(r_shadow["direct_visibility"][rec]))
    mean_vis_noshadow = float(np.mean(r_noshadow["direct_visibility"][rec]))
    assert mean_vis_noshadow > mean_vis_shadow


# ===========================================================================
# 3. CPU-TO-METAL PARITY ACROSS 1, 2, 3, AND 4 LIGHTS
# ===========================================================================

@pytest.mark.parametrize("num_lights", [1, 2, 3, 4])
def test_cpu_metal_multilight_parity(num_lights: int):
    """Verifies that Metal GPU matches CPU reference across 1, 2, 3, and 4 lights."""
    scene, img, depth, norm, fg, rec, _ = generate_scene_fixture("cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE)
    scene.render_settings.final_samples = 25

    lights_def = [
        ("Fill", [-1.5, 1.2, 1.0], [-25.0, -35.0, 0.0], 0.6, 3200.0),
        ("Rim", [0.0, 2.2, -1.8], [45.0, 180.0, 0.0], 1.2, 6500.0),
        ("Top", [0.0, 2.8, 0.0], [-90.0, 0.0, 0.0], 0.5, 5000.0)
    ]
    for i in range(num_lights - 1):
        name, pos, rot, intensity, cct = lights_def[i]
        l = scene.add_light()
        l.name = name
        l.position = pos
        l.rotation_deg = rot
        l.intensity = intensity
        l.temperature_kelvin = cct

    cpu_b = CPURenderBackend()
    metal_b = MetalRenderBackend()

    r_cpu = cpu_b.render(scene, img, depth, norm, fg, quality=RenderQuality.FINAL)
    r_gpu = metal_b.render(scene, img, depth, norm, fg, quality=RenderQuality.FINAL)

    soft_iou = compute_soft_iou(r_gpu["direct_visibility"], r_cpu["direct_visibility"], rec)
    sde = compute_continuous_sde(r_gpu["direct_visibility"], r_cpu["direct_visibility"], rec)
    mae_irr = float(np.mean(np.abs(r_gpu["direct_irradiance"][fg] - r_cpu["direct_irradiance"][fg])))

    assert soft_iou >= 0.93, f"Soft IoU {soft_iou:.4f} failed gate >= 0.93 for {num_lights} lights"
    assert sde <= 1.0, f"SDE {sde:.4f} px failed gate <= 1.0 px for {num_lights} lights"
    assert mae_irr <= 0.001, f"Irradiance MAE {mae_irr:.6f} failed gate <= 0.001 for {num_lights} lights"


# ===========================================================================
# 4. PHOTOGRAPHIC FIDELITY & EXTREME GAMUT BOUNDS
# ===========================================================================

def test_multilight_photographic_fidelity_on_nike_plate():
    """Verifies that 3-point studio lighting on Nike plate achieves DCI_fg >= 0.8800 and 0.0 mutation."""
    img_pil = Image.open("demo_output/nike_sample.jpg").convert("RGB")
    img_np = np.array(img_pil, dtype=np.float32) / 255.0
    H, W = img_np.shape[:2]

    depth = np.array(Image.open("demo_output/nike_test/depth.png").convert("L"), dtype=np.float32) / 255.0
    raw_norm = np.array(Image.open("demo_output/nike_test/normals.png").convert("RGB"), dtype=np.float32) / 255.0 * 2.0 - 1.0
    norm = raw_norm / np.clip(np.linalg.norm(raw_norm, axis=2, keepdims=True), 1e-4, None)

    gray = np.mean(img_np, axis=-1)
    fg_mask = gray < 0.92

    scene = StudioScene()
    scene.camera = CameraData(width=W, height=H)
    scene.lights[0].position = [1.2, 1.8, 1.5]
    scene.lights[0].intensity = 1.4

    l_fill = scene.add_light()
    l_fill.position = [-1.5, 1.2, 1.0]
    l_fill.intensity = 0.6
    l_fill.temperature_kelvin = 3200.0

    l_rim = scene.add_light()
    l_rim.position = [0.0, 2.0, -1.5]
    l_rim.intensity = 1.2
    l_rim.temperature_kelvin = 6500.0

    prot_mask = np.zeros((H, W), dtype=bool)
    prot_mask[:, :int(W * 0.4)] = True

    metal_b = MetalRenderBackend()
    res = metal_b.render(scene, img_np, depth, norm, fg_mask, quality=RenderQuality.FINAL, protected_mask=prot_mask)

    dci_fg = compute_DCI(img_np, res["relit_srgb"], mask=fg_mask)
    dci_whole = compute_DCI(img_np, res["relit_srgb"])
    prot_diff = float(np.max(np.abs(res["relit_srgb"][prot_mask] - img_np[prot_mask])))

    assert dci_fg >= 0.8800, f"Foreground DCI too low: {dci_fg:.4f}"
    assert dci_whole >= 0.8800, f"Whole image DCI too low: {dci_whole:.4f}"
    assert prot_diff == 0.0, f"Protected mask mutated: {prot_diff:.10e}"


def test_extreme_exposure_gamut_safety():
    """Verifies that 4 extreme lights + 5.0 exposure remain strictly finite and within [0, 1]."""
    scene, img, depth, norm, fg, rec, _ = generate_scene_fixture("cat1_perfume_box", ProxyType.OBB, ReceiverType.PLANE)
    scene.render_settings.exposure = 5.0
    for _ in range(3):
        li = scene.add_light()
        li.intensity = 10.0
    scene.lights[0].intensity = 10.0

    metal_b = MetalRenderBackend()
    res = metal_b.render(scene, img, depth, norm, fg, quality=RenderQuality.PREVIEW)
    relit = res["relit_srgb"]

    assert np.all(np.isfinite(relit)), "Non-finite numbers found in relit output!"
    assert np.min(relit) >= 0.0, f"Under-gamut pixel found: {np.min(relit)}"
    assert np.max(relit) <= 1.0, f"Over-gamut pixel found: {np.max(relit)}"
