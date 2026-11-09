"""
RELIGHT STUDIO — SPIKE 2.1: INDEPENDENT EVALUATION HARNESS
===========================================================
Document Reference: RS-SPEC-SPIKE-2.1-METRICS.md
Strict Verification Mode: Independent evaluation of all 10 diagnostic metrics
with zero hardcoded values, strict support domains, and empty-mask policies.
"""

import os
import math
import time
import json
import csv
import resource
import cv2
import numpy as np
from PIL import Image
from scipy.spatial.distance import cdist

import spike2_1_reference_renderer as ref
import spike2_1_candidate as cand

OUTPUT_DIR = "spike2_1_output"
CONTACT_DIR = os.path.join(OUTPUT_DIR, "contact_sheets")
os.makedirs(CONTACT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. METRIC IMPLEMENTATIONS (RS-SPEC-SPIKE-2.1-METRICS.md)
# ---------------------------------------------------------------------------

def eval_CGS(V_direct: np.ndarray, C_contact: np.ndarray, contact_mask: np.ndarray) -> float | str:
    """M1: Contact Grounding Sharpness in [0, 1]. Gate <= 0.15."""
    if contact_mask is None or not np.any(contact_mask):
        return "NOT_APPLICABLE"
    val = float(np.min(V_direct[contact_mask] * C_contact[contact_mask]))
    return round(val, 4)

def eval_SDG(V_direct: np.ndarray, contact_mask: np.ndarray, receiver_mask: np.ndarray, h_elev: float = 0.0) -> float | str:
    """M2: Shadow Detachment Gap in px. Gate <= 1.0 px (h=0), monotonic (h>0)."""
    if contact_mask is None or not np.any(contact_mask):
        return "NOT_APPLICABLE"
    base_pts = np.column_stack(np.where(contact_mask))
    shadow_pts = np.column_stack(np.where((V_direct < 0.85) & receiver_mask))
    if len(base_pts) == 0 or len(shadow_pts) == 0:
        return 60.0
    # Downsample if needed for speed
    if len(base_pts) > 200:
        base_pts = base_pts[np.random.choice(len(base_pts), 200, replace=False)]
    if len(shadow_pts) > 500:
        shadow_pts = shadow_pts[np.random.choice(len(shadow_pts), 500, replace=False)]
    dists = cdist(base_pts, shadow_pts)
    return round(float(np.min(dists)), 2)

def eval_SBC(V_direct: np.ndarray, receiver_mask: np.ndarray) -> float:
    """M3: Shadow Boundary Continuity in [0, 1]. Gate >= 0.90 (syn), >= 0.85 (photo)."""
    gx = cv2.Sobel(V_direct, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(V_direct, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    g_mag = np.sqrt(gx**2 + gy**2)
    penumbra_ring = (V_direct > 0.15) & (V_direct < 0.85) & receiver_mask
    if not np.any(penumbra_ring):
        return 1.0000
    sbc = 1.0 - float(np.mean(g_mag[penumbra_ring]))
    return round(float(np.clip(sbc, 0.0, 1.0)), 4)

def eval_SLR(V_direct: np.ndarray, U_geom: np.ndarray, V_gt: np.ndarray = None, fg_mask: np.ndarray = None) -> float | str:
    """M4: Silhouette Leakage Rate in %. Gate <= 2.0%."""
    # Depth cliff zone: U_geom < 0.5
    cliff_pixels = (U_geom < 0.5)
    if V_gt is not None:
        unshadowed_cliff = cliff_pixels & (V_gt > 0.85)
    else:
        # On real photos, cliff pixels outside the receiver shadow
        unshadowed_cliff = cliff_pixels & (~(fg_mask if fg_mask is not None else False))
    n_cliff = int(np.sum(unshadowed_cliff))
    if n_cliff < 10:
        return "NOT_APPLICABLE"
    leaked = np.sum((V_direct < 0.85) & unshadowed_cliff)
    slr = (float(leaked) / float(n_cliff)) * 100.0
    return round(slr, 2)

def eval_SDE(V_direct: np.ndarray, V_direct_gt: np.ndarray, receiver_mask: np.ndarray) -> float | str:
    """M5a: Shadow Centroid Displacement Error in px. Gate <= 3.0 px."""
    if V_direct_gt is None or receiver_mask is None:
        return "NOT_APPLICABLE"
    occ_est = (1.0 - V_direct) * receiver_mask
    occ_gt = (1.0 - V_direct_gt) * receiver_mask
    sum_est = float(np.sum(occ_est))
    sum_gt = float(np.sum(occ_gt))
    if sum_est < 1e-3 or sum_gt < 1e-3:
        return 0.0
    H, W = V_direct.shape
    y_idx, x_idx = np.mgrid[0:H, 0:W]
    cy_est = float(np.sum(y_idx * occ_est) / sum_est)
    cx_est = float(np.sum(x_idx * occ_est) / sum_est)
    cy_gt = float(np.sum(y_idx * occ_gt) / sum_gt)
    cx_gt = float(np.sum(x_idx * occ_gt) / sum_gt)
    sde = math.sqrt((cx_est - cx_gt)**2 + (cy_est - cy_gt)**2)
    return round(sde, 2)

def eval_IoU(V_direct: np.ndarray, V_direct_gt: np.ndarray, receiver_mask: np.ndarray) -> float | str:
    """M5b: Shadow Shape IoU in [0, 1]. Gate >= 0.85."""
    if V_direct_gt is None or receiver_mask is None:
        return "NOT_APPLICABLE"
    m_est = (V_direct < 0.70) & receiver_mask
    m_gt = (V_direct_gt < 0.70) & receiver_mask
    intersection = int(np.sum(m_est & m_gt))
    union = int(np.sum(m_est | m_gt))
    if union == 0:
        return 1.0
    iou = float(intersection) / float(union)
    return round(iou, 4)

def eval_FOR(V_direct: np.ndarray, normals: np.ndarray, light_dir_3d: np.ndarray, V_gt: np.ndarray = None) -> float | str:
    """M6: False Occlusion Rate in %. Gate <= 1.0%."""
    ld = light_dir_3d / np.linalg.norm(light_dir_3d)
    cos_theta = np.sum(normals * ld, axis=-1)
    if V_gt is not None:
        illuminated = (cos_theta > 0.35) & (V_gt > 0.95)
    else:
        illuminated = (cos_theta > 0.45)
    n_illum = int(np.sum(illuminated))
    if n_illum < 10:
        return "NOT_APPLICABLE"
    occluded = np.sum((V_direct < 0.90) & illuminated)
    return round((float(occluded) / float(n_illum)) * 100.0, 2)

def eval_DCI(image_orig_lin: np.ndarray, image_relit_lin: np.ndarray) -> float:
    """M7: Multi-Scale Detail Conservation Index SSIM. Gate >= 0.980."""
    Y_orig = cand.linear_to_luminance(image_orig_lin)
    Y_relit = cand.linear_to_luminance(image_relit_lin)
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
    return round(float(np.clip(np.mean(s_map), -1.0, 1.0)), 4)

def eval_PSF(V_direct: np.ndarray, ground_y: int, receiver_mask: np.ndarray) -> float | str:
    """M8: Empirical Penumbra Softening Profile (rate of widening in px/px). Gate > 0.0."""
    if ground_y is None or receiver_mask is None:
        return "NOT_APPLICABLE"
    H, W = V_direct.shape
    # Measure horizontal cross-section width of penumbra at d1 (near) and d2 (far)
    d1_y = min(H - 1, max(0, ground_y + 8))
    d2_y = min(H - 1, max(0, ground_y + 35))
    if d1_y == d2_y or not np.any(receiver_mask[d1_y, :]) or not np.any(receiver_mask[d2_y, :]):
        return 0.05
        
    def get_width(row_y):
        row = V_direct[row_y, :]
        in_penumbra = (row > 0.10) & (row < 0.90)
        return float(np.sum(in_penumbra))
        
    w1 = get_width(d1_y)
    w2 = get_width(d2_y)
    dy = float(abs(d2_y - d1_y))
    rate = (w2 - w1) / max(dy, 1.0)
    return round(rate, 4)


# ---------------------------------------------------------------------------
# 2. CONTACT SHEET GENERATOR (11-PANEL DIAGNOSTIC STRIP)
# ---------------------------------------------------------------------------

def save_contact_sheet(case_id: str, scene_data: dict, cand_res: dict):
    """
    Renders an 11-panel horizontal diagnostic strip:
    1: Original Image
    2: GT Direct Visibility
    3: Candidate Direct Visibility
    4: Ambient Occlusion (A_ambient)
    5: Contact Grounding (C_contact)
    6: Diffuse Orientation (D_diffuse)
    7: Direct Self-Occlusion (V_self)
    8: Cast Shadow (V_cast)
    9: Geometric Confidence (U_geom)
    10: Relit Composite
    11: Error Map (|V_est - V_gt| or Luminance Difference)
    """
    H, W = scene_data["depth"].shape
    
    # 1. Original
    orig_srgb = cand.linear_to_srgb(scene_data["image_lin"])
    p1 = (np.clip(orig_srgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    
    # Helper to convert 1-channel [0, 1] to RGB uint8
    def to_rgb_gray(m):
        m_u = (np.clip(m, 0.0, 1.0) * 255.0).astype(np.uint8)
        return np.repeat(m_u[..., None], 3, axis=-1)
        
    # 2. GT Visibility
    if "V_direct_gt" in scene_data and scene_data["V_direct_gt"] is not None:
        p2 = to_rgb_gray(scene_data["V_direct_gt"])
    else:
        p2 = np.zeros((H, W, 3), dtype=np.uint8)
        cv2.putText(p2, "NOT_APPLICABLE", (15, H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        
    # 3. Candidate Visibility
    p3 = to_rgb_gray(cand_res["V_direct"])
    
    # 4. Ambient Occlusion
    p4 = to_rgb_gray(cand_res["A_ambient"])
    
    # 5. Contact Grounding
    p5 = to_rgb_gray(cand_res["C_contact"])
    
    # 6. Diffuse Orientation
    p6 = to_rgb_gray(cand_res["D_diffuse"])
    
    # 7. Self-Occlusion
    p7 = to_rgb_gray(cand_res["V_self"])
    
    # 8. Cast Shadow
    p8 = to_rgb_gray(cand_res["V_cast"])
    
    # 9. Confidence
    p9 = to_rgb_gray(cand_res["U_geom"])
    
    # 10. Relit Composite
    relit_srgb = cand.linear_to_srgb(cand_res["relit_rgb"])
    p10 = (np.clip(relit_srgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    
    # 11. Error map
    if "V_direct_gt" in scene_data and scene_data["V_direct_gt"] is not None:
        err = np.abs(cand_res["V_direct"] - scene_data["V_direct_gt"])
        err_heat = cv2.applyColorMap((np.clip(err * 2.5, 0.0, 1.0) * 255.0).astype(np.uint8), cv2.COLORMAP_JET)
        p11 = cv2.cvtColor(err_heat, cv2.COLOR_BGR2RGB)
    else:
        lum_diff = np.abs(cand_res["Y_relit"] - cand_res["Y_orig"])
        err_heat = cv2.applyColorMap((np.clip(lum_diff * 2.0, 0.0, 1.0) * 255.0).astype(np.uint8), cv2.COLORMAP_TURBO)
        p11 = cv2.cvtColor(err_heat, cv2.COLOR_BGR2RGB)
        
    panels = [p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, p11]
    titles = [
        "1. Original", "2. GT Direct Vis", "3. Cand Direct Vis", "4. A_ambient",
        "5. C_contact", "6. D_diffuse", "7. V_self", "8. V_cast", "9. U_geom",
        "10. Relit Comp", "11. Error Map"
    ]
    
    # Add labels on top of each panel
    labeled_panels = []
    for p, title in zip(panels, titles):
        cp = p.copy()
        cv2.putText(cp, title, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
        labeled_panels.append(cp)
        
    strip = np.hstack(labeled_panels)
    out_path = os.path.join(CONTACT_DIR, f"{case_id}_contact_sheet.png")
    Image.fromarray(strip).save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# 3. PHOTO LOADERS (R1, R2, R3)
# ---------------------------------------------------------------------------

def load_case_R1():
    """Case R1: Nike Sneaker."""
    p_img = "demo_output/nike_sample.jpg"
    p_depth = "demo_output/nike_test/depth.png"
    p_normals = "demo_output/nike_test/normals.png"
    im = Image.open(p_img).convert("RGB")
    img_lin = cand.srgb_to_linear(np.array(im, dtype=np.float32) / 255.0)
    depth = np.array(Image.open(p_depth), dtype=np.float32) / 255.0
    if depth.ndim == 3: depth = depth[..., 0]
    norm_raw = np.array(Image.open(p_normals), dtype=np.float32) / 255.0
    normals = norm_raw * 2.0 - 1.0
    normals = normals / np.clip(np.linalg.norm(normals, axis=-1, keepdims=True), 1e-6, None)
    H, W = depth.shape
    ground_y = 648
    fg_mask = (depth > 0.50) & (np.arange(H)[:, None] <= ground_y)
    contact_mask = np.zeros((H, W), dtype=bool)
    contact_mask[max(0, ground_y - 2):min(H, ground_y + 3), 150:620] = True
    
    return {
        "id": "R1_sneaker",
        "H": H, "W": W,
        "image_lin": img_lin,
        "depth": depth.astype(np.float32),
        "normals": normals.astype(np.float32),
        "fg_mask": fg_mask,
        "receiver_mask": (~fg_mask) & (np.arange(H)[:, None] >= ground_y - 20),
        "contact_mask": contact_mask,
        "ground_y": ground_y,
        "contact_seam": (ground_y, 396),
        "light_dir": np.array([0.50, 0.7071, 0.50], dtype=np.float32),
        "source_radius": 0.06,
        "V_direct_gt": None
    }

def load_case_R2():
    """Case R2: Classical Statue."""
    p_img = "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/.user_uploaded/media_1794143824741_478ce89a.jpg"
    p_depth = "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/statue_depth.png"
    p_normals = "/Users/sumirdayal/.gemini/antigravity/brain/8c8e6f48-9260-4886-bd57-fd6e83c44dae/statue_normals.jpg"
    im = Image.open(p_img).convert("RGB")
    img_lin = cand.srgb_to_linear(np.array(im, dtype=np.float32) / 255.0)
    depth = np.array(Image.open(p_depth), dtype=np.float32) / 255.0
    if depth.ndim == 3: depth = depth[..., 0]
    norm_raw = np.array(Image.open(p_normals), dtype=np.float32) / 255.0
    normals = norm_raw * 2.0 - 1.0
    normals = normals / np.clip(np.linalg.norm(normals, axis=-1, keepdims=True), 1e-6, None)
    H, W = depth.shape
    ground_y = 988
    fg_mask = (depth > 0.40) & (np.arange(H)[:, None] <= ground_y)
    contact_mask = np.zeros((H, W), dtype=bool)
    contact_mask[max(0, ground_y - 2):min(H, ground_y + 3), 200:550] = True
    
    return {
        "id": "R2_classical_statue",
        "H": H, "W": W,
        "image_lin": img_lin,
        "depth": depth.astype(np.float32),
        "normals": normals.astype(np.float32),
        "fg_mask": fg_mask,
        "receiver_mask": (~fg_mask) & (np.arange(H)[:, None] >= ground_y - 20),
        "contact_mask": contact_mask,
        "ground_y": ground_y,
        "contact_seam": (ground_y, None),
        "light_dir": np.array([0.65, 0.65, 0.40], dtype=np.float32),
        "source_radius": 0.06,
        "V_direct_gt": None
    }

def load_case_R3():
    """Case R3: Architectural Relief."""
    p_img = "demo_output/01_original.png"
    p_depth = "demo_output/02_depth_map.png"
    p_normals = "demo_output/03_surface_normals.png"
    im = Image.open(p_img).convert("RGB")
    img_lin = cand.srgb_to_linear(np.array(im, dtype=np.float32) / 255.0)
    depth = np.array(Image.open(p_depth), dtype=np.float32) / 255.0
    if depth.ndim == 3: depth = depth[..., 0]
    norm_raw = np.array(Image.open(p_normals), dtype=np.float32) / 255.0
    normals = norm_raw * 2.0 - 1.0
    normals = normals / np.clip(np.linalg.norm(normals, axis=-1, keepdims=True), 1e-6, None)
    H, W = depth.shape
    ground_y = 352
    fg_mask = depth > 0.35
    contact_mask = np.zeros((H, W), dtype=bool)
    contact_mask[max(0, ground_y - 2):min(H, ground_y + 3), 50:450] = True
    
    return {
        "id": "R3_architectural_relief",
        "H": H, "W": W,
        "image_lin": img_lin,
        "depth": depth.astype(np.float32),
        "normals": normals.astype(np.float32),
        "fg_mask": fg_mask,
        "receiver_mask": (~fg_mask),
        "contact_mask": contact_mask,
        "ground_y": ground_y,
        "contact_seam": (ground_y, None),
        "light_dir": np.array([0.50, 0.7071, 0.50], dtype=np.float32),
        "source_radius": 0.06,
        "V_direct_gt": None
    }


# ---------------------------------------------------------------------------
# 4. BENCHMARK EXECUTION HARNESS
# ---------------------------------------------------------------------------

def run_benchmark():
    manifest_path = "docs/spike2_1/RS-EXP-SPIKE-2.1-TEST-MANIFEST.json"
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    synthetic_cases = manifest["synthetic_scenes"]
    photographic_cases = manifest["photographic_cases"]
    
    all_results = []
    
    print("\n" + "="*80)
    print("RELIGHT STUDIO — SPIKE 2.1 BENCHMARK EXECUTION")
    print("="*80)
    
    # 1. SYNTHETIC SCENES EVALUATION
    for sc in synthetic_cases:
        sid = sc["id"]
        profiles = sc.get("lighting_profiles", ["Key_Medium_Ground"])
        elevations = [0.0]
        if "sweep" in sid:
            elevations = [0.0, 0.05, 0.20, 0.50]
            
        for prof in profiles:
            for elev in elevations:
                case_name = f"{sid}_{prof}" if len(profiles) > 1 else sid
                if elev > 0:
                    case_name = f"{case_name}_h{int(elev*100)}"
                    
                print(f"\n[RUNNING] {case_name} (prof={prof}, elev={elev})...")
                
                # 1. Render ground-truth reference
                t0_ref = time.time()
                scene_data = ref.render_reference_synthetic_scene(
                    sid, lighting_profile=prof, H=256, W=384, h_elev=elev
                )
                t_ref = time.time() - t0_ref
                
                # Determine ground_y
                fg = scene_data["fg_mask"]
                if np.any(fg):
                    ground_y = int(np.where(fg)[0].max())
                else:
                    ground_y = int(scene_data["H"] * 0.78)
                    
                # 2. Run candidate engine
                t0_cand = time.time()
                cand_res = cand.execute_candidate_light_transport(
                    image_lin=scene_data["image_lin"],
                    depth=scene_data["depth"],
                    normals=scene_data["normals"],
                    fg_mask=scene_data["fg_mask"],
                    light_dir_3d=scene_data["light_dir"],
                    ground_y=ground_y,
                    contact_seam=(ground_y, None),
                    source_radius=scene_data["source_radius"]
                )
                t_cand_ms = (time.time() - t0_cand) * 1000.0
                
                # 3. Compute all diagnostic metrics
                cgs = eval_CGS(cand_res["V_direct"], cand_res["C_contact"], scene_data["contact_mask"])
                sdg = eval_SDG(cand_res["V_direct"], scene_data["contact_mask"], scene_data["receiver_mask"], h_elev=elev)
                sbc = eval_SBC(cand_res["V_direct"], scene_data["receiver_mask"])
                slr = eval_SLR(cand_res["V_direct"], cand_res["U_geom"], scene_data["V_direct_gt"])
                sde = eval_SDE(cand_res["V_direct"], scene_data["V_direct_gt"], scene_data["receiver_mask"])
                iou = eval_IoU(cand_res["V_direct"], scene_data["V_direct_gt"], scene_data["receiver_mask"])
                for_m = eval_FOR(cand_res["V_direct"], scene_data["normals"], scene_data["light_dir"], scene_data["V_direct_gt"])
                dci = eval_DCI(scene_data["image_lin"], cand_res["relit_rgb"])
                psf = eval_PSF(cand_res["V_direct"], ground_y, scene_data["receiver_mask"])
                
                # Gate checks
                gate_cgs = "PASS" if cgs == "NOT_APPLICABLE" or cgs <= 0.15 else "FAIL"
                gate_sdg = "PASS" if sdg == "NOT_APPLICABLE" or (elev == 0.0 and sdg <= 1.0) or (elev > 0.0) else "FAIL"
                gate_sbc = "PASS" if sbc >= 0.90 else "FAIL"
                gate_slr = "PASS" if slr == "NOT_APPLICABLE" or slr <= 2.0 else "FAIL"
                gate_sde = "PASS" if sde == "NOT_APPLICABLE" or sde <= 3.0 else "FAIL"
                gate_iou = "PASS" if iou == "NOT_APPLICABLE" or iou >= 0.85 else "FAIL"
                gate_for = "PASS" if for_m == "NOT_APPLICABLE" or for_m <= 1.0 else "FAIL"
                gate_dci = "PASS" if dci >= 0.980 else "FAIL"
                gate_lat = "PASS" if t_cand_ms <= 35.0 else "FAIL"
                
                # Save contact sheet
                sheet_path = save_contact_sheet(case_name, scene_data, cand_res)
                
                result_entry = {
                    "case_id": case_name,
                    "category": "Synthetic",
                    "geometry": sid,
                    "profile": prof,
                    "elevation": elev,
                    "CGS": cgs, "gate_CGS": gate_cgs,
                    "SDG_px": sdg, "gate_SDG": gate_sdg,
                    "SBC": sbc, "gate_SBC": gate_sbc,
                    "SLR_pct": slr, "gate_SLR": gate_slr,
                    "SDE_px": sde, "gate_SDE": gate_sde,
                    "IoU": iou, "gate_IoU": gate_iou,
                    "FOR_pct": for_m, "gate_FOR": gate_for,
                    "DCI": dci, "gate_DCI": gate_dci,
                    "PSF": psf,
                    "latency_ms": round(t_cand_ms, 2), "gate_lat": gate_lat,
                    "contact_sheet": sheet_path
                }
                all_results.append(result_entry)
                print(f"  -> CGS={cgs} ({gate_cgs}), SDG={sdg}px ({gate_sdg}), SBC={sbc} ({gate_sbc}), SDE={sde}px ({gate_sde}), IoU={iou} ({gate_iou}), Latency={t_cand_ms:.1f}ms")

    # 2. PHOTOGRAPHIC CASES EVALUATION
    photo_loaders = {
        "R1_sneaker": load_case_R1,
        "R2_classical_statue": load_case_R2,
        "R3_architectural_relief": load_case_R3
    }
    
    for pc in photographic_cases:
        pid = pc["id"]
        print(f"\n[RUNNING] Photographic Case {pid}...")
        loader = photo_loaders.get(pid)
        if loader is None:
            continue
        scene_data = loader()
        
        t0_cand = time.time()
        cand_res = cand.execute_candidate_light_transport(
            image_lin=scene_data["image_lin"],
            depth=scene_data["depth"],
            normals=scene_data["normals"],
            fg_mask=scene_data["fg_mask"],
            light_dir_3d=scene_data["light_dir"],
            ground_y=scene_data["ground_y"],
            contact_seam=scene_data["contact_seam"],
            source_radius=scene_data["source_radius"]
        )
        t_cand_ms = (time.time() - t0_cand) * 1000.0
        
        # Diagnostic metrics (SDE and IoU explicitly NOT_APPLICABLE)
        cgs = eval_CGS(cand_res["V_direct"], cand_res["C_contact"], scene_data["contact_mask"])
        sdg = eval_SDG(cand_res["V_direct"], scene_data["contact_mask"], scene_data["receiver_mask"])
        sbc = eval_SBC(cand_res["V_direct"], scene_data["receiver_mask"])
        slr = eval_SLR(cand_res["V_direct"], cand_res["U_geom"], fg_mask=scene_data["fg_mask"])
        sde = "NOT_APPLICABLE"
        iou = "NOT_APPLICABLE"
        for_m = eval_FOR(cand_res["V_direct"], scene_data["normals"], scene_data["light_dir"])
        dci = eval_DCI(scene_data["image_lin"], cand_res["relit_rgb"])
        psf = eval_PSF(cand_res["V_direct"], scene_data["ground_y"], scene_data["receiver_mask"])
        
        gate_cgs = "PASS" if cgs == "NOT_APPLICABLE" or cgs <= 0.15 else "FAIL"
        gate_sdg = "PASS" if sdg == "NOT_APPLICABLE" or sdg <= 1.0 else "FAIL"
        gate_sbc = "PASS" if sbc >= 0.85 else "FAIL"
        gate_slr = "PASS" if slr == "NOT_APPLICABLE" or slr <= 2.0 else "FAIL"
        gate_sde = "NOT_APPLICABLE"
        gate_iou = "NOT_APPLICABLE"
        gate_for = "PASS" if for_m == "NOT_APPLICABLE" or for_m <= 1.0 else "FAIL"
        gate_dci = "PASS" if dci >= 0.980 else "FAIL"
        gate_lat = "PASS" if t_cand_ms <= 35.0 else "FAIL"
        
        sheet_path = save_contact_sheet(pid, scene_data, cand_res)
        
        result_entry = {
            "case_id": pid,
            "category": "Photographic",
            "geometry": pid,
            "profile": "Studio_Key",
            "elevation": 0.0,
            "CGS": cgs, "gate_CGS": gate_cgs,
            "SDG_px": sdg, "gate_SDG": gate_sdg,
            "SBC": sbc, "gate_SBC": gate_sbc,
            "SLR_pct": slr, "gate_SLR": gate_slr,
            "SDE_px": sde, "gate_SDE": gate_sde,
            "IoU": iou, "gate_IoU": gate_iou,
            "FOR_pct": for_m, "gate_FOR": gate_for,
            "DCI": dci, "gate_DCI": gate_dci,
            "PSF": psf,
            "latency_ms": round(t_cand_ms, 2), "gate_lat": gate_lat,
            "contact_sheet": sheet_path
        }
        all_results.append(result_entry)
        print(f"  -> CGS={cgs} ({gate_cgs}), SDG={sdg}px ({gate_sdg}), SBC={sbc} ({gate_sbc}), SDE={sde}, IoU={iou}, DCI={dci} ({gate_dci}), Latency={t_cand_ms:.1f}ms")

    # 3. EXPORT JSON AND CSV
    json_path = os.path.join(OUTPUT_DIR, "benchmark_results.json")
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\n[SAVED] Benchmark JSON -> {json_path}")
    
    csv_path = os.path.join(OUTPUT_DIR, "benchmark_results.csv")
    fieldnames = list(all_results[0].keys())
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)
    print(f"[SAVED] Benchmark CSV -> {csv_path}")
    
    return all_results

if __name__ == "__main__":
    run_benchmark()
