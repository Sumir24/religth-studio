"""
Investigates the Plate P1 Rough Metal DCI drop (0.7899) vs Polished Metal (0.9894).
Relight Studio — RS-SPIKE-3C.2.1 Audit
"""

import numpy as np
from benchmarks.validate_photographic_fidelity import load_photographic_case
from studio3a.material import MaterialData
from studio3a.reconstruction import compute_DCI, linear_to_luminance, srgb_to_linear
from metal2.renderer import MetalRenderBackend
from studio3a.scene import RenderQuality


def investigate_p1():
    backend = MetalRenderBackend()
    _, scene, img_srgb, depth, normals, fg_mask, ground_y = load_photographic_case("P1_nike_sneaker")
    H, W = img_srgb.shape[:2]

    # Setup standard 3 lights as in benchmark
    scene.lights[0].intensity = 1.5
    scene.lights[0].width, scene.lights[0].height = 0.8, 0.8
    l2 = scene.add_light()
    l2.position = [-1.4, 1.2, 1.0]
    l2.rotation_deg = [-20.0, -35.0, 0.0]
    l2.width, l2.height = 1.0, 1.0
    l2.intensity = 0.6
    l2.temperature_kelvin = 3200.0
    l3 = scene.add_light()
    l3.position = [0.0, 2.2, -1.8]
    l3.rotation_deg = [45.0, 180.0, 0.0]
    l3.width, l3.height = 0.5, 0.5
    l3.intensity = 1.2
    l3.temperature_kelvin = 6500.0

    print("Investigating Plate P1 Materials:")
    for name, mat in [
        ("Fabric", MaterialData.fabric()),
        ("Rough_Metal", MaterialData.rough_metal()),
        ("Polished_Metal", MaterialData.polished_metal())
    ]:
        scene.subject.material = mat
        res = backend.render(scene, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL)
        relit = res["relit_srgb"]
        spec = res["specular_radiance"]
        irr = res["direct_irradiance"]
        vis = res["direct_visibility"]

        dci_fg = compute_DCI(img_srgb, relit, mask=fg_mask)
        dci_whole = compute_DCI(img_srgb, relit)
        
        # Analyze luminance stats on foreground
        Y_orig_fg = linear_to_luminance(srgb_to_linear(img_srgb))[fg_mask]
        Y_relit_fg = linear_to_luminance(srgb_to_linear(relit))[fg_mask]
        spec_fg = linear_to_luminance(spec)[fg_mask]

        print(f"\nMaterial: {name} (roughness={mat.roughness}, metallic={mat.metallic})")
        print(f"  FG DCI: {dci_fg:.4f} | Whole DCI: {dci_whole:.4f}")
        print(f"  Y_orig FG: mean={np.mean(Y_orig_fg):.4f}, std={np.std(Y_orig_fg):.4f}, min={np.min(Y_orig_fg):.4f}, max={np.max(Y_orig_fg):.4f}")
        print(f"  Y_relit FG: mean={np.mean(Y_relit_fg):.4f}, std={np.std(Y_relit_fg):.4f}, min={np.min(Y_relit_fg):.4f}, max={np.max(Y_relit_fg):.4f}")
        print(f"  Spec FG: mean={np.mean(spec_fg):.4f}, max={np.max(spec_fg):.4f}")
        
        # Compute ratio Y_relit / Y_orig
        relit_ratio = Y_relit_fg / np.maximum(Y_orig_fg, 1e-4)
        print(f"  Relit Ratio (Y_relit / Y_orig): mean={np.mean(relit_ratio):.4f}, min={np.min(relit_ratio):.4f}, max={np.max(relit_ratio):.4f}")


if __name__ == "__main__":
    investigate_p1()
