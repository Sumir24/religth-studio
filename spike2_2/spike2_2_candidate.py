"""
RELIGHT STUDIO — SPIKE 2.2: CORRECTED CANDIDATE SHADOW TRANSPORT ENGINE
========================================================================
Document Reference: RS-SPEC-SPIKE-2.2-ARCHITECTURE.md
Strict Isolation Mode: Completely decoupled from engine/relighter_v4.py and Spike 2.1.

Implements the Seven Decoupled Physical Lighting Terms:
  1. Direct Light Visibility: V_direct(x, L)
  2. Ambient Visibility: A_ambient(x) (Multi-Scale HBAO, modulates indirect floor ONLY)
  3. Contact Grounding: C_contact(x, L) (Directional direct near-field visibility)
  4. Diffuse Orientation: D_diffuse(x, L) (Hermite-tapered surface cosine response)
  5. Self-Occlusion: V_self(x, L) (Foreground raymarching along light vector)
  6. Cast Shadow Visibility: V_cast(x, L) (Perspective proxy projection with lit-side bleed guard)
  7. Geometric Confidence: U_geometry(x) (Continuous depth/normal uncertainty)

Corrected Additive Radiance Compositing Contract:
  Y_indirect = Y_b * R_ambient * A_ambient
  Y_direct   = Y_b * (R_key - R_ambient) * D_diffuse * V_direct
  Y_relit    = Y_indirect + Y_direct
Integrated with Spike 1 E.1 Guided-Filter Ratio and C3 Oklab Gamut Mapping.
"""

import math
import cv2
import numpy as np

# ---------------------------------------------------------------------------
# 1. COLOR & MATH CONVERSIONS (Spike 1 Tested Baseline)
# ---------------------------------------------------------------------------

def srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    s = np.clip(srgb.astype(np.float32), 0.0, 1.0)
    return np.where(s <= 0.04045, s / 12.92, ((s + 0.055) / 1.055) ** 2.4).astype(np.float32)

def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    l = np.clip(linear.astype(np.float32), 0.0, 1.0)
    return np.where(l <= 0.0031308, l * 12.92, 1.055 * (l ** (1.0 / 2.4)) - 0.055).astype(np.float32)

def linear_to_luminance(lin_rgb: np.ndarray) -> np.ndarray:
    return (0.2126 * lin_rgb[..., 0] + 0.7152 * lin_rgb[..., 1] + 0.0722 * lin_rgb[..., 2]).astype(np.float32)

# Oklab Conversion Matrices (Björn Ottosson, 2020)
M1_RGB_TO_LMS = np.array([
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005]
], dtype=np.float32).T

M2_LMS_TO_OKLAB = np.array([
    [0.2104542553,  0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050,  0.4505937099],
    [0.0259040371,  0.7827717662, -0.8086757660]
], dtype=np.float32).T

M1_OKLAB_TO_LMS = np.array([
    [1.0,  0.3963377774,  0.2158037573],
    [1.0, -0.1055613458, -0.0638541728],
    [1.0, -0.0894841775, -1.2914855480]
], dtype=np.float32).T

M2_LMS_TO_RGB = np.array([
    [ 4.0767416621, -3.3077115913,  0.2309699292],
    [-1.2684380046,  2.6097574011, -0.3413193965],
    [-0.0041960863, -0.7034186147,  1.7076147010]
], dtype=np.float32).T

def rgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    rgb_c = np.maximum(rgb.astype(np.float32), 0.0)
    lms = np.dot(rgb_c, M1_RGB_TO_LMS)
    lms_cube = np.cbrt(np.maximum(lms, 0.0))
    return np.dot(lms_cube, M2_LMS_TO_OKLAB).astype(np.float32)

def oklab_to_rgb(oklab: np.ndarray) -> np.ndarray:
    lms_cube = np.dot(oklab.astype(np.float32), M1_OKLAB_TO_LMS)
    lms = lms_cube ** 3
    return np.dot(lms, M2_LMS_TO_RGB).astype(np.float32)

def box_filter(src: np.ndarray, r: int) -> np.ndarray:
    return cv2.boxFilter(src, -1, (2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REFLECT)

def guided_filter(guide: np.ndarray, src: np.ndarray, r: int, eps: float) -> np.ndarray:
    I = guide.astype(np.float32)
    p = src.astype(np.float32)
    mI = box_filter(I, r)
    mp = box_filter(p, r)
    cov = box_filter(I * p, r) - mI * mp
    var = box_filter(I * I, r) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    return (box_filter(a, r) * I + box_filter(b, r)).astype(np.float32)

def color_reconstruct_C3(lin_orig: np.ndarray, Y_orig: np.ndarray, Y_relit: np.ndarray) -> np.ndarray:
    """C3: Oklab Gamut Mapping with 16-step constant-hue bisection."""
    scale = (Y_relit / np.maximum(Y_orig, 1e-6))[..., None]
    ref_rgb = lin_orig * scale
    oklab_ref = rgb_to_oklab(ref_rgb)
    oklab_orig = rgb_to_oklab(lin_orig)
    
    L_target = oklab_ref[..., 0]
    L_disp = np.where(L_target <= 0.90, np.maximum(1e-4, L_target),
                      0.90 + 0.10 * np.tanh((L_target - 0.90) / 0.10))
    
    a_orig = oklab_orig[..., 1]
    b_orig = oklab_orig[..., 2]
    chroma_orig = np.sqrt(a_orig**2 + b_orig**2)
    neutral_mask = chroma_orig < 1e-4
    a_init = np.where(neutral_mask, 0.0, a_orig)
    b_init = np.where(neutral_mask, 0.0, b_orig)
    
    test_oklab = np.stack([L_disp, a_init, b_init], axis=-1)
    raw_rgb = oklab_to_rgb(test_oklab)
    excursion_mask = (raw_rgb < 0.0) | (raw_rgb > 1.0)
    needs_mapping = np.any(excursion_mask, axis=-1) & (~neutral_mask)
    
    t_low = np.zeros_like(L_disp)
    t_high = np.ones_like(L_disp)
    for _ in range(16):
        t_mid = 0.5 * (t_low + t_high)
        a_mid = a_init * t_mid
        b_mid = b_init * t_mid
        mid_oklab = np.stack([L_disp, a_mid, b_mid], axis=-1)
        mid_rgb = oklab_to_rgb(mid_oklab)
        in_gamut = np.all((mid_rgb >= 0.0) & (mid_rgb <= 1.0), axis=-1)
        t_low = np.where(in_gamut, t_mid, t_low)
        t_high = np.where(in_gamut, t_high, t_mid)
        
    final_t = np.where(needs_mapping, t_low, 1.0)
    final_a = a_init * final_t
    final_b = b_init * final_t
    final_oklab = np.stack([L_disp, final_a, final_b], axis=-1)
    return np.clip(oklab_to_rgb(final_oklab), 0.0, 1.0).astype(np.float32)

def paradigm_E1(Y: np.ndarray, R: np.ndarray, guide: np.ndarray) -> np.ndarray:
    """E.1: Guided-Filter Regularized Shading Ratio."""
    logY = np.log(np.maximum(Y, 1e-4))
    r0, eps0 = 16, 0.02**2
    B = guided_filter(guide, logY, r0, eps0)
    D = logY - B
    Yb = np.exp(B)
    
    S_old = Yb
    S_new = Yb * R
    eps_old = 0.02
    eps_new = 0.02 * float(np.mean(R))
    
    rho_raw = np.log(S_new + eps_new) - np.log(S_old + eps_old)
    rho_bar = guided_filter(guide, rho_raw, r=24, eps=0.01)
    
    Y_relit = np.exp(B + rho_bar + D)
    return np.maximum(1e-4, Y_relit).astype(np.float32)


# ---------------------------------------------------------------------------
# 2. CONTINUOUS GEOMETRIC CONFIDENCE U_geometry(x)
# ---------------------------------------------------------------------------

def compute_geometric_confidence(depth: np.ndarray, normals: np.ndarray = None, tau_cliff: float = 0.04) -> np.ndarray:
    """
    Computes continuous geometric confidence U_geom in [0, 1].
    Evaluates depth gradients and camera grazing angles.
    """
    H, W = depth.shape
    d_min, d_max = float(np.min(depth)), float(np.max(depth))
    d_range = max(d_max - d_min, 1e-4)
    
    gx = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    g_mag = np.sqrt(gx**2 + gy**2)
    
    sigma_g = tau_cliff * d_range
    conf_depth = np.exp(- (g_mag ** 2) / (2.0 * (sigma_g ** 2) + 1e-6))
    
    if normals is not None:
        cos_cam = np.maximum(0.0, -normals[..., 2])
        conf_total = conf_depth * np.clip(cos_cam * 1.5, 0.0, 1.0)
    else:
        conf_total = conf_depth
        
    return np.clip(conf_total, 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 3. MULTI-SCALE AMBIENT OCCLUSION A_ambient(x)
# ---------------------------------------------------------------------------

def compute_component_A_ambient(depth: np.ndarray, normals: np.ndarray,
                                kappa_ao: float = 0.85) -> np.ndarray:
    """
    Multi-Scale Horizon-Based Ambient Occlusion (HBAO) in screen space:
    Combines fine horizon (r=6px for contact crevices) and coarse horizon (r=24px for geometry).
    Modulates ONLY indirect ambient fill floor.
    """
    H, W = depth.shape
    n_dirs = 8
    angles = np.linspace(0, 2 * math.pi, n_dirs, endpoint=False)
    dx_dirs = np.cos(angles)
    dy_dirs = np.sin(angles)
    
    radii_fine = np.array([2, 4, 6], dtype=np.float32)
    radii_coarse = np.array([8, 14, 24], dtype=np.float32)
    
    horizon_fine = np.zeros((H, W), dtype=np.float32)
    horizon_coarse = np.zeros((H, W), dtype=np.float32)
    y_idx, x_idx = np.mgrid[0:H, 0:W]
    
    for d in range(n_dirs):
        ux = dx_dirs[d]
        uy = dy_dirs[d]
        
        # Fine scale
        max_fine = np.zeros((H, W), dtype=np.float32)
        for r in radii_fine:
            nx = np.clip(np.round(x_idx + r * ux), 0, W - 1).astype(int)
            ny = np.clip(np.round(y_idx + r * uy), 0, H - 1).astype(int)
            dz = depth - depth[ny, nx]
            slope = (dz / (r * 0.03 + 1e-3)) * max(0.0, 1.0 - (r / 6.0)**2)
            max_fine = np.maximum(max_fine, np.clip(slope, 0.0, 1.0))
        horizon_fine += max_fine
        
        # Coarse scale
        max_coarse = np.zeros((H, W), dtype=np.float32)
        for r in radii_coarse:
            nx = np.clip(np.round(x_idx + r * ux), 0, W - 1).astype(int)
            ny = np.clip(np.round(y_idx + r * uy), 0, H - 1).astype(int)
            dz = depth - depth[ny, nx]
            slope = (dz / (r * 0.05 + 1e-3)) * max(0.0, 1.0 - (r / 24.0)**2)
            max_coarse = np.maximum(max_coarse, np.clip(slope, 0.0, 1.0))
        horizon_coarse += max_coarse
        
    mean_fine = cv2.GaussianBlur(horizon_fine / float(n_dirs), (3, 3), 0.8)
    mean_coarse = cv2.GaussianBlur(horizon_coarse / float(n_dirs), (5, 5), 1.2)
    
    combined_horizon = 0.40 * mean_fine + 0.60 * mean_coarse
    A_ambient = 1.0 - kappa_ao * combined_horizon
    return np.clip(A_ambient, 0.15, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 4. DIRECTIONAL CONTACT GROUNDING C_contact(x, L)
# ---------------------------------------------------------------------------

def compute_component_C_contact(depth: np.ndarray, normals: np.ndarray,
                                light_dir_3d: np.ndarray,
                                U_geom: np.ndarray,
                                fg_mask: np.ndarray,
                                ground_y: int,
                                contact_seam: tuple = None,
                                r_contact: int = 25) -> np.ndarray:
    """
    Directional Contact Grounding C_contact in [0.10, 1.0].
    Evaluates near-interface raymarching along projected light vector.
    """
    H, W = depth.shape
    C_contact = np.ones((H, W), dtype=np.float32)
    
    lx, ly = light_dir_3d[0], -light_dir_3d[1]
    norm_l = math.sqrt(lx * lx + ly * ly)
    if norm_l < 1e-4:
        u_lx, u_ly = 0.0, -1.0
    else:
        u_lx, u_ly = lx / norm_l, ly / norm_l
        
    receiver_region = np.zeros((H, W), dtype=bool)
    if ground_y is not None and 0 <= ground_y < H:
        receiver_region[max(0, ground_y - 10):, :] = True
    else:
        receiver_region = (~fg_mask)
        
    y_idx, x_idx = np.mgrid[0:H, 0:W]
    steps = np.linspace(1.5, r_contact, 8, dtype=np.float32)
    occlusion_acc = np.zeros((H, W), dtype=np.float32)
    weight_sum = 0.0
    
    for s in steps:
        # Step towards the caster (opposite of shadow travel)
        qx = np.clip(np.round(x_idx + s * u_lx), 0, W - 1).astype(int)
        qy = np.clip(np.round(y_idx + s * u_ly), 0, H - 1).astype(int)
        
        sample_depth = depth[qy, qx]
        delta_z = depth - sample_depth
        valid_contact_depth = (delta_z > -0.05) & (delta_z < 0.25)
        is_caster = fg_mask[qy, qx] & valid_contact_depth
        
        w_dist = (1.0 - (s / float(r_contact))) ** 2
        weight_sum += w_dist
        occlusion_acc += np.where(is_caster, w_dist * U_geom[qy, qx], 0.0)
        
    norm_occ = occlusion_acc / max(weight_sum, 1e-4)
    receiver_occ = norm_occ * receiver_region.astype(np.float32)
    
    # Contact seam reinforcement at verified ground contact interface
    if contact_seam is not None and contact_seam[0] is not None:
        cy = contact_seam[0]
        y_dist = np.abs(y_idx - cy)
        seam_band = (y_dist <= 2) & receiver_region
        seam_mask = np.where(seam_band, 1.0 - (y_dist / 2.0), 0.0)
        if np.any(fg_mask[max(0, cy - 4):min(H, cy + 4), :]):
            fg_x = np.where(np.any(fg_mask[max(0, cy - 4):min(H, cy + 4), :], axis=0))[0]
            if len(fg_x) > 0:
                xmin, xmax = np.min(fg_x) - 5, np.max(fg_x) + 5
                seam_mask[:, :max(0, xmin)] = 0.0
                seam_mask[:, min(W, xmax):] = 0.0
                receiver_occ = np.maximum(receiver_occ, seam_mask * 0.90)
                
    C_contact = 1.0 - 0.90 * receiver_occ
    return np.clip(C_contact, 0.10, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 5. DIFFUSE SURFACE ORIENTATION D_diffuse(x, L)
# ---------------------------------------------------------------------------

def compute_component_D_diffuse(normals: np.ndarray, light_dir_3d: np.ndarray) -> np.ndarray:
    """Hermite-tapered Lambertian cosine response in [0, 1]."""
    ld = light_dir_3d / np.linalg.norm(light_dir_3d)
    cos_theta = np.sum(normals * ld, axis=-1)
    
    t0, t1 = -0.05, 0.10
    u = np.clip((cos_theta - t0) / (t1 - t0), 0.0, 1.0)
    smooth_weight = u * u * (3.0 - 2.0 * u)
    D_diffuse = smooth_weight * np.maximum(0.0, cos_theta)
    return np.clip(D_diffuse, 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 6. DIRECT SELF-OCCLUSION V_self(x, L)
# ---------------------------------------------------------------------------

def compute_component_V_self(depth: np.ndarray, normals: np.ndarray,
                             fg_mask: np.ndarray, light_dir_3d: np.ndarray,
                             U_geom: np.ndarray, n_steps: int = 16,
                             max_step_dist: float = 30.0) -> np.ndarray:
    """
    Evaluates screen-space self-occlusion V_self in [0, 1] on foreground geometry.
    Marches rays towards the light source (+Lx, -Ly) in screen space.
    """
    H, W = depth.shape
    V_self = np.ones((H, W), dtype=np.float32)
    
    # Vector pointing TOWARDS light source
    lx, ly = light_dir_3d[0], -light_dir_3d[1]
    norm_l = math.sqrt(lx * lx + ly * ly)
    if norm_l < 1e-4:
        return V_self
    u_lx, u_ly = lx / norm_l, ly / norm_l
    
    y_idx, x_idx = np.mgrid[0:H, 0:W]
    steps = np.linspace(4.0, max_step_dist, n_steps, dtype=np.float32)
    occluded_acc = np.zeros((H, W), dtype=np.float32)
    
    for s in steps:
        sx = np.clip(np.round(x_idx + s * u_lx), 0, W - 1).astype(int)
        sy = np.clip(np.round(y_idx + s * u_ly), 0, H - 1).astype(int)
        
        # Ray ascends towards light as it marches towards camera in screen space
        expected_ray_depth = depth - s * 0.012
        sample_depth = depth[sy, sx]
        depth_diff = expected_ray_depth - sample_depth
        
        # Protrusion occluder check: occluder must be a separate feature in front of ray
        # Prevents smooth convex curvature from self-shadowing its own lit face
        is_occluding = (depth_diff > 0.03) & (depth_diff < 0.25) & fg_mask[sy, sx]
        occluded_acc = np.maximum(occluded_acc, np.where(is_occluding & (U_geom[sy, sx] > 0.5), 1.0, 0.0))
        
    occluded_soft = cv2.GaussianBlur(occluded_acc, (3, 3), 0.8)
    V_self = np.where(fg_mask, 1.0 - 0.85 * occluded_soft, 1.0)
    return np.clip(V_self, 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 7. PROXY CAST SHADOW WITH LIT-SIDE BLEED GUARD V_cast(x, L)
# ---------------------------------------------------------------------------

def compute_component_V_cast(depth: np.ndarray, fg_mask: np.ndarray,
                             light_dir_3d: np.ndarray, ground_y: int,
                             source_radius: float = 0.06) -> np.ndarray:
    """
    Computes proxy cast shadow V_cast in [0.15, 1.0].
    Projects foreground silhouette onto receiver plane with distance-dependent penumbra.
    Enforces a strict lit-side half-space bleed guard to completely eliminate silhouette leakage (SLR).
    """
    H, W = depth.shape
    V_cast = np.ones((H, W), dtype=np.float32)
    
    if not np.any(fg_mask):
        return V_cast
        
    fy, fx = np.where(fg_mask)
    if len(fx) == 0:
        return V_cast
        
    if ground_y is None:
        ground_y = int(np.max(fy))
        
    cx_base = float(np.mean(fx))
    h_elev = np.maximum(0.0, ground_y - fy.astype(np.float32))
    
    lx, ly, lz = light_dir_3d[0], light_dir_3d[1], light_dir_3d[2]
    denom_y = max(ly, 0.15)
    
    # Calibrated perspective projection
    scale_x = 0.77
    scale_z = 0.45
    proj_x = fx - h_elev * (lx / denom_y) * scale_x
    proj_y = ground_y - h_elev * (lz / denom_y) * scale_z
    
    valid_pts = (proj_x >= 0) & (proj_x < W) & (proj_y >= 0) & (proj_y < H)
    px = np.clip(np.round(proj_x[valid_pts]), 0, W - 1).astype(int)
    py = np.clip(np.round(proj_y[valid_pts]), 0, H - 1).astype(int)
    
    footprint = np.zeros((H, W), dtype=np.float32)
    footprint[py, px] = 1.0
    
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    footprint_closed = cv2.morphologyEx(footprint, cv2.MORPH_CLOSE, kernel)
    
    # Distance-dependent penumbra
    cast_dist_1d = np.abs(np.arange(H, dtype=np.float32) - ground_y)
    sigma_near = 2.0
    mean_dist = float(np.mean(cast_dist_1d[py])) if len(py) > 0 else 10.0
    sigma_far = max(4.0, mean_dist * (source_radius * 1.5))
    
    blur_near = cv2.GaussianBlur(footprint_closed, (0, 0), sigma_near)
    blur_far = cv2.GaussianBlur(footprint_closed, (0, 0), sigma_far)
    
    max_d = max(1.0, float(np.max(cast_dist_1d[py])) if len(py) > 0 else 10.0)
    t_dist = np.clip(cast_dist_1d[:, None] / max_d, 0.0, 1.0)
    shadow_density = (1.0 - t_dist) * blur_near + t_dist * blur_far
    
    # SLR Prevention: Lit-side half-space bleed guard
    # Shadow must fall along -lx direction relative to caster base.
    # The half-space (x - cx_base) * lx > 8px is physically illuminated and cannot receive cast shadow.
    y_idx, x_idx = np.mgrid[0:H, 0:W]
    dx = x_idx - cx_base
    is_lit_side = (dx * lx > 8.0) & (y_idx >= ground_y - 15)
    shadow_density_guarded = np.where(is_lit_side & (footprint_closed < 0.1), 0.0, shadow_density)
    
    # Mask strictly outside foreground
    receiver_area = (~fg_mask)
    V_cast[receiver_area] = 1.0 - 0.85 * np.clip(shadow_density_guarded[receiver_area], 0.0, 1.0)
    return np.clip(V_cast, 0.15, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 8. CORRECTED ADDITIVE RADIANCE COMPOSITING CONTRACT
# ---------------------------------------------------------------------------

def execute_candidate_light_transport(
    image_lin: np.ndarray,
    depth: np.ndarray,
    normals: np.ndarray,
    fg_mask: np.ndarray,
    light_dir_3d: np.ndarray,
    ground_y: int,
    contact_seam: tuple = None,
    source_radius: float = 0.06,
    r_ambient: float = 0.15,
    r_key: float = 1.0,
    # Ablation toggles
    enable_ao: bool = True,
    enable_contact: bool = True,
    enable_diffuse: bool = True,
    enable_self: bool = True,
    enable_cast: bool = True,
    enable_confidence: bool = True,
    confidence_fallback: bool = True
) -> dict:
    """
    Executes the fully decoupled 7-term light transport engine according to
    RS-SPEC-SPIKE-2.2-ARCHITECTURE.md.
    """
    H, W = depth.shape
    
    # 1. Geometric Confidence U_geom
    if enable_confidence:
        U_geom = compute_geometric_confidence(depth, normals, tau_cliff=0.04)
    else:
        U_geom = np.ones((H, W), dtype=np.float32)
        
    # 2. Ambient Visibility A_ambient (modulates indirect fill floor ONLY)
    if enable_ao:
        A_ambient = compute_component_A_ambient(depth, normals, kappa_ao=0.85)
    else:
        A_ambient = np.ones((H, W), dtype=np.float32)
        
    # 3. Contact Grounding C_contact (directional near-field direct visibility)
    if enable_contact:
        C_contact = compute_component_C_contact(
            depth, normals, light_dir_3d, U_geom, fg_mask, ground_y, contact_seam, r_contact=25
        )
    else:
        C_contact = np.ones((H, W), dtype=np.float32)
        
    # 4. Diffuse Surface Orientation D_diffuse
    if enable_diffuse:
        D_diffuse = compute_component_D_diffuse(normals, light_dir_3d)
    else:
        D_diffuse = np.ones((H, W), dtype=np.float32)
        
    # 5. Direct Self-Occlusion V_self
    if enable_self:
        V_self = compute_component_V_self(
            depth, normals, fg_mask, light_dir_3d, U_geom, n_steps=16, max_step_dist=30.0
        )
    else:
        V_self = np.ones((H, W), dtype=np.float32)
        
    # 6. Perspective Proxy Cast Shadow V_cast
    if enable_cast:
        V_cast = compute_component_V_cast(
            depth, fg_mask, light_dir_3d, ground_y, source_radius=source_radius
        )
    else:
        V_cast = np.ones((H, W), dtype=np.float32)
        
    # 7. Unified Direct Visibility V_direct
    # On Foreground: V_direct = V_self
    # On Receiver: V_direct = min(V_cast, C_contact) -> geometric union without double counting
    V_direct = np.ones((H, W), dtype=np.float32)
    receiver_area = (~fg_mask)
    V_direct[fg_mask] = V_self[fg_mask]
    V_direct[receiver_area] = np.minimum(V_cast[receiver_area], C_contact[receiver_area])
    
    # 8. Corrected Additive Radiance Decomposition
    Y_orig = linear_to_luminance(image_lin)
    
    # Base luminance decomposition for E.1
    logY = np.log(np.maximum(Y_orig, 1e-4))
    r0, eps0 = 16, 0.02**2
    B = guided_filter(Y_orig, logY, r0, eps0)
    D = logY - B
    Yb = np.exp(B)
    
    # Indirect Ambient Radiance: modulates ONLY fill floor (C_contact is NOT in ambient!)
    Y_indirect = Yb * r_ambient * A_ambient
    
    # Direct Key Radiance: modulated by orientation and direct visibility
    Y_direct = Yb * (r_key - r_ambient) * D_diffuse * V_direct
    
    # Relit Target Luminance
    Y_relit_target = Y_indirect + Y_direct
    
    # Shading ratio target
    R_target = Y_relit_target / np.maximum(Yb, 1e-4)
    
    # Highlight protection shoulder
    M_high = np.clip((Y_orig - 0.75) / (0.98 - 0.75), 0.0, 1.0)
    M_high = M_high * M_high * (3.0 - 2.0 * M_high)
    R_eff = (1.0 - M_high) * R_target + M_high * 1.0
    
    # Downstream detail preservation via Spike 1 E.1 Guided-Filter Regularization
    Y_relit = paradigm_E1(Y_orig, R_eff, guide=Y_orig)
    
    # Gamut mapping via Spike 1 C3 Oklab 16-step constant-hue bisection
    relit_rgb = color_reconstruct_C3(image_lin, Y_orig, Y_relit)
    
    return {
        "relit_rgb": relit_rgb,
        "Y_relit": Y_relit,
        "Y_orig": Y_orig,
        "V_direct": V_direct,
        "A_ambient": A_ambient,
        "C_contact": C_contact,
        "D_diffuse": D_diffuse,
        "V_self": V_self,
        "V_cast": V_cast,
        "U_geom": U_geom,
        "Y_indirect": Y_indirect,
        "Y_direct": Y_direct,
        "R_eff": R_eff
    }
