"""
RELIGHT STUDIO — RS-PRODUCT-1.2.1
==================================
Comprehensive Performance & 1080p Reproduction Benchmark Suite
Measures:
1. Preview (1024x576) across 1, 4, and 8 area lights (Host P50, P95, P99, FPS, GPU ms).
2. True 1080p (1920x1080) Final Quality (32 MC samples) across 1, 4, and 8 area lights.
3. True 1080p (1920x1080) Interactive Preview across 1, 4, and 8 area lights.
4. Direct comparison explaining why previous reports quoted 5.00ms (576x1024 single light).
"""

import os
import sys
import time
import json
import tempfile
import numpy as np
import cv2
from pathlib import Path

from studio3a.scene import StudioScene, AreaLightData, RenderQuality, ReceiverType
from relight_studio.controller import StudioAppController

OUT_FILE = Path("docs/RS-PRODUCT-1.2.1/performance_audit_results.json")
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)


def create_blank_test_controller(width: int, height: int) -> StudioAppController:
    img = np.zeros((height, width, 3), dtype=np.float32)
    depth = np.ones((height, width), dtype=np.float32) * 0.5
    normals = np.zeros((height, width, 3), dtype=np.float32)
    normals[..., 2] = -1.0
    fg = np.ones((height, width), dtype=bool)

    td = tempfile.mkdtemp()
    p_img = os.path.join(td, f"bench_{width}x{height}.png")
    cv2.imwrite(p_img, (img * 255).astype(np.uint8))

    ctrl = StudioAppController(sample_image_path=p_img, use_metal=True)
    ctrl.project.img_orig_srgb = img
    ctrl.project.depth_map = depth
    ctrl.project.normals_map = normals
    ctrl.project.fg_mask = fg
    ctrl.current_scene.camera.width = width
    ctrl.current_scene.camera.height = height
    return ctrl


def setup_lights(ctrl: StudioAppController, count: int):
    ctrl.current_scene.lights.clear()
    for k in range(count):
        ang = k * (2.0 * np.pi / count)
        ctrl.current_scene.add_light(AreaLightData(
            id=f"light_{k:02d}",
            name=f"Light {k:02d}",
            position=[float(1.5 * np.cos(ang)), 1.5, float(1.5 * np.sin(ang))],
            rotation_deg=[-30.0, float(np.degrees(ang) + 180.0), 0.0],
            width=0.5,
            height=0.5,
            intensity=1.0,
            temperature_kelvin=5500.0,
            cast_shadows=True,
            enabled=True
        ))


def benchmark_config(ctrl: StudioAppController, quality: RenderQuality, iterations: int = 30) -> dict:
    # Warmup
    for _ in range(5):
        ctrl.request_render(quality=quality, async_mode=False)

    host_times = []
    gpu_times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        res = ctrl.request_render(quality=quality, async_mode=False)
        dt = (time.perf_counter() - t0) * 1000.0
        host_times.append(dt)
        if "diagnostics" in res and "gpu_time_ms" in res["diagnostics"]:
            gpu_times.append(res["diagnostics"]["gpu_time_ms"])

    p50 = float(np.percentile(host_times, 50))
    p95 = float(np.percentile(host_times, 95))
    p99 = float(np.percentile(host_times, 99))
    t_min = float(np.min(host_times))
    t_max = float(np.max(host_times))
    t_mean = float(np.mean(host_times))
    gpu_avg = float(np.mean(gpu_times)) if gpu_times else 0.0

    return {
        "host_p50_ms": round(p50, 2),
        "host_p95_ms": round(p95, 2),
        "host_p99_ms": round(p99, 2),
        "host_min_ms": round(t_min, 2),
        "host_max_ms": round(t_max, 2),
        "host_mean_ms": round(t_mean, 2),
        "fps_p50": round(1000.0 / p50, 1),
        "gpu_avg_ms": round(gpu_avg, 2)
    }


def run_benchmarks():
    print("=" * 80)
    print("RELIGHT STUDIO — RS-PRODUCT-1.2.1 RIGOROUS PERFORMANCE BENCHMARK")
    print("=" * 80)

    results = {
        "system_info": {
            "chip": "Apple M5 (10 cores: 4 Super, 6 Efficiency)",
            "gpu": "10-core Apple M5 GPU, Metal 4",
            "memory": "16 GB Unified Memory",
            "os": "macOS 27.0 (Build 26A428)"
        },
        "preview_1024x576": {},
        "true_1080p_final": {},
        "true_1080p_preview": {},
        "reconciliation_nike_576x1024": {}
    }

    # 1. Preview Resolution (1024x576) across 1, 4, 8 lights
    print("\n[Phase 1] Preview Resolution (1024x576, 4 MC Samples)...")
    ctrl_prev = create_blank_test_controller(1024, 576)
    for n in [1, 4, 8]:
        setup_lights(ctrl_prev, n)
        b = benchmark_config(ctrl_prev, RenderQuality.PREVIEW, iterations=35)
        results["preview_1024x576"][f"{n}_lights"] = b
        print(f"  {n} Lights: P50={b['host_p50_ms']}ms ({b['fps_p50']} FPS) | P95={b['host_p95_ms']}ms | GPU={b['gpu_avg_ms']}ms")

    # 2. True 1080p (1920x1080) Final Quality (32 MC Samples)
    print("\n[Phase 2] True 1080p (1920x1080, 32 MC Samples)...")
    ctrl_1080 = create_blank_test_controller(1920, 1080)
    for n in [1, 4, 8]:
        setup_lights(ctrl_1080, n)
        b = benchmark_config(ctrl_1080, RenderQuality.FINAL, iterations=25)
        results["true_1080p_final"][f"{n}_lights"] = b
        print(f"  {n} Lights (1080p FINAL): P50={b['host_p50_ms']}ms ({b['fps_p50']} FPS) | P95={b['host_p95_ms']}ms | GPU={b['gpu_avg_ms']}ms")

    # 3. True 1080p (1920x1080) Preview Quality (4 MC Samples)
    print("\n[Phase 3] True 1080p (1920x1080, 4 MC Samples)...")
    for n in [1, 4, 8]:
        setup_lights(ctrl_1080, n)
        b = benchmark_config(ctrl_1080, RenderQuality.PREVIEW, iterations=30)
        results["true_1080p_preview"][f"{n}_lights"] = b
        print(f"  {n} Lights (1080p PREVIEW): P50={b['host_p50_ms']}ms ({b['fps_p50']} FPS) | P95={b['host_p95_ms']}ms | GPU={b['gpu_avg_ms']}ms")

    # 4. Reconciliation of previous RS-PRODUCT-1.2 benchmark claim (nike_sample.jpg, 576x1024)
    print("\n[Phase 4] Reconciling Previous 5.00ms Claim on nike_sample.jpg (576x1024)...")
    ctrl_nike = StudioAppController(sample_image_path="demo_output/nike_sample.jpg", use_metal=True)
    setup_lights(ctrl_nike, 1)
    b_nike = benchmark_config(ctrl_nike, RenderQuality.FINAL, iterations=30)
    results["reconciliation_nike_576x1024"]["1_light_final"] = b_nike
    print(f"  nike_sample (576x1024, 1 light): P50={b_nike['host_p50_ms']}ms ({b_nike['fps_p50']} FPS) | GPU={b_nike['gpu_avg_ms']}ms")

    with open(OUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    print("\nBenchmark results written to:", OUT_FILE)


if __name__ == "__main__":
    run_benchmarks()

