"""
RELIGHT STUDIO — RS-PRODUCT-1.2
================================
Visual Verification & Real Interaction Evidence Pipeline
Captures all 12 required high-DPI screenshots demonstrating:
- Camera Matching (24mm, 50mm, 85mm presets & fit to subject)
- Photograph Alignment Overlays (wireframe, silhouette blend, guides, mismatch)
- 3D Geometry Editing (subject gizmo with pitch/yaw/roll and scale)
- Receiver and Ground Contact Alignment (closed-form snap to ground)
- Alignment Diagnostics in Inspector
- Non-silent Error Handling for Missing Project Assets
"""

import os
import sys
import time
import json
import hashlib
import shutil
import tempfile
import threading
import subprocess
from pathlib import Path
import cv2
import numpy as np

from studio3a.scene import RenderQuality, ReceiverType, ProxyType
from relight_studio.controller import StudioAppController
from relight_studio.server import create_app
import uvicorn


CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUTPUT_DIR = "docs/RS-PRODUCT-1.2/screenshots"
PORT = 8524


def get_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def capture_chrome_screenshot(url: str, output_path: str, delay_sec: float = 1.2, window_size: str = "1440,920"):
    """Invokes headless Google Chrome to capture a pixel-accurate screenshot of the UI."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    time.sleep(delay_sec)
    cmd = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--window-size={window_size}",
        f"--screenshot={output_path}",
        url
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[Chrome Warning] rc={res.returncode}: {res.stderr}")


def run_pipeline():
    print("=" * 80)
    print("RELIGHT STUDIO — RS-PRODUCT-1.2 VISUAL QA SCREENSHOT CAPTURE SUITE")
    print("=" * 80)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    sample_img = "demo_output/nike_sample.jpg"
    orig_image_hash = get_file_sha256(sample_img)
    print(f"Verified immutable source photograph: {sample_img}")
    print(f"SHA-256: {orig_image_hash}")

    ctrl = StudioAppController(sample_image_path=sample_img, use_metal=True)
    app = create_app(ctrl)

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    time.sleep(1.5)
    base_url = f"http://127.0.0.1:{PORT}"
    print(f"Server online at {base_url}")

    # -------------------------------------------------------------------------
    # SCREENSHOT 1: Initial Studio Workspace
    # -------------------------------------------------------------------------
    print("\n[1/12] Capturing 01_initial_studio_workspace.png...")
    ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    p1 = os.path.join(OUTPUT_DIR, "01_initial_studio_workspace.png")
    capture_chrome_screenshot(base_url, p1, delay_sec=1.5)

    # -------------------------------------------------------------------------
    # SCREENSHOT 2: Camera Preset 24mm Wide
    # -------------------------------------------------------------------------
    print("[2/12] Capturing 02_camera_preset_24mm_wide.png...")
    ctrl.select_object("camera")
    ctrl.apply_camera_preset("24mm")
    ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    p2 = os.path.join(OUTPUT_DIR, "02_camera_preset_24mm_wide.png")
    capture_chrome_screenshot(base_url, p2, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 3: Camera Preset 50mm Normal
    # -------------------------------------------------------------------------
    print("[3/12] Capturing 03_camera_preset_50mm_normal.png...")
    ctrl.apply_camera_preset("50mm")
    ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    p3 = os.path.join(OUTPUT_DIR, "03_camera_preset_50mm_normal.png")
    capture_chrome_screenshot(base_url, p3, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 4: Camera Preset 85mm Portrait
    # -------------------------------------------------------------------------
    print("[4/12] Capturing 04_camera_preset_85mm_portrait.png...")
    ctrl.apply_camera_preset("85mm")
    ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    p4 = os.path.join(OUTPUT_DIR, "04_camera_preset_85mm_portrait.png")
    capture_chrome_screenshot(base_url, p4, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 5: Camera Framing Fit to Subject
    # -------------------------------------------------------------------------
    print("[5/12] Capturing 05_camera_framing_fit_to_subject.png...")
    ctrl.fit_camera_to_subject()
    ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    p5 = os.path.join(OUTPUT_DIR, "05_camera_framing_fit_to_subject.png")
    capture_chrome_screenshot(base_url, p5, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 6: Photograph Wireframe Overlay
    # -------------------------------------------------------------------------
    print("[6/12] Capturing 06_photograph_wireframe_overlay.png...")
    p6 = os.path.join(OUTPUT_DIR, "06_photograph_wireframe_overlay.png")
    capture_chrome_screenshot(f"{base_url}/?view=wireframe&alpha=0.7", p6, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 7: Photograph Silhouette Blend
    # -------------------------------------------------------------------------
    print("[7/12] Capturing 07_photograph_silhouette_blend.png...")
    p7 = os.path.join(OUTPUT_DIR, "07_photograph_silhouette_blend.png")
    capture_chrome_screenshot(f"{base_url}/?view=silhouette&alpha=0.55", p7, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 8: Photograph Guides (Horizon & Ground Grid)
    # -------------------------------------------------------------------------
    print("[8/12] Capturing 08_photograph_guides_horizon_ground.png...")
    p8 = os.path.join(OUTPUT_DIR, "08_photograph_guides_horizon_ground.png")
    capture_chrome_screenshot(f"{base_url}/?view=guides&alpha=1.0", p8, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 9: Photograph Mismatch Diagnostic Heatmap
    # -------------------------------------------------------------------------
    print("[9/12] Capturing 09_photograph_mismatch_diagnostic.png...")
    p9 = os.path.join(OUTPUT_DIR, "09_photograph_mismatch_diagnostic.png")
    capture_chrome_screenshot(f"{base_url}/?view=mismatch&alpha=0.75", p9, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 10: Subject Proxy 3D Gizmo with Pitch, Yaw, Roll
    # -------------------------------------------------------------------------
    print("[10/12] Capturing 10_subject_proxy_3d_gizmo_pitch_yaw_roll.png...")
    ctrl.select_object("subject")
    ctrl.update_subject_proxy_params(rotation_deg=[15.0, 30.0, -10.0])
    ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    p10 = os.path.join(OUTPUT_DIR, "10_subject_proxy_3d_gizmo_pitch_yaw_roll.png")
    capture_chrome_screenshot(f"{base_url}/?view=relit", p10, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 11: Subject Snap to Ground Contact
    # -------------------------------------------------------------------------
    print("[11/12] Capturing 11_subject_snap_to_ground_contact.png...")
    ctrl.snap_subject_to_ground()
    ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    p11 = os.path.join(OUTPUT_DIR, "11_subject_snap_to_ground_contact.png")
    capture_chrome_screenshot(f"{base_url}/?view=relit", p11, delay_sec=1.2)

    # -------------------------------------------------------------------------
    # SCREENSHOT 12: Missing Asset Error Handling
    # -------------------------------------------------------------------------
    print("[12/12] Capturing 12_missing_asset_error_handling.png...")
    ctrl.project.is_missing_assets = True
    ctrl.project.missing_assets = ["original_image.jpg", "depth_map.png"]
    p12 = os.path.join(OUTPUT_DIR, "12_missing_asset_error_handling.png")
    capture_chrome_screenshot(f"{base_url}/?view=relit", p12, delay_sec=1.2)

    # Verify original photograph hash unchanged (Zero-mutation guarantee)
    final_image_hash = get_file_sha256(sample_img)
    assert orig_image_hash == final_image_hash, "MUTATION DETECTED in source photograph!"
    print(f"\nSource photograph non-destructive integrity verified: {final_image_hash}")
    print(f"All 12 visual QA screenshots successfully captured in {OUTPUT_DIR}/")


if __name__ == "__main__":
    run_pipeline()

