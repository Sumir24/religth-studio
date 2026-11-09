"""
RELIGHT STUDIO — SPIKE 2.1: CANDIDATE 2.5D SHADOW TRANSPORT ENGINE
===================================================================
Document Reference: RS-SPEC-SPIKE-2.1-CORRECTED-ARCHITECTURE.md
Strict Isolation Mode: Completely decoupled from engine/relighter_v4.py and Spike 2.

Implements the Seven Decoupled Physical Lighting Terms:
  1. Direct Light Visibility: V_direct(x, L)
  2. Ambient Visibility: A_ambient(x)
  3. Contact Grounding: C_contact(x, L)
  4. Diffuse Orientation: D_diffuse(x, L)
  5. Self-Occlusion: V_self(x, L)
  6. Cast Shadow Visibility: V_cast(x, L)
  7. Geometric Confidence: U_geometry(x)

And the Additive Radiance Compositing Contract:
  Y_indirect = Y_b * R_ambient * A_ambient * C_contact
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
    """He et al. 2013 edge-preserving Guided Filter."""
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
# 2. GEOMETRIC CONFIDENCE & DEPTH CLIFF DETECTOR U_geometry
# ---------------------------------------------------------------------------

def compute_geometric_confidence(depth: np.ndarray, tau_cliff: float = 0.04) -> np.ndarray:
    """
    Computes spatial geometric confidence U_geometry in [0, 1].
    Identifies depth cliffs using normalized 3x3 Sobel gradients.
    Dilates cliff mask with a 3x3 kernel to cover boundary blur.
    Returns 0.0 at depth discontinuities and 1.0 on continuous surfaces.
    """
    H, W = depth.shape
    d_min, d_max = float(np.min(depth)), float(np.max(depth))
    d_range = max(d_max - d_min, 1e-4)
    
    # Normalized Sobel gradients
    gx = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    gy = cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    g_mag = np.sqrt(gx**2 + gy**2)
    
    # Cliff threshold relative to depth range
    cliff_mask = (g_mag > (tau_cliff * d_range)).astype(np.uint8)
    
    # Dilate 3x3 to cover transition
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated_cliff = cv2.dilate(cliff_mask, kernel, iterations=1)
    
    U_geom = 1.0 - dilated_cliff.astype(np.float32)
    return np.clip(U_geom, 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 3. COMPONENT 1: AMBIENT OCCLUSION A_ambient(x)
# ---------------------------------------------------------------------------

def compute_component_A_ambient(depth: np.ndarray, normals: np.ndarray,
                                r_ao: int = 24, n_dirs: int = 8,
                                kappa_ao: float = 0.85) -> np.ndarray:
    """
    Computes Horizon-Based Ambient Occlusion (HBAO) in screen space.
    Evaluates radial horizon angles with distance falloff W(r) = max(0, 1 - (r/r_ao)^2).
    A_ambient modulates ONLY the indirect ambient fill floor in [0.15, 1.0].
    """
    H, W = depth.shape
    # Generate 8 radial direction vectors
    angles = np.linspace(0, 2 * math.pi, n_dirs, endpoint=False)
    dx_dirs = np.cos(angles)
    dy_dirs = np.sin(angles)
    
    # Step radii along each ray (geometric distribution)
    sample_radii = np.array([3, 6, 11, 17, 24], dtype=np.float32)
    sample_radii = sample_radii[sample_radii <= r_ao]
    
    horizon_acc = np.zeros((H, W), dtype=np.float32)
    
    y_idx, x_idx = np.mgrid[0:H, 0:W]
    
    for d in range(n_dirs):
        u_x = dx_dirs[d]
        u_y = dy_dirs[d]
        max_sin_theta = np.zeros((H, W), dtype=np.float32)
        
        for r in sample_radii:
            nx = np.clip(np.round(x_idx + r * u_x), 0, W - 1).astype(int)
            ny = np.clip(np.round(y_idx + r * u_y), 0, H - 1).astype(int)
            
            sample_depth = depth[ny, nx]
            delta_z = depth - sample_depth  # positive if sample is closer to camera (occluding)
            
            falloff = max(0.0, 1.0 - (r / float(r_ao))**2)
            slope = (delta_z / (r * 0.05 + 1e-3)) * falloff
            max_sin_theta = np.maximum(max_sin_theta, np.clip(slope, 0.0, 1.0))
            
        horizon_acc += max_sin_theta
        
    mean_horizon = horizon_acc / float(n_dirs)
    # Screen-space blur to smooth sampling noise
    mean_horizon = cv2.GaussianBlur(mean_horizon, (5, 5), 1.2)
    
    A_ambient = 1.0 - kappa_ao * mean_horizon
    return np.clip(A_ambient, 0.15, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 4. COMPONENT 2: CONTACT GROUNDING C_contact(x, L)
# ---------------------------------------------------------------------------

def compute_component_C_contact(depth: np.ndarray, normals: np.ndarray,
                                light_dir_3d: np.ndarray,
                                U_geom: np.ndarray,
                                fg_mask: np.ndarray,
                                ground_y: int,
                                contact_seam: tuple = None,
                                r_contact: int = 25) -> np.ndarray:
    """
    Computes Contact Grounding C_contact in [0.10, 1.0].
    Performs bounded screen-space raymarching along projected light vector u_L.
    Suppressed by U_geometry at depth cliffs to eliminate halo bleeding.
    Enforces anchor grounding at zero-distance contact interfaces.
    """
    H, W = depth.shape
    C_contact = np.ones((H, W), dtype=np.float32)
    
    # 2D projected light direction in screen coordinates
    lx, ly = light_dir_3d[0], -light_dir_3d[1]
    norm_l = math.sqrt(lx * lx + ly * ly)
    if norm_l < 1e-4:
        u_lx, u_ly = 0.0, -1.0
    else:
        u_lx, u_ly = lx / norm_l, ly / norm_l
        
    # Receiver region: pixels on floor or near base
    receiver_region = np.zeros((H, W), dtype=bool)
    if ground_y is not None and 0 <= ground_y < H:
        receiver_region[max(0, ground_y - 10):, :] = True
        
    y_idx, x_idx = np.mgrid[0:H, 0:W]
    
    # Bounded march: sample 8 steps up to r_contact
    steps = np.linspace(2, r_contact, 8, dtype=np.float32)
    occlusion_acc = np.zeros((H, W), dtype=np.float32)
    weight_sum = 0.0
    
    for s in steps:
        # Step back towards the caster (opposite of shadow direction)
        qx = np.clip(np.round(x_idx - s * u_lx), 0, W - 1).astype(int)
        qy = np.clip(np.round(y_idx - s * u_ly), 0, H - 1).astype(int)
        
        # Caster depth sample
        sample_depth = depth[qy, qx]
        delta_z = depth - sample_depth # positive if caster is in front
        
        # Bounded depth tolerance: contact requires close z-proximity (< 0.25 depth range)
        valid_contact_depth = (delta_z > -0.05) & (delta_z < 0.25)
        is_caster = fg_mask[qy, qx] & valid_contact_depth
        
        w_dist = (1.0 - (s / float(r_contact))) ** 2
        weight_sum += w_dist
        
        # Accumulate occlusion on receiver, modulated by caster confidence
        occlusion_acc += np.where(is_caster, w_dist * U_geom[qy, qx], 0.0)
        
    norm_occ = occlusion_acc / max(weight_sum, 1e-4)
    # Apply to receiver region and near-base zone
    receiver_occ = norm_occ * receiver_region.astype(np.float32)
    
    # Base contact seam reinforcement
    if contact_seam is not None and contact_seam[0] is not None:
        cy = contact_seam[0]
        seam_mask = np.zeros((H, W), dtype=np.float32)
        y_dist = np.abs(y_idx - cy)
        seam_band = (y_dist <= 3) & receiver_region
        seam_mask[seam_band] = 1.0 - (y_dist[seam_band] / 3.0)
        
        # Find horizontal extent of foreground at seam
        if np.any(fg_mask[max(0, cy - 5):min(H, cy + 5), :]):
            fg_x = np.where(np.any(fg_mask[max(0, cy - 5):min(H, cy + 5), :], axis=0))[0]
            if len(fg_x) > 0:
                xmin, xmax = np.min(fg_x) - 10, np.max(fg_x) + 10
                seam_mask[:, :max(0, xmin)] = 0.0
                seam_mask[:, min(W, xmax):] = 0.0
                receiver_occ = np.maximum(receiver_occ, seam_mask * 0.90)
                
    C_contact = 1.0 - 0.90 * receiver_occ
    C_contact = np.clip(C_contact, 0.10, 1.0).astype(np.float32)
    return C_contact


# ---------------------------------------------------------------------------
# 5. COMPONENT 3: DIFFUSE SURFACE ORIENTATION D_diffuse(x, L)
# ---------------------------------------------------------------------------

def compute_component_D_diffuse(normals: np.ndarray, light_dir_3d: np.ndarray) -> np.ndarray:
    """
    Computes local Lambertian cosine response D_diffuse with Hermite terminator taper.
    Smooths terminator boundary in [-0.05, 0.10] to eliminate knife-edge raster tearing.
    D_diffuse is a radiometric surface orientation term, NOT a visibility term.
    """
    ld = light_dir_3d / np.linalg.norm(light_dir_3d)
    cos_theta = np.sum(normals * ld, axis=-1)
    
    # Smooth Hermite transition around terminator: t in [-0.05, 0.10]
    t0, t1 = -0.05, 0.10
    u = np.clip((cos_theta - t0) / (t1 - t0), 0.0, 1.0)
    smooth_weight = u * u * (3.0 - 2.0 * u)
    
    # Tapered cosine response
    D_diffuse = smooth_weight * np.maximum(0.0, cos_theta)
    return np.clip(D_diffuse, 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 6. COMPONENT 4: DIRECTIONAL SELF-OCCLUSION V_self(x, L)
# ---------------------------------------------------------------------------

def compute_component_V_self(depth: np.ndarray, normals: np.ndarray,
                             fg_mask: np.ndarray, light_dir_3d: np.ndarray,
                             U_geom: np.ndarray, n_steps: int = 16,
                             max_step_dist: float = 30.0) -> np.ndarray:
    """
    Computes screen-space self-occlusion V_self in [0, 1] on foreground geometry.
    Marches rays toward the light direction (-Lx, Ly) in screen space.
    Detects when recessed surfaces facing the light are occluded by foreground protrusions.
    Suppressed by U_geometry across depth cliffs.
    """
    H, W = depth.shape
    V_self = np.ones((H, W), dtype=np.float32)
    
    # Projected screen-space vector pointing TOWARDS light source
    lx, ly = -light_dir_3d[0], light_dir_3d[1]
    norm_l = math.sqrt(lx * lx + ly * ly)
    if norm_l < 1e-4:
        return V_self
    u_lx, u_ly = lx / norm_l, ly / norm_l
    
    # Elevation slope in depth per pixel
    lz_slope = light_dir_3d[2] / norm_l
    
    y_idx, x_idx = np.mgrid[0:H, 0:W]
    fg_indices = np.where(fg_mask)
    if len(fg_indices[0]) == 0:
        return V_self
        
    steps = np.linspace(2.0, max_step_dist, n_steps, dtype=np.float32)
    occluded_acc = np.zeros((H, W), dtype=np.float32)
    
    for s in steps:
        sx = np.clip(np.round(x_idx + s * u_lx), 0, W - 1).astype(int)
        sy = np.clip(np.round(y_idx + s * u_ly), 0, H - 1).astype(int)
        
        # Ray depth: ray ascends toward the light in front of surface
        expected_ray_depth = depth - s * lz_slope * 0.01
        sample_depth = depth[sy, sx]
        
        # Occluder is closer to camera than ray AND part of foreground
        # Guard against depth cliffs (cliff confidence must be high)
        depth_diff = expected_ray_depth - sample_depth
        is_occluding = (sample_depth < expected_ray_depth - 0.015) & (depth_diff < 0.20) & fg_mask[sy, sx]
        
        occluded_acc = np.maximum(occluded_acc, np.where(is_occluding & (U_geom[sy, sx] > 0.5), 1.0, 0.0))
        
    # Soften self-shadow edge
    occluded_soft = cv2.GaussianBlur(occluded_acc, (3, 3), 0.8)
    V_self = np.where(fg_mask, 1.0 - 0.85 * occluded_soft, 1.0)
    return np.clip(V_self, 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 7. COMPONENT 5: CAST SHADOW VISIBILITY V_cast(x, L)
# ---------------------------------------------------------------------------

def compute_component_V_cast(depth: np.ndarray, fg_mask: np.ndarray,
                             light_dir_3d: np.ndarray, ground_y: int,
                             source_radius: float = 0.06,
                             receiver_normal: np.ndarray = None) -> np.ndarray:
    """
    Computes receiver proxy projected cast shadow V_cast in [0.15, 1.0].
    Projects foreground silhouette onto receiver plane with distance-dependent penumbra.
    Distance-dependent penumbra width sigma(d) = max(sigma_min, d_cast * omega_source).
    Evaluated strictly on receiver region x not in Omega_fg.
    """
    H, W = depth.shape
    V_cast = np.ones((H, W), dtype=np.float32)
    
    if ground_y is None or ground_y >= H or not np.any(fg_mask):
        return V_cast
        
    lx, ly, lz = light_dir_3d[0], light_dir_3d[1], light_dir_3d[2]
    # Denominator clamped to avoid infinite extrusion at grazing angles
    denom_y = max(ly, 0.15)
    
    # Extract foreground pixel coordinates
    fy, fx = np.where(fg_mask)
    if len(fx) == 0:
        return V_cast
        
    # Height elevation above receiver line in 2D/2.5D space
    h_elev = np.maximum(0.0, ground_y - fy.astype(np.float32))
    
    # 2.5D proxy projection mapping
    # Floor projection: light travels along -L, so shadow shifts along -Lx and -Lz
    scale_x = 0.77
    scale_z = 0.45
    proj_x = fx - h_elev * (lx / denom_y) * scale_x
    proj_y = ground_y - h_elev * (lz / denom_y) * scale_z
    
    valid_pts = (proj_x >= 0) & (proj_x < W) & (proj_y >= 0) & (proj_y < H)
    px = np.clip(np.round(proj_x[valid_pts]), 0, W - 1).astype(int)
    py = np.clip(np.round(proj_y[valid_pts]), 0, H - 1).astype(int)
    
    # Rasterize silhouette footprint
    footprint = np.zeros((H, W), dtype=np.float32)
    footprint[py, px] = 1.0
    
    # Close single-pixel raster gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    footprint_closed = cv2.morphologyEx(footprint, cv2.MORPH_CLOSE, kernel)
    
    # Distance-dependent penumbra: average caster height contributing to shadow
    # Near contact: small sigma; Far field: large sigma
    cast_dist_1d = np.abs(np.arange(H, dtype=np.float32) - ground_y)
    
    # Multi-band penumbral simulation: combine near-field sharp and far-field soft
    sigma_near = 2.0
    mean_dist = float(np.mean(cast_dist_1d[py])) if len(py) > 0 else 10.0
    sigma_far = max(4.0, mean_dist * (source_radius * 1.5))
    
    blur_near = cv2.GaussianBlur(footprint_closed, (0, 0), sigma_near)
    blur_far = cv2.GaussianBlur(footprint_closed, (0, 0), sigma_far)
    
    # Blend near and far blur based on distance from ground line
    max_d = max(1.0, float(np.max(cast_dist_1d[py])) if len(py) > 0 else 10.0)
    t_dist = np.clip(cast_dist_1d[:, None] / max_d, 0.0, 1.0)
    shadow_density = (1.0 - t_dist) * blur_near + t_dist * blur_far
    
    # Receiver mask: strictly outside foreground
    receiver_area = (~fg_mask)
    
    # Invert to visibility [0.15, 1.0]
    V_cast[receiver_area] = 1.0 - 0.85 * np.clip(shadow_density[receiver_area], 0.0, 1.0)
    return np.clip(V_cast, 0.15, 1.0).astype(np.float32)


# ---------------------------------------------------------------------------
# 8. ADDITIVE RADIANCE COMPOSITING CONTRACT
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
    RS-SPEC-SPIKE-2.1-CORRECTED-ARCHITECTURE.md.
    """
    H, W = depth.shape
    
    # 1. Geometric Confidence U_geometry
    if enable_confidence:
        U_geom = compute_geometric_confidence(depth, tau_cliff=0.04)
    else:
        U_geom = np.ones((H, W), dtype=np.float32)
        
    # 2. Ambient Visibility A_ambient (modulates indirect floor only)
    if enable_ao:
        A_ambient = compute_component_A_ambient(depth, normals, r_ao=24, n_dirs=8, kappa_ao=0.85)
    else:
        A_ambient = np.ones((H, W), dtype=np.float32)
        
    # 3. Contact Grounding C_contact
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
        
    # 6. Cast Shadow Visibility V_cast
    if enable_cast:
        V_cast = compute_component_V_cast(
            depth, fg_mask, light_dir_3d, ground_y, source_radius=source_radius
        )
    else:
        V_cast = np.ones((H, W), dtype=np.float32)
        
    # 7. Unified Direct Visibility V_direct
    # On Foreground: V_direct = V_self
    # On Receiver: V_direct = min(V_cast, C_contact) -> physical union without double-counting
    V_direct = np.ones((H, W), dtype=np.float32)
    receiver_area = (~fg_mask)
    V_direct[fg_mask] = V_self[fg_mask]
    V_direct[receiver_area] = np.minimum(V_cast[receiver_area], C_contact[receiver_area])
    
    # 8. Additive Radiance Decomposition
    Y_orig = linear_to_luminance(image_lin)
    
    # Guided filter base decomposition for E.1
    logY = np.log(np.maximum(Y_orig, 1e-4))
    r0, eps0 = 16, 0.02**2
    B = guided_filter(Y_orig, logY, r0, eps0)
    D = logY - B
    Yb = np.exp(B)
    
    # Indirect Ambient Radiance: modulates ONLY fill floor
    Y_indirect = Yb * r_ambient * A_ambient * C_contact
    
    # Direct Key Radiance: modulated by orientation and visibility
    Y_direct = Yb * (r_key - r_ambient) * D_diffuse * V_direct
    
    # Relit Target Luminance
    Y_relit_target = Y_indirect + Y_direct
    
    # Shading ratio target
    R_target = Y_relit_target / np.maximum(Yb, 1e-4)
    
    # Highlight protection shoulder (Spike 1 standard)
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
