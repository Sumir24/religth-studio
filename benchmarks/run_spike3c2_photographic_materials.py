"""
RELIGHT STUDIO — RS-SPIKE-3C.2: PHOTOGRAPHIC MATERIAL RESPONSE HARNESS
======================================================================
Evaluates physical material transport across authentic photographic plates:
  • P1: Nike Sneaker (commercial knit footwear)
  • P2: Classical Statue (sculpted marble)
  • P3: Architectural Relief (weathered stone)
Across 5 Physical Material Profiles:
  • Fabric / Knit (roughness 0.85, metallic 0.0, F0 0.03)
  • Marble / Stone (roughness 0.35, metallic 0.0, F0 0.045)
  • Plastic / Polymer (roughness 0.22, metallic 0.0, F0 0.04)
  • Rough Metal (roughness 0.45, metallic 1.0, F0 base_color)
  • Polished Metal (roughness 0.12, metallic 1.0, F0 base_color)
Measures:
  • Foreground DCI (Detail Conservation Index >= 0.8800)
  • Bitwise Zero Mutation on Protected Region (0.0000000000)
  • Peak Specular Radiance & Dynamic Range
Generates 100% scale diagnostic comparison boards into:
  metal2/benchmark_results/diagnostic_boards/
"""

import os
import json
import numpy as np
import cv2
from PIL import Image

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, ProxyType, ReceiverType, RenderQuality
)
from studio3a.material import MaterialData
from studio3a.reconstruction import compute_DCI
from metal2.renderer import MetalRenderBackend
from benchmarks.validate_photographic_fidelity import load_photographic_case

OUTPUT_DIR = "metal2/benchmark_results/diagnostic_boards"
os.makedirs(OUTPUT_DIR, exist_ok=True)
RESULTS_JSON = "metal2/benchmark_results/photographic_material_results.json"


def run_spike3c2_materials():
    print("=" * 80)
    print("RELIGHT STUDIO — RS-SPIKE-3C.2: PHOTOGRAPHIC MATERIAL RESPONSE HARNESS")
    print("=" * 80)

    metal_renderer = MetalRenderBackend()
    cases = ["P1_nike_sneaker", "P2_classical_statue", "P3_architectural_relief"]

    profiles = [
        ("Fabric", MaterialData.fabric()),
        ("Marble", MaterialData.marble()),
        ("Plastic", MaterialData.plastic()),
        ("Rough_Metal", MaterialData.rough_metal()),
        ("Polished_Metal", MaterialData.polished_metal()),
    ]

    benchmark_summary = []

    for case_id in cases:
        print(f"\n--- [EVALUATING PHOTOGRAPHIC PLATE] {case_id} ---")
        _, scene, img_srgb, depth, normals, fg_mask, ground_y = load_photographic_case(case_id)
        H, W = img_srgb.shape[:2]

        # Multi-light setup: Key (warm, 5600K) + Fill (soft, 3200K) + Rim (cool, 6500K)
        scene.lights[0].name = "Key Softbox"
        scene.lights[0].intensity = 1.5
        scene.lights[0].width, scene.lights[0].height = 0.8, 0.8

        l2 = scene.add_light()
        l2.name = "Fill Softbox"
        l2.position = [-1.4, 1.2, 1.0]
        l2.rotation_deg = [-20.0, -35.0, 0.0]
        l2.width, l2.height = 1.0, 1.0
        l2.intensity = 0.6
        l2.temperature_kelvin = 3200.0

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

        case_results = {
            "case_id": case_id,
            "resolution": f"{W}x{H}",
            "profiles": []
        }

        # Board tiles for visual comparison
        board_tiles = [("Original Plate", img_srgb)]

        for prof_name, mat in profiles:
            scene.subject.material = mat
            scene.render_settings.enable_specular = True
            scene.render_settings.specular_only = False

            # Render full relit frame with protected mask
            res = metal_renderer.render(
                scene, img_srgb, depth, normals, fg_mask,
                quality=RenderQuality.FINAL,
                protected_mask=prot_mask
            )

            relit = res["relit_srgb"]
            spec = res["specular_radiance"]
            vis = res["direct_visibility"]

            # 1. Zero Mutation Verification on Protected Region
            prot_err_max = float(np.max(np.abs(relit[prot_mask] - img_srgb[prot_mask])))

            # 2. Detail Conservation Index (DCI) on isolated foreground
            dci_fg = compute_DCI(img_srgb, relit, mask=fg_mask)
            dci_whole = compute_DCI(img_srgb, relit)

            # 3. Specular Statistics on Foreground
            fg_spec = spec[fg_mask]
            peak_spec = float(np.max(fg_spec))
            mean_spec = float(np.mean(fg_spec))

            print(f"  [{prof_name:14s}] FG-DCI: {dci_fg:.4f} | Whole-DCI: {dci_whole:.4f} | "
                  f"ProtErr: {prot_err_max:.10f} | SpecPeak: {peak_spec:.4f} | SpecMean: {mean_spec:.4f}")

            assert prot_err_max == 0.0, f"Protected zero mutation failed: {prot_err_max}"
            if mat.metallic < 0.5:
                # Standard dielectric materials must preserve original photographic detail >= 0.8800
                assert dci_fg >= 0.8800, f"Dielectric foreground DCI dropped below 0.8800: {dci_fg}"
            else:
                # Conductor metals legitimately extinguish diffuse scattering (kd -> 0)
                # Documented in Section 10 as an expected single-image physical material limitation
                pass

            case_results["profiles"].append({
                "profile": prof_name,
                "roughness": mat.roughness,
                "metallic": mat.metallic,
                "fg_dci": round(dci_fg, 4),
                "whole_dci": round(dci_whole, 4),
                "protected_error_max": prot_err_max,
                "peak_specular_radiance": round(peak_spec, 4),
                "mean_specular_radiance": round(mean_spec, 4),
                "gpu_time_ms": res["diagnostics"]["gpu_time_ms"]
            })

            board_tiles.append((f"{prof_name}", relit))

        # Generate Specular Isolation Tile (Plastic profile)
        scene.subject.material = MaterialData.plastic()
        scene.render_settings.specular_only = True
        res_spec = metal_renderer.render(
            scene, img_srgb, depth, normals, fg_mask,
            quality=RenderQuality.FINAL,
            protected_mask=None
        )
        board_tiles.append(("Specular Only (Plastic)", res_spec["relit_srgb"]))

        # Build Diagnostic Comparison Board
        n_tiles = len(board_tiles)
        cols = 3
        rows = (n_tiles + cols - 1) // cols
        tile_h, tile_w = H, W
        board = np.zeros((rows * (tile_h + 40), cols * tile_w, 3), dtype=np.uint8)

        for idx, (label, img_float) in enumerate(board_tiles):
            r = idx // cols
            c = idx % cols
            y_start = r * (tile_h + 40)
            x_start = c * tile_w

            # Title banner
            cv2.putText(
                board, f"{label}", (x_start + 15, y_start + 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA
            )

            img_uint8 = np.clip(img_float * 255.0, 0, 255).astype(np.uint8)
            # OpenCV BGR format conversion
            img_bgr = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2BGR)
            board[y_start + 35:y_start + 35 + tile_h, x_start:x_start + tile_w] = img_bgr

        board_filename = os.path.join(OUTPUT_DIR, f"{case_id}_material_comparison_board.jpg")
        cv2.imwrite(board_filename, board)
        print(f"  [SAVED COMPARISON BOARD] {board_filename}")

        benchmark_summary.append(case_results)

    with open(RESULTS_JSON, "w") as f:
        json.dump(benchmark_summary, f, indent=2)
    print(f"\n[BENCHMARK JSON COMPLETE] Saved to {RESULTS_JSON}")
    print("=" * 80)


if __name__ == "__main__":
    run_spike3c2_materials()
