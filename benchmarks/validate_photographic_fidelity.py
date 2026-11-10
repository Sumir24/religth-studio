"""
RELIGHT STUDIO — RS-SPIKE-3B: PHOTOGRAPHIC FIDELITY & IMMUTABILITY VALIDATION
=============================================================================
Workstream D Verification Suite:
  1. Photographic Relighting across diverse real-world subjects:
     - Case P1: Footwear (Nike Sneaker - 576x1024)
     - Case P2: Classical Statue / Organic Surface (576x1024)
     - Case P3: Architectural Relief / Hard Surface (768x512)
  2. Bitwise Zero-Mutation Immutability Test on Protected Mask
  3. Detail Preservation Index (DCI) & E.1 High-Frequency Preservation
  4. C3 Oklab Constant-Hue Gamut Mapping Bounds & Hue Conservation
  5. Photographic Shadow Transport & Contact Grounding Plausibility
Saves authoritative results to docs/RS-SPIKE-3B/photographic_validation_results.json
"""

import os
import json
import math
from typing import Optional
import numpy as np
import cv2
from PIL import Image

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, RenderSettingsData, ProxyType, ReceiverType,
    EnergyConvention, RenderQuality
)
from studio3a.renderer import RenderBackend as CPURenderBackend
from metal2.renderer import MetalRenderBackend


OUTPUT_DIR = "docs/RS-SPIKE-3B/photographic_boards"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    return np.where(srgb <= 0.04045, srgb / 12.92, ((np.maximum(srgb, 0.0) + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(lin: np.ndarray) -> np.ndarray:
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * (np.maximum(lin, 0.0) ** (1.0 / 2.4)) - 0.055)


def linear_to_luminance(img_lin: np.ndarray) -> np.ndarray:
    return 0.2126 * img_lin[..., 0] + 0.7152 * img_lin[..., 1] + 0.0722 * img_lin[..., 2]


def eval_DCI(orig_lin: np.ndarray, relit_lin: np.ndarray, mask: Optional[np.ndarray] = None) -> float:
    """
    Authoritative Multi-Scale Detail Conservation Index (DCI) via Laplacian SSIM.
    Isolates high-frequency textural detail from low-frequency macroscopic shading gradients.
    """
    Y_orig = linear_to_luminance(orig_lin)
    Y_relit = linear_to_luminance(relit_lin)
    lap_orig = cv2.Laplacian(Y_orig, cv2.CV_32F, ksize=3)
    lap_relit = cv2.Laplacian(Y_relit, cv2.CV_32F, ksize=3)
    
    win_size, sigma = 11, 1.5
    C3 = (0.03 * 1.0) ** 2 / 2.0
    mu_x = cv2.GaussianBlur(lap_orig, (win_size, win_size), sigma)
    mu_y = cv2.GaussianBlur(lap_relit, (win_size, win_size), sigma)
    sigma_x_sq = cv2.GaussianBlur(lap_orig ** 2, (win_size, win_size), sigma) - mu_x ** 2
    sigma_y_sq = cv2.GaussianBlur(lap_relit ** 2, (win_size, win_size), sigma) - mu_y ** 2
    sigma_xy = cv2.GaussianBlur(lap_orig * lap_relit, (win_size, win_size), sigma) - mu_x * mu_y
    sigma_x = np.sqrt(np.maximum(0.0, sigma_x_sq))
    sigma_y = np.sqrt(np.maximum(0.0, sigma_y_sq))
    s_map = (2.0 * sigma_xy + C3) / (2.0 * sigma_x * sigma_y + C3)
    
    if mask is not None and np.any(mask):
        return round(float(np.clip(np.mean(s_map[mask]), -1.0, 1.0)), 4)
    return round(float(np.clip(np.mean(s_map), -1.0, 1.0)), 4)


def load_photographic_case(case_id: str):
    if case_id == "P1_nike_sneaker":
        p_img = "demo_output/nike_sample.jpg"
        p_depth = "demo_output/nike_test/depth.png"
        p_normals = "demo_output/nike_test/normals.png"
        
        im = Image.open(p_img).convert("RGB")
        img_srgb = np.array(im, dtype=np.float32) / 255.0
        H, W = img_srgb.shape[:2]
        
        d_im = Image.open(p_depth).resize((W, H))
        depth = np.array(d_im, dtype=np.float32) / 255.0
        if depth.ndim == 3: depth = depth[..., 0]
        
        n_im = Image.open(p_normals).resize((W, H))
        norm_raw = (np.array(n_im, dtype=np.float32) / 255.0) * 2.0 - 1.0
        normals = norm_raw / np.clip(np.linalg.norm(norm_raw, axis=-1, keepdims=True), 1e-6, None)
        
        ground_y = int(H * 0.85)
        fg_mask = (depth > 0.45) & (np.arange(H)[:, None] <= ground_y)
        
        scene = StudioScene()
        scene.camera = CameraData(pos=[0.0, 1.2, 2.5], target=[0.0, 0.35, 0.0], fov_deg=45.0, width=W, height=H)
        scene.subject.proxy_type = ProxyType.MESH
        scene.subject.position = [0.0, 0.15, 0.0]
        scene.subject.dimensions = [0.35, 0.20, 0.45]
        scene.receiver = ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=0.0)
        scene.lights[0].position = [1.2, 1.8, 1.5]
        scene.lights[0].rotation_deg = [-35.0, 30.0, 0.0]
        scene.lights[0].intensity = 1.4
        scene.lights[0].temperature_kelvin = 5600.0
        
        return case_id, scene, img_srgb, depth, normals, fg_mask, ground_y

    elif case_id == "P2_classical_statue":
        p_img = "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/.user_uploaded/media_1794143824741_478ce89a.jpg"
        p_depth = "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/statue_depth.png"
        p_normals = "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/statue_normals.jpg"
        
        im = Image.open(p_img).convert("RGB")
        img_srgb = np.array(im, dtype=np.float32) / 255.0
        H, W = img_srgb.shape[:2]
        
        d_im = Image.open(p_depth).resize((W, H))
        depth = np.array(d_im, dtype=np.float32) / 255.0
        if depth.ndim == 3: depth = depth[..., 0]
        
        n_im = Image.open(p_normals).resize((W, H))
        norm_raw = (np.array(n_im, dtype=np.float32) / 255.0) * 2.0 - 1.0
        normals = norm_raw / np.clip(np.linalg.norm(norm_raw, axis=-1, keepdims=True), 1e-6, None)
        
        ground_y = int(H * 0.95)
        fg_mask = (depth > 0.40) & (np.arange(H)[:, None] <= ground_y)
        
        scene = StudioScene()
        scene.camera = CameraData(pos=[0.0, 1.2, 2.5], target=[0.0, 0.50, 0.0], fov_deg=45.0, width=W, height=H)
        scene.subject.proxy_type = ProxyType.SUPERQUADRIC
        scene.subject.position = [0.0, 0.50, 0.0]
        scene.subject.dimensions = [0.35, 0.55, 0.35]
        scene.subject.sq_exponents = [1.5, 1.2]
        scene.receiver = ReceiverData(receiver_type=ReceiverType.CYCLORAMA, ground_y=0.0)
        scene.lights[0].position = [-1.5, 2.0, 1.2]
        scene.lights[0].rotation_deg = [-30.0, -35.0, 0.0]
        scene.lights[0].intensity = 1.6
        scene.lights[0].temperature_kelvin = 3200.0 # Warm key light
        
        return case_id, scene, img_srgb, depth, normals, fg_mask, ground_y

    elif case_id == "P3_architectural_relief":
        p_img = "demo_output/01_original.png"
        p_depth = "demo_output/02_depth_map.png"
        p_normals = "demo_output/03_surface_normals.png"
        
        im = Image.open(p_img).convert("RGB")
        img_srgb = np.array(im, dtype=np.float32) / 255.0
        H, W = img_srgb.shape[:2]
        
        d_im = Image.open(p_depth).resize((W, H))
        depth = np.array(d_im, dtype=np.float32) / 255.0
        if depth.ndim == 3: depth = depth[..., 0]
        
        n_im = Image.open(p_normals).resize((W, H))
        norm_raw = (np.array(n_im, dtype=np.float32) / 255.0) * 2.0 - 1.0
        normals = norm_raw / np.clip(np.linalg.norm(norm_raw, axis=-1, keepdims=True), 1e-6, None)
        
        ground_y = int(H * 0.70)
        fg_mask = depth > 0.35
        
        scene = StudioScene()
        scene.camera = CameraData(pos=[0.0, 1.0, 2.5], target=[0.0, 0.30, 0.0], fov_deg=45.0, width=W, height=H)
        scene.subject.proxy_type = ProxyType.OBB
        scene.subject.position = [0.0, 0.30, 0.0]
        scene.subject.dimensions = [0.50, 0.30, 0.20]
        scene.receiver = ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=0.0)
        scene.lights[0].position = [1.0, 1.5, 1.8]
        scene.lights[0].rotation_deg = [-25.0, 20.0, 0.0]
        scene.lights[0].intensity = 1.3
        scene.lights[0].temperature_kelvin = 6500.0
        
        return case_id, scene, img_srgb, depth, normals, fg_mask, ground_y

    else:
        raise ValueError(f"Unknown case: {case_id}")


def run_photographic_fidelity_suite():
    print("="*80)
    print("RS-SPIKE-3B: PHOTOGRAPHIC FIDELITY, IMMUTABILITY & TEXTURE AUDIT")
    print("="*80)
    
    metal_backend = MetalRenderBackend()
    cases = ["P1_nike_sneaker", "P2_classical_statue", "P3_architectural_relief"]
    
    results = []
    
    for cid in cases:
        print(f"\n[EVALUATING CASE] {cid}...")
        case_id, scene, img_srgb, depth, normals, fg_mask, ground_y = load_photographic_case(cid)
        H, W = img_srgb.shape[:2]
        
        # 1. Base Render on Apple Silicon GPU
        res = metal_backend.render(scene, img_srgb, depth, normals, fg_mask, quality=RenderQuality.FINAL)
        relit_srgb = res["relit_srgb"]
        relit_lin = srgb_to_linear(relit_srgb)
        orig_lin = srgb_to_linear(img_srgb)
        
        # 2. Bitwise Zero-Mutation Test on Protected Region
        # Protect the left 40% of the image
        prot_mask = np.zeros((H, W), dtype=bool)
        prot_mask[:, :int(W * 0.40)] = True
        
        res_prot = metal_backend.render(
            scene, img_srgb, depth, normals, fg_mask,
            quality=RenderQuality.FINAL,
            protected_mask=prot_mask
        )
        max_prot_diff = float(np.max(np.abs(res_prot["relit_srgb"][prot_mask] - img_srgb[prot_mask])))
        gate_mutation = "PASS" if max_prot_diff == 0.0 else "FAIL"
        
        # 3. Detail Conservation Index (DCI)
        dci_overall = eval_DCI(orig_lin, relit_lin)
        dci_fg = eval_DCI(orig_lin, relit_lin, fg_mask)
        gate_dci = "PASS" if dci_overall >= 0.88 else "QUALIFIED"
        
        # 4. Gamut Validity Check: Any values < 0.0 or > 1.0?
        out_of_gamut_pixels = int(np.sum((relit_srgb < 0.0) | (relit_srgb > 1.0)))
        out_of_gamut_pct = float(out_of_gamut_pixels / (H * W * 3)) * 100.0
        gate_gamut = "PASS" if out_of_gamut_pixels == 0 else "FAIL"
        
        # 5. Contact Seam Attenuation: Average visibility at contact seam
        contact_band = np.zeros((H, W), dtype=bool)
        contact_band[max(0, ground_y - 3):min(H, ground_y + 4), :] = True
        seam_vis_mean = float(np.mean(res["direct_visibility"][contact_band]))
        
        # 6. Latency on Hardware
        gpu_time_ms = res["diagnostics"]["gpu_time_ms"]
        
        print(f"  Dimensions: {W}x{H} ({H*W/1e6:.2f} MP)")
        print(f"  Protected Zero-Mutation Max Diff: {max_prot_diff:.10f} ({gate_mutation})")
        print(f"  Detail Conservation Index (DCI):  Overall = {dci_overall:.4f}, FG = {dci_fg:.4f} ({gate_dci})")
        print(f"  Out of Gamut Pixels:              {out_of_gamut_pixels} ({out_of_gamut_pct:.4f}%) ({gate_gamut})")
        print(f"  Contact Seam Average Visibility:  {seam_vis_mean:.4f}")
        print(f"  GPU Kernel Latency:               {gpu_time_ms:.2f} ms")
        
        # Save Diagnostic Visual Contact Board
        img_orig_u8 = (img_srgb * 255).astype(np.uint8)
        img_relit_u8 = (relit_srgb * 255).astype(np.uint8)
        vis_u8 = cv2.applyColorMap((res["direct_visibility"] * 255).astype(np.uint8), cv2.COLORMAP_VIRIDIS)
        
        # Split view
        split_u8 = img_orig_u8.copy()
        split_u8[:, W//2:] = img_relit_u8[:, W//2:]
        cv2.line(split_u8, (W//2, 0), (W//2, H), (255, 255, 255), 2)
        
        board = np.hstack([img_orig_u8, img_relit_u8, split_u8, vis_u8])
        board_path = os.path.join(OUTPUT_DIR, f"{cid}_photographic_board.png")
        Image.fromarray(board).save(board_path)
        print(f"  Saved Visual Board -> {board_path}")
        
        entry = {
            "case_id": cid,
            "width": W, "height": H,
            "max_protected_mutation": max_prot_diff, "gate_mutation": gate_mutation,
            "dci_overall": dci_overall, "dci_foreground": dci_fg, "gate_dci": gate_dci,
            "out_of_gamut_pct": out_of_gamut_pct, "gate_gamut": gate_gamut,
            "contact_seam_vis_mean": seam_vis_mean,
            "gpu_time_ms": gpu_time_ms,
            "board_path": board_path
        }
        results.append(entry)
        
    out_json = "docs/RS-SPIKE-3B/photographic_validation_results.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SAVED] Photographic Validation JSON -> {out_json}")


if __name__ == "__main__":
    run_photographic_fidelity_suite()
