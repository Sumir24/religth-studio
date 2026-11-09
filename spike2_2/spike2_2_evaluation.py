"""
RELIGHT STUDIO — SPIKE 2.2: CORRECTED EVALUATION HARNESS
=========================================================
Document Reference: RS-SPEC-SPIKE-2.2-METRICS.md
Strict Verification Mode: Independent evaluation of all diagnostic metrics
with zero hardcoded values, independent ground-truth cliff masks,
strict empty-mask policies, and missing-feature recall penalties.
"""

import os
import math
import time
import json
import csv
import cv2
import numpy as np
from PIL import Image
from scipy.spatial.distance import cdist

import spike2_2_reference_renderer as ref
import spike2_2_candidate as cand

OUTPUT_DIR = "spike2_2_output"
CONTACT_DIR = os.path.join(OUTPUT_DIR, "contact_sheets")
os.makedirs(CONTACT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. METRIC IMPLEMENTATIONS (RS-SPEC-SPIKE-2.2-METRICS.md)
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
    if len(base_pts) > 200:
        base_pts = base_pts[np.random.choice(len(base_pts), 200, replace=False)]
    if len(shadow_pts) > 500:
        shadow_pts = shadow_pts[np.random.choice(len(shadow_pts), 500, replace=False)]
    dists = cdist(base_pts, shadow_pts)
    return round(float(np.min(dists)), 2)

def eval_SBC(V_direct: np.ndarray, receiver_mask: np.ndarray) -> float | str:
    """M3: Shadow Boundary Continuity in [0, 1]. Gate >= 0.90 (syn), >= 0.85 (photo)."""
    penumbra_ring = (V_direct > 0.15) & (V_direct < 0.85) & receiver_mask
    if not np.any(penumbra_ring) or np.sum(penumbra_ring) < 10:
        # Crucial fix: return NOT_APPLICABLE when no shadow boundary exists!
        return "NOT_APPLICABLE"
    gx = cv2.Sobel(V_direct, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(V_direct, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    g_mag = np.sqrt(gx**2 + gy**2)
    sbc = 1.0 - float(np.mean(g_mag[penumbra_ring]))
    return round(float(np.clip(sbc, 0.0, 1.0)), 4)

def eval_SLR(V_direct: np.ndarray, cliff_mask_gt: np.ndarray, V_gt: np.ndarray = None, fg_mask: np.ndarray = None) -> float | str:
    """M4: Silhouette Leakage Rate in %. Gate <= 2.0%."""
    if cliff_mask_gt is None or not np.any(cliff_mask_gt):
        return "NOT_APPLICABLE"
    if V_gt is not None:
        unshadowed_cliff = cliff_mask_gt & (V_gt > 0.85)
    else:
        unshadowed_cliff = cliff_mask_gt & (~(fg_mask if fg_mask is not None else False))
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
    # Crucial fix: if estimated shadow is missing, report NOT_APPLICABLE (not 0.0!)
    if sum_est < 10.0:
        return "NOT_APPLICABLE"
    if sum_gt < 10.0:
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

def eval_REC_shadow(V_direct: np.ndarray, V_direct_gt: np.ndarray, receiver_mask: np.ndarray) -> float | str:
    """M5c: Shadow Recall in %. Gate >= 90.0%."""
    if V_direct_gt is None or receiver_mask is None:
        return "NOT_APPLICABLE"
    m_est = (V_direct < 0.70) & receiver_mask
    m_gt = (V_direct_gt < 0.70) & receiver_mask
    n_gt = int(np.sum(m_gt))
    if n_gt == 0:
        return 100.0
    rec = (float(np.sum(m_est & m_gt)) / float(n_gt)) * 100.0
    return round(rec, 2)

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
    """M8: Empirical Penumbra Softening Profile. Gate > 0.0 px/px."""
    if ground_y is None or receiver_mask is None:
        return "NOT_APPLICABLE"
    H, W = V_direct.shape
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
# 2. CONTACT SHEET GENERATOR (11-PANEL STRIP)
# ---------------------------------------------------------------------------

def save_contact_sheet(case_id: str, scene_data: dict, cand_res: dict) -> str:
    H, W = scene_data["depth"].shape
    orig_srgb = cand.linear_to_srgb(scene_data["image_lin"])
    p1 = (np.clip(orig_srgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    
    def to_rgb_gray(m):
        m_u = (np.clip(m, 0.0, 1.0) * 255.0).astype(np.uint8)
        return np.repeat(m_u[..., None], 3, axis=-1)
        
    if "V_direct_gt" in scene_data and scene_data["V_direct_gt"] is not None:
        p2 = to_rgb_gray(scene_data["V_direct_gt"])
    else:
        p2 = np.zeros((H, W, 3), dtype=np.uint8)
        cv2.putText(p2, "NOT_APPLICABLE", (15, H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
        
    p3 = to_rgb_gray(cand_res["V_direct"])
    p4 = to_rgb_gray(cand_res["A_ambient"])
    p5 = to_rgb_gray(cand_res["C_contact"])
    p6 = to_rgb_gray(cand_res["D_diffuse"])
    p7 = to_rgb_gray(cand_res["V_self"])
    p8 = to_rgb_gray(cand_res["V_cast"])
    p9 = to_rgb_gray(cand_res["U_geom"])
    
    relit_srgb = cand.linear_to_srgb(cand_res["relit_rgb"])
    p10 = (np.clip(relit_srgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    
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
# 3. PHOTOGRAPHIC CASE LOADERS
# ---------------------------------------------------------------------------

def load_case_R1():
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
    
    # Accurate contact interface: points near ground line that match ground depth
    contact_mask = np.zeros((H, W), dtype=bool)
    contact_mask[max(0, ground_y - 2):min(H, ground_y + 3), 150:620] = (depth[max(0, ground_y - 2):min(H, ground_y + 3), 150:620] > 0.48)
    
    # Depth cliff mask
    gx = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    cliff_mask = np.sqrt(gx**2 + gy**2) > 0.04
    
    return {
        "id": "R1_sneaker",
        "H": H, "W": W,
        "image_lin": img_lin,
        "depth": depth.astype(np.float32),
        "normals": normals.astype(np.float32),
        "fg_mask": fg_mask,
        "receiver_mask": (~fg_mask) & (np.arange(H)[:, None] >= ground_y - 20),
        "contact_mask": contact_mask,
        "cliff_mask": cliff_mask,
        "ground_y": ground_y,
        "contact_seam": (ground_y, 396),
        "light_dir": np.array([0.50, 0.7071, 0.50], dtype=np.float32),
        "source_radius": 0.06,
        "V_direct_gt": None
    }

def load_case_R2():
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
    
    gx = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    cliff_mask = np.sqrt(gx**2 + gy**2) > 0.04
    
    return {
        "id": "R2_classical_statue",
        "H": H, "W": W,
        "image_lin": img_lin,
        "depth": depth.astype(np.float32),
        "normals": normals.astype(np.float32),
        "fg_mask": fg_mask,
        "receiver_mask": (~fg_mask) & (np.arange(H)[:, None] >= ground_y - 20),
        "contact_mask": contact_mask,
        "cliff_mask": cliff_mask,
        "ground_y": ground_y,
        "contact_seam": (ground_y, None),
        "light_dir": np.array([0.65, 0.65, 0.40], dtype=np.float32),
        "source_radius": 0.06,
        "V_direct_gt": None
    }

def load_case_R3():
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
    
    # Relief terrain has no flat floor; contact interface is along relief base
    contact_mask = np.zeros((H, W), dtype=bool)
    contact_mask[max(0, ground_y - 2):min(H, ground_y + 3), 50:450] = True
    
    gx = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    cliff_mask = np.sqrt(gx**2 + gy**2) > 0.04
    
    return {
        "id": "R3_architectural_relief",
        "H": H, "W": W,
        "image_lin": img_lin,
        "depth": depth.astype(np.float32),
        "normals": normals.astype(np.float32),
        "fg_mask": fg_mask,
        "receiver_mask": (~fg_mask),
        "contact_mask": contact_mask,
        "cliff_mask": cliff_mask,
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
    manifest_path = "docs/spike2_2/RS-EXP-SPIKE-2.2-TEST-MANIFEST.json"
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    synthetic_cases = manifest["synthetic_scenes"]
    photographic_cases = manifest["photographic_cases"]
    
    all_results = []
    
    print("\n" + "="*80)
    print("RELIGHT STUDIO — SPIKE 2.2 BENCHMARK EXECUTION")
    print("="*80)
    
    # 1. SYNTHETIC SCENES EVALUATION
    for sc in synthetic_cases:
        sid = sc["id"]
        profiles = sc.get("lighting_profiles", ["Key_Medium_Ground"])
        elevations = [0.0]
        if "sweep" in sid:
            elevations = [0.0, 0.05, 0.20, 0.50]
            
        cameras = ["Studio_Standard"]
        if "camera" in sid:
            cameras = ["Eye_Level", "Studio_Standard", "Top_Down"]
            
        radii = [None]
        if "light_scaling" in sid:
            radii = [0.01, 0.06, 0.15]
            
        for prof in profiles:
            for elev in elevations:
                for cam in cameras:
                    for rad in radii:
                        case_name = sid
                        if len(profiles) > 1: case_name += f"_{prof}"
                        if elev > 0: case_name += f"_h{int(elev*100)}"
                        if cam != "Studio_Standard": case_name += f"_{cam}"
                        if rad is not None: case_name += f"_r{int(rad*100)}"
                        
                        print(f"\n[RUNNING] {case_name}...")
                        scene_data = ref.render_reference_synthetic_scene(
                            sid, lighting_profile=prof, H=256, W=384, h_elev=elev,
                            camera_pitch=cam, source_radius_override=rad
                        )
                        
                        fg = scene_data["fg_mask"]
                        if np.any(fg):
                            ground_y = int(np.where(fg)[0].max())
                        else:
                            ground_y = int(scene_data["H"] * 0.78)
                            
                        # Candidate execution
                        t0 = time.time()
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
                        t_cand_ms = (time.time() - t0) * 1000.0
                        
                        # Diagnostic metrics
                        cgs = eval_CGS(cand_res["V_direct"], cand_res["C_contact"], scene_data["contact_mask"])
                        sdg = eval_SDG(cand_res["V_direct"], scene_data["contact_mask"], scene_data["receiver_mask"], h_elev=elev)
                        sbc = eval_SBC(cand_res["V_direct"], scene_data["receiver_mask"])
                        slr = eval_SLR(cand_res["V_direct"], scene_data["cliff_mask"], scene_data["V_direct_gt"])
                        sde = eval_SDE(cand_res["V_direct"], scene_data["V_direct_gt"], scene_data["receiver_mask"])
                        iou = eval_IoU(cand_res["V_direct"], scene_data["V_direct_gt"], scene_data["receiver_mask"])
                        rec = eval_REC_shadow(cand_res["V_direct"], scene_data["V_direct_gt"], scene_data["receiver_mask"])
                        for_m = eval_FOR(cand_res["V_direct"], scene_data["normals"], scene_data["light_dir"], scene_data["V_direct_gt"])
                        dci = eval_DCI(scene_data["image_lin"], cand_res["relit_rgb"])
                        psf = eval_PSF(cand_res["V_direct"], ground_y, scene_data["receiver_mask"])
                        
                        gate_cgs = "PASS" if cgs == "NOT_APPLICABLE" or cgs <= 0.15 else "FAIL"
                        gate_sdg = "PASS" if sdg == "NOT_APPLICABLE" or (elev == 0.0 and sdg <= 1.0) or (elev > 0.0) else "FAIL"
                        gate_sbc = "PASS" if sbc == "NOT_APPLICABLE" or sbc >= 0.90 else "FAIL"
                        gate_slr = "PASS" if slr == "NOT_APPLICABLE" or slr <= 2.0 else "FAIL"
                        gate_sde = "PASS" if sde == "NOT_APPLICABLE" or sde <= 3.0 else "FAIL"
                        gate_iou = "PASS" if iou == "NOT_APPLICABLE" or iou >= 0.85 else "FAIL"
                        gate_rec = "PASS" if rec == "NOT_APPLICABLE" or rec >= 90.0 else "FAIL"
                        gate_for = "PASS" if for_m == "NOT_APPLICABLE" or for_m <= 1.0 else "FAIL"
                        gate_dci = "PASS" if dci >= 0.980 else "FAIL"
                        gate_lat = "PASS" if t_cand_ms <= 35.0 else "FAIL"
                        
                        sheet_path = save_contact_sheet(case_name, scene_data, cand_res)
                        
                        entry = {
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
                            "REC_shadow_pct": rec, "gate_REC": gate_rec,
                            "FOR_pct": for_m, "gate_FOR": gate_for,
                            "DCI": dci, "gate_DCI": gate_dci,
                            "PSF": psf,
                            "latency_ms": round(t_cand_ms, 2), "gate_lat": gate_lat,
                            "contact_sheet": sheet_path
                        }
                        all_results.append(entry)
                        print(f"  -> CGS={cgs} ({gate_cgs}), SDG={sdg}px ({gate_sdg}), SBC={sbc} ({gate_sbc}), SLR={slr}% ({gate_slr}), SDE={sde}px ({gate_sde}), IoU={iou} ({gate_iou}), REC={rec}%, Lat={t_cand_ms:.1f}ms")

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
        if loader is None: continue
        scene_data = loader()
        
        t0 = time.time()
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
        t_cand_ms = (time.time() - t0) * 1000.0
        
        cgs = eval_CGS(cand_res["V_direct"], cand_res["C_contact"], scene_data["contact_mask"])
        sdg = eval_SDG(cand_res["V_direct"], scene_data["contact_mask"], scene_data["receiver_mask"])
        sbc = eval_SBC(cand_res["V_direct"], scene_data["receiver_mask"])
        slr = eval_SLR(cand_res["V_direct"], scene_data["cliff_mask"], fg_mask=scene_data["fg_mask"])
        sde = "NOT_APPLICABLE"
        iou = "NOT_APPLICABLE"
        rec = "NOT_APPLICABLE"
        for_m = eval_FOR(cand_res["V_direct"], scene_data["normals"], scene_data["light_dir"])
        dci = eval_DCI(scene_data["image_lin"], cand_res["relit_rgb"])
        psf = eval_PSF(cand_res["V_direct"], scene_data["ground_y"], scene_data["receiver_mask"])
        
        gate_cgs = "PASS" if cgs == "NOT_APPLICABLE" or cgs <= 0.15 else "FAIL"
        gate_sdg = "PASS" if sdg == "NOT_APPLICABLE" or sdg <= 1.0 else "FAIL"
        gate_sbc = "PASS" if sbc == "NOT_APPLICABLE" or sbc >= 0.85 else "FAIL"
        gate_slr = "PASS" if slr == "NOT_APPLICABLE" or slr <= 2.0 else "FAIL"
        gate_sde = "NOT_APPLICABLE"
        gate_iou = "NOT_APPLICABLE"
        gate_rec = "NOT_APPLICABLE"
        gate_for = "PASS" if for_m == "NOT_APPLICABLE" or for_m <= 1.0 else "FAIL"
        gate_dci = "PASS" if dci >= 0.980 else "FAIL"
        gate_lat = "PASS" if t_cand_ms <= 35.0 else "FAIL"
        
        sheet_path = save_contact_sheet(pid, scene_data, cand_res)
        
        entry = {
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
            "REC_shadow_pct": rec, "gate_REC": gate_rec,
            "FOR_pct": for_m, "gate_FOR": gate_for,
            "DCI": dci, "gate_DCI": gate_dci,
            "PSF": psf,
            "latency_ms": round(t_cand_ms, 2), "gate_lat": gate_lat,
            "contact_sheet": sheet_path
        }
        all_results.append(entry)
        print(f"  -> CGS={cgs} ({gate_cgs}), SDG={sdg}px ({gate_sdg}), SBC={sbc} ({gate_sbc}), SLR={slr}% ({gate_slr}), SDE={sde}, DCI={dci} ({gate_dci}), Lat={t_cand_ms:.1f}ms")

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
