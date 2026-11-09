"""
Benchmark and Evaluation Suite for Relight Studio Engine v5 vs Engine v4
"""
import os
import sys
import time
import json
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from engine.relighter_v5 import (
    prepare_scene as prep_v5, relight_scene as relight_v5,
    PRESETS as PRESETS_V5, Params as ParamsV5, Light as LightV5,
    compute_metrics, make_board as make_board_v5, make_diagnostic_board,
    sweep_wheel, sweep_elevation, sweep_materials, load_srgb, save_srgb, _fonts
)
from engine.relighter_v4 import (
    prepare_scene as prep_v4, relight_scene as relight_v4,
    PRESETS as PRESETS_V4, Params as ParamsV4
)

test_photos = [
    ("nike_sneaker", "demo_output/nike_sample.jpg", "satin", "warm_key_cool_rim"),
    ("classical_statue", "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/.user_uploaded/media_1794143824741_478ce89a.jpg", "skin_marble", "rembrandt"),
    ("alpine_landscape", "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/.user_uploaded/media_1794164643841_a40aaeee.jpg", "matte", "golden_hour_back"),
    ("sailboat_sea", "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/.user_uploaded/media_1794166447021_87847076.jpg", "glossy", "warm_key_cool_rim"),
    ("landscape_sun", "demo_output/01_original.png", "matte", "warm_key_cool_rim"),
]

os.makedirs("demo_output/v5_evaluation", exist_ok=True)
benchmark_records = []

print("=== Starting Relight Studio Engine v5 Comprehensive Benchmark ===")

for name, img_path, mat, preset_name in test_photos:
    if not os.path.exists(img_path):
        print(f"Skipping {name}: file not found {img_path}")
        continue

    print(f"\nProcessing {name} (Material: {mat}, Preset: {preset_name})...")
    srgb = load_srgb(img_path)
    H, W = srgb.shape[:2]

    # 1. Run Engine v5
    t0 = time.perf_counter()
    p5 = ParamsV5(lam=0.7, strength=1.0, auto_delight=True)
    sc5 = prep_v5(srgb, p5)
    lights5 = PRESETS_V5[preset_name]
    res5 = relight_v5(sc5, lights5, p=p5)
    t_v5 = time.perf_counter() - t0
    m5 = compute_metrics(srgb, res5, p5)

    # 2. Run Engine v4 baseline
    t0_v4 = time.perf_counter()
    p4 = ParamsV4(lam=0.7, strength=1.0)
    sc4 = prep_v4(srgb, p4)
    lights4 = PRESETS_V4[preset_name]
    res4 = relight_v4(sc4, lights4, p=p4)
    t_v4 = time.perf_counter() - t0_v4
    m4 = compute_metrics(srgb, res4, p4)

    # Save outputs
    out_v5_path = f"demo_output/v5_evaluation/{name}_v5_relit.png"
    board_v5_path = f"demo_output/v5_evaluation/{name}_v5_board.png"
    diag_v5_path = f"demo_output/v5_evaluation/{name}_v5_diagnostics.png"
    save_srgb(out_v5_path, res5.relit_srgb)
    make_board_v5(srgb, res5, m5, f"{name} Engine v5 ({preset_name})", board_v5_path)
    make_diagnostic_board(sc5, res5, diag_v5_path)

    # Sweeps for Nike and Statue
    if name == "nike_sneaker":
        sweep_wheel(sc5, p5, "demo_output/v5_evaluation/nike_v5_sweep_wheel.png")
        sweep_elevation(sc5, p5, "demo_output/v5_evaluation/nike_v5_sweep_elevation.png")
        sweep_materials(sc5, p5, "demo_output/v5_evaluation/nike_v5_sweep_materials.png")

    if name == "classical_statue":
        sweep_wheel(sc5, p5, "demo_output/v5_evaluation/statue_v5_sweep_wheel.png")
        sweep_elevation(sc5, p5, "demo_output/v5_evaluation/statue_v5_sweep_elevation.png")

    # Record benchmark
    record = {
        "name": name,
        "resolution": f"{W}x{H}",
        "preset": preset_name,
        "material": mat,
        "L_orig_estimated": [float(x) for x in sc5.orig_light.pos],
        "v5": {
            "time_ms": round(t_v5 * 1000, 1),
            "detail_lock_err": round(m5["detail_lock_error_log"], 4),
            "detail_ratio_med": round(m5["detail_ratio_median"], 4),
            "banding_gain": round(m5["banding_gain"], 4),
            "chroma_shift_p95": round(m5["chroma_shift_p95_in_subject"], 2),
            "finite": m5["finite"],
        },
        "v4": {
            "time_ms": round(t_v4 * 1000, 1),
            "detail_lock_err": round(m4["detail_lock_error_log"], 4),
            "detail_ratio_med": round(m4["detail_ratio_median"], 4),
            "banding_gain": round(m4["banding_gain"], 4),
            "chroma_shift_p95": round(m4["chroma_shift_p95_in_subject"], 2),
        }
    }
    benchmark_records.append(record)
    print(f"[{name}] v5 Lock Err: {m5['detail_lock_error_log']:.4f} (v4: {m4['detail_lock_error_log']:.4f})")
    print(f"[{name}] v5 Banding Gain: {m5['banding_gain']:.4f} (v4: {m4['banding_gain']:.4f})")
    print(f"[{name}] Estimated L_orig: {record['L_orig_estimated']}")

with open("demo_output/v5_evaluation/benchmark_summary.json", "w") as f:
    json.dump(benchmark_records, f, indent=2)

# Build a Master Head-to-Head Comparison Sheet between v4 and v5
f1, f2 = _fonts()
h2h_rows = []
for r in benchmark_records:
    name = r["name"]
    im_orig = load_srgb(f"demo_output/nike_sample.jpg" if name == "nike_sneaker" else
                        f"/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/.user_uploaded/media_1794143824741_478ce89a.jpg" if name == "classical_statue" else
                        "demo_output/01_original.png")
    im_v4 = load_srgb(f"demo_output/v4_nike_warm_key.png" if name == "nike_sneaker" else f"demo_output/v4_statue_relit.png" if name == "classical_statue" else f"demo_output/v5_evaluation/{name}_v5_relit.png")
    im_v5 = load_srgb(f"demo_output/v5_evaluation/{name}_v5_relit.png")
    h2h_rows.append((name.replace("_", " ").title(), im_orig, im_v4, im_v5))

thumb_w = 420
thumb_h = 240
canvas_h2h = Image.new("RGB", (thumb_w * 3, len(h2h_rows) * (thumb_h + 30) + 50), (20, 20, 22))
draw_h2h = ImageDraw.Draw(canvas_h2h)
draw_h2h.text((15, 12), "ENGINE v4 VS ENGINE v5 (MASTER PBR) HEAD-TO-HEAD COMPARISON", fill=(255, 255, 255), font=f1)

for idx, (title, orig_img, v4_img, v5_img) in enumerate(h2h_rows):
    y_base = 45 + idx * (thumb_h + 30)
    for col_idx, (col_title, img_data) in enumerate([("Original Photo", orig_img), ("Engine v4", v4_img), ("Engine v5 (Master PBR)", v5_img)]):
        x0 = col_idx * thumb_w
        t = cv2.resize(np.clip(img_data, 0, 1), (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
        canvas_h2h.paste(Image.fromarray((t * 255).astype(np.uint8)), (x0, y_base + 20))
        draw_h2h.text((x0 + 10, y_base + 2), f"{title} — {col_title}", fill=(210, 210, 215), font=f2)

canvas_h2h.save("demo_output/v5_evaluation/head_to_head_master_v4_vs_v5.png")
print("\n=== Benchmark completed successfully! All outputs generated ===")

