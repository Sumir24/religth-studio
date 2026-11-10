"""
RS-SPIKE-3C.3 — Phase E: Photographic IBL Integration Tests
===========================================================
Evaluates Image-Based Lighting on authentic photographic plates:
  • P1: Nike Sneaker (commercial footwear product)
  • P2: Classical Statue (sculpted marble)
  • P3: Architectural Relief (weathered stone)
Verifies:
  • Foreground DCI >= 0.8800 for dielectric profiles
  • Protected-region mutation is strictly 0.0000000000
  • Specular environment highlights conform to material roughness
"""

import pytest
import numpy as np

from studio3a.scene import RenderQuality
from studio3a.material import MaterialData
from studio3a.environment import EnvironmentData
from studio3a.reconstruction import compute_DCI
from metal2.renderer import MetalRenderBackend
from benchmarks.validate_photographic_fidelity import load_photographic_case


@pytest.mark.parametrize("case_id,mat_factory", [
    ("P1_nike_sneaker", MaterialData.fabric),
    ("P2_classical_statue", MaterialData.marble),
    ("P3_architectural_relief", MaterialData.marble)
])
def test_photographic_plate_ibl_preservation(case_id, mat_factory):
    """Verifies DCI detail preservation and zero-mutation on protected regions under IBL."""
    _, scene, img_srgb, depth, normals, fg_mask, ground_y = load_photographic_case(case_id)
    H, W = img_srgb.shape[:2]

    # Setup environment
    scene.environment = EnvironmentData(
        enabled=True,
        intensity=0.8,
        rotation_deg=45.0,
        diffuse_weight=1.0,
        specular_weight=1.0
    )

    # 35% protected mask
    prot_mask = np.zeros((H, W), dtype=bool)
    prot_mask[:, :int(W * 0.35)] = True

    metal_renderer = MetalRenderBackend()

    # Assign plate-appropriate dielectric material
    scene.subject.material = mat_factory()
    scene.render_settings.enable_specular = True

    res = metal_renderer.render(
        scene, img_srgb, depth, normals, fg_mask,
        quality=RenderQuality.PREVIEW,
        protected_mask=prot_mask
    )

    relit = res["relit_srgb"]
    spec = res["specular_radiance"]

    # 1. Zero Mutation Guarantee
    prot_err = float(np.max(np.abs(relit[prot_mask] - img_srgb[prot_mask])))
    assert prot_err == 0.0, f"Protected region mutated on {case_id}: max error = {prot_err}"

    # 2. Foreground DCI
    dci_fg = compute_DCI(img_srgb, relit, mask=fg_mask)
    dci_whole = compute_DCI(img_srgb, relit)
    assert dci_fg >= 0.8800, f"Foreground DCI dropped below threshold on {case_id}: {dci_fg:.4f}"

    # 3. Specular highlights exist on reflective foreground
    peak_spec = float(np.max(spec[fg_mask]))
    assert peak_spec > 0.01, f"Peak specular highlight too dim on {case_id}: {peak_spec}"


def test_photographic_plate_polished_conductor_behavior():
    """Verifies that polished conductor metal reflects environment on photographic plate."""
    _, scene, img_srgb, depth, normals, fg_mask, ground_y = load_photographic_case("P1_nike_sneaker")
    H, W = img_srgb.shape[:2]

    scene.environment = EnvironmentData(
        enabled=True,
        intensity=1.5,
        rotation_deg=90.0,
        diffuse_weight=1.0,
        specular_weight=1.0
    )

    prot_mask = np.zeros((H, W), dtype=bool)
    prot_mask[:, :int(W * 0.35)] = True

    metal_renderer = MetalRenderBackend()
    scene.subject.material = MaterialData.polished_metal()

    res = metal_renderer.render(
        scene, img_srgb, depth, normals, fg_mask,
        quality=RenderQuality.PREVIEW,
        protected_mask=prot_mask
    )

    relit = res["relit_srgb"]
    spec = res["specular_radiance"]

    # Protected region zero mutation
    prot_err = float(np.max(np.abs(relit[prot_mask] - img_srgb[prot_mask])))
    assert prot_err == 0.0

    # Polished metal specular peak should be sharp and substantial
    peak_spec = float(np.max(spec[fg_mask]))
    assert peak_spec > 0.5, f"Polished metal peak specular too low: {peak_spec}"
