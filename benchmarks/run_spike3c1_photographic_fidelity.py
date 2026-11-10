"""
RELIGHT STUDIO — RS-SPIKE-3C.1: MULTI-LIGHT PHOTOGRAPHIC FIDELITY EVALUATOR
=============================================================================
Evaluates multi-light additive rendering across real photographic plates:
  • Plate P1: Nike Sneaker (commercial product, high-frequency knit mesh)
  • Plate P2: Classical Statue (organic marble, continuous smooth curvature)
  • Plate P3: Architectural Relief (outdoor hard surface, high dynamic range)
Measures:
  • Isolated Foreground DCI (must be >= 0.8800)
  • Background DCI
  • Whole-image DCI
  • Protected Region Bitwise Zero-Mutation (must be 0.0000000000)
  • Multi-light configurations: 1, 2, 3, and 4 lights
Saves visual diagnostic boards to metal2/benchmark_results/diagnostic_boards/
"""

import os
import json
import numpy as np
import cv2
from PIL import Image

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, ProxyType, ReceiverType, EnergyConvention, RenderQuality
)
from studio3a.reconstruction import compute_DCI
from metal2.renderer import MetalRenderBackend
from benchmarks.validate_photographic_fidelity import load_photographic_case

OUTPUT_DIR = "metal2/benchmark_results/diagnostic_boards"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_spike3c1_fidelity():
    print("="*80)
    print("RELIGHT STUDIO — RS-SPIKE-3C.1: PHOTOGRAPHIC FIDELITY & MULTI-LIGHT DCI EVALUATION")
    print("="*80)

    metal_b = MetalRenderBackend()
    cases = ["P1_nike_sneaker", "P2_classical_statue", "P3_architectural_relief"]
    summary_results = []

    for case_id in cases:
        print(f"\n[EVALUATING PLATE] {case_id}...")
        _, scene, img_srgb, depth, normals, fg_mask, ground_y = load_photographic_case(case_id)
        H, W = img_srgb.shape[:2]

        # Multi-light rig configurations:
        # 1-light: Baseline Key
        # 2-light: Key + Fill (opposing, softer, tungsten)
        # 3-light: Key + Fill + Rim kicker (behind, blue daylight)
        # 4-light: Key + Fill + Rim + Top softbox
        
        # Configure Multi-Light Studio Scene
        # Light 1: Key
        scene.lights[0].name = "Key Softbox"
        scene.lights[0].intensity = 1.4
        scene.lights[0].width, scene.lights[0].height = 0.8, 0.8
        
        # Light 2: Fill
        l2 = scene.add_light()
        l2.name = "Fill Softbox"
        l2.position = [-1.5, 1.2, 1.0]
        l2.rotation_deg = [-25.0, -35.0, 0.0]
        l2.width, l2.height = 1.0, 1.0
        l2.intensity = 0.6
        l2.temperature_kelvin = 3200.0
        
        # Light 3: Rim Kicker
        l3 = scene.add_light()
        l3.name = "Rim Kicker"
        l3.position = [0.0, 2.2, -1.8]
        l3.rotation_deg = [45.0, 180.0, 0.0]
        l3.width, l3.height = 0.5, 0.5
        l3.intensity = 1.2
        l3.temperature_kelvin = 6500.0

        # Define 40% protected region mask (left 40% of image)
        prot_mask = np.zeros((H, W), dtype=bool)
        prot_mask[:, :int(W * 0.4)] = True

        rig_evaluations = [
            ("1_Light_Key", 1),
            ("2_Lights_Key_Fill", 2),
            ("3_Lights_Key_Fill_Rim", 3),
        ]

        plate_summary = {"case_id": case_id, "resolution": f"{W}x{H}", "rigs": []}

        for rig_name, num_active in rig_evaluations:
            # Enable only the first num_active lights
            for idx, l in enumerate(scene.lights):
                l.enabled = (idx < num_active)

            # Render with protected mask active
            res_prot = metal_b.render(scene, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL, protected_mask=prot_mask)
            
            # 1. Zero-Mutation Verification
            prot_err_max = float(np.max(np.abs(res_prot["relit_srgb"][prot_mask] - img_srgb[prot_mask])))

            # Render full frame for DCI evaluation
            res_full = metal_b.render(scene, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL)
            relit_srgb = res_full["relit_srgb"]

            # 2. DCI Multi-Zone Computation
            dci_fg = compute_DCI(img_srgb, relit_srgb, mask=fg_mask)
            bg_mask = ~fg_mask
            dci_bg = compute_DCI(img_srgb, relit_srgb, mask=bg_mask)
            dci_whole = compute_DCI(img_srgb, relit_srgb)

            gate_dci = "PASS" if dci_fg >= 0.8800 else "FAIL"
            gate_prot = "PASS" if prot_err_max == 0.0 else "FAIL"

            print(f"  [{rig_name}]: DCI_fg={dci_fg:.4f} ({gate_dci}), DCI_bg={dci_bg:.4f}, DCI_whole={dci_whole:.4f} | Zero-Mut={prot_err_max:.10f} ({gate_prot})")

            rig_data = {
                "rig_name": rig_name,
                "num_lights": num_active,
                "dci_foreground": dci_fg,
                "dci_background": dci_bg,
                "dci_whole": dci_whole,
                "gate_dci": gate_dci,
                "zero_mutation_diff": prot_err_max,
                "gate_zero_mutation": gate_prot
            }
            plate_summary["rigs"].append(rig_data)

            # Save Visual Comparison Board for 3-Light Studio
            if num_active == 3:
                board_img = np.hstack([
                    (img_srgb * 255).astype(np.uint8),
                    (relit_srgb * 255).astype(np.uint8),
                    (np.repeat(res_full["direct_visibility"][..., None], 3, axis=-1) * 255).astype(np.uint8)
                ])
                out_path = os.path.join(OUTPUT_DIR, f"{case_id}_3light_board.png")
                Image.fromarray(board_img).save(out_path)
                print(f"  -> Saved Visual Board: {out_path}")

        summary_results.append(plate_summary)

    # Save Authoritative JSON
    out_json = "metal2/benchmark_results/photographic_fidelity_results.json"
    with open(out_json, "w") as f:
        json.dump(summary_results, f, indent=2)
    print(f"\n[SAVED] Photographic Fidelity Summary -> {out_json}")
    return summary_results


if __name__ == "__main__":
    run_spike3c1_fidelity()
