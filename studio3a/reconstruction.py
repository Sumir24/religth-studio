"""
RELIGHT STUDIO — RS-SPIKE-3A: NON-DESTRUCTIVE IMAGE RECONSTRUCTION
===================================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Strict Invariant: The original photograph is completely immutable.
Preserves high-frequency texture via E.1 Guided-Filter Log-Ratio Regularization
and guarantees gamut safety via C3 Oklab Constant-Hue Chroma Reduction.
"""

from __future__ import annotations

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# 1. COLOR SPACE TRANSFORMATIONS
# ---------------------------------------------------------------------------

LUMA_WEIGHTS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

M1_SRGB_TO_LMS = np.array([
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005]
], dtype=np.float32).T

M2_LMS_TO_OKLAB = np.array([
    [0.2104542553,  0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050,  0.4505937099],
    [0.0259040371,  0.7827717662, -0.8086757660]
], dtype=np.float32).T

M2_INV = np.linalg.inv(M2_LMS_TO_OKLAB.T).T
M1_INV = np.linalg.inv(M1_SRGB_TO_LMS.T).T


def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    """Converts sRGB image in [0, 1] to Linear sRGB."""
    x = np.clip(x.astype(np.float32), 0.0, None)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(x: np.ndarray) -> np.ndarray:
    """Converts Linear sRGB image to display sRGB in [0, 1]."""
    x = np.clip(x.astype(np.float32), 0.0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * (x ** (1.0 / 2.4)) - 0.055).astype(np.float32)


def linear_to_luminance(rgb_lin: np.ndarray) -> np.ndarray:
    """Computes photometric luminance Y from linear RGB."""
    return np.sum(rgb_lin * LUMA_WEIGHTS, axis=-1).astype(np.float32)


def rgb_to_oklab(rgb_lin: np.ndarray) -> np.ndarray:
    lms = np.maximum(0.0, rgb_lin @ M1_SRGB_TO_LMS)
    lms_cubed = lms ** (1.0 / 3.0)
    return (lms_cubed @ M2_LMS_TO_OKLAB).astype(np.float32)


def oklab_to_rgb(oklab: np.ndarray) -> np.ndarray:
    lms = np.maximum(0.0, oklab @ M2_INV)
    lms_cubed = lms ** 3.0
    return (lms_cubed @ M1_INV).astype(np.float32)


# ---------------------------------------------------------------------------
# 2. GUIDED FILTER & E.1 REGULARIZATION
# ---------------------------------------------------------------------------

def box_filter(img: np.ndarray, r: int) -> np.ndarray:
    return cv2.boxFilter(img, ddepth=-1, ksize=(2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REFLECT)


def guided_filter(guide: np.ndarray, src: np.ndarray, r: int = 16, eps: float = 0.02**2) -> np.ndarray:
    """Standard fast guided filter for edge-preserving smoothing."""
    mean_I = box_filter(guide, r)
    mean_p = box_filter(src, r)
    mean_Ip = box_filter(guide * src, r)
    cov_Ip = mean_Ip - mean_I * mean_p

    mean_II = box_filter(guide * guide, r)
    var_I = mean_II - mean_I * mean_I

    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I

    mean_a = box_filter(a, r)
    mean_b = box_filter(b, r)

    return (mean_a * guide + mean_b).astype(np.float32)


def color_reconstruct_C3(
    image_lin: np.ndarray,
    Y_orig: np.ndarray,
    Y_relit: np.ndarray,
    n_bisection_steps: int = 8
) -> np.ndarray:
    """
    C3 Gamut Mapping: Oklab Constant-Hue Chroma Reduction.
    Guarantees zero hue drift and displayable sRGB gamut bounds [0, 1].
    """
    scale = (Y_relit / np.maximum(Y_orig, 1e-6))[..., None]
    ref_rgb = image_lin * scale
    oklab_ref = rgb_to_oklab(ref_rgb)
    oklab_orig = rgb_to_oklab(image_lin)

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

    for _ in range(n_bisection_steps):
        t_mid = 0.5 * (t_low + t_high)
        cand_ok = np.stack([L_disp, a_init * t_mid, b_init * t_mid], axis=-1)
        rgb_mid = oklab_to_rgb(cand_ok)
        in_g = np.all((rgb_mid >= -1e-4) & (rgb_mid <= 1.0001), axis=-1)
        t_low = np.where(in_g, t_mid, t_low)
        t_high = np.where(in_g, t_high, t_mid)

    final_t = np.where(needs_mapping, t_low, 1.0)
    final_oklab = np.stack([L_disp, a_init * final_t, b_init * final_t], axis=-1)
    final_rgb = np.clip(oklab_to_rgb(final_oklab), 0.0, 1.0).astype(np.float32)
    return final_rgb


# ---------------------------------------------------------------------------
# 3. RECONSTRUCTION PIPELINE
# ---------------------------------------------------------------------------

class ReconstructionEngine:
    """
    Non-destructive image relighting reconstruction engine.
    Ensures that original photograph texture is preserved and protected regions are untouched.
    """
    def __init__(self, r_filter: int = 16, eps_filter: float = 0.02**2):
        self.r_filter = r_filter
        self.eps_filter = eps_filter

    def reconstruct_relit_image(
        self,
        image_orig_srgb: np.ndarray,
        direct_irradiance: np.ndarray,
        direct_visibility: Optional[np.ndarray] = None,
        ambient_fill: float = 0.15,
        protected_mask: Optional[np.ndarray] = None
    ) -> dict[str, np.ndarray]:
        """
        Executes end-to-end reconstruction from original photograph.
        Args:
            image_orig_srgb: (H, W, 3) original photograph in display sRGB [0, 1].
            direct_irradiance: (H, W, 3) linear direct lighting irradiance from 3D area light(s).
            direct_visibility: Optional (H, W) geometric shadow visibility in [0, 1].
            ambient_fill: Ambient indirect light baseline fraction.
            protected_mask: (H, W) boolean mask of regions that must NEVER be modified.
        Returns:
            Dictionary with relit_srgb, relit_linear, shading_ratio, and diagnostics.
        """
        image_lin = srgb_to_linear(image_orig_srgb)
        Y_orig = linear_to_luminance(image_lin)
        
        # 1. Base / Detail Luminance Decomposition
        logY = np.log(np.maximum(Y_orig, 1e-4))
        B = guided_filter(Y_orig, logY, self.r_filter, self.eps_filter)
        D = logY - B
        Yb = np.exp(B)
        
        # 2. Additive Radiance Decomposition
        # Ambient bounce floor
        Y_indirect = Yb * ambient_fill
        
        # Direct illumination: modulated by physical area light irradiance and shadow visibility
        irr_luma = linear_to_luminance(direct_irradiance)
        if direct_visibility is not None:
            Y_direct = Yb * irr_luma * direct_visibility
        else:
            Y_direct = Yb * irr_luma
        
        Y_relit_target = Y_indirect + Y_direct
        R_target = np.clip(Y_relit_target / np.maximum(Yb, 1e-4), 0.05, 20.0)
        
        # Highlight protection shoulder (protect original specular peaks)
        M_high = np.clip((Y_orig - 0.75) / (0.98 - 0.75), 0.0, 1.0)
        M_high = M_high * M_high * (3.0 - 2.0 * M_high)
        R_eff = (1.0 - M_high) * R_target + M_high * 1.0
        
        # Protected region masking: where protected, ratio is strictly 1.0
        if protected_mask is not None:
            R_eff = np.where(protected_mask, 1.0, R_eff)
            
        # 3. E.1 Guided-Filter Regularization on Shading Ratio
        rho = np.log(np.maximum(R_eff, 1e-4))
        rho_bar = guided_filter(Y_orig, rho, self.r_filter, self.eps_filter)
        Y_relit = np.exp(B + rho_bar + D)
        Y_relit = np.maximum(1e-4, Y_relit).astype(np.float32)
        
        # 4. C3 Oklab Constant-Hue Gamut Mapping
        relit_rgb_lin = color_reconstruct_C3(image_lin, Y_orig, Y_relit, n_bisection_steps=8)
        
        # Protect original image if protected_mask specified
        if protected_mask is not None:
            relit_rgb_lin = np.where(protected_mask[..., None], image_lin, relit_rgb_lin)
            
        relit_srgb = linear_to_srgb(relit_rgb_lin)
        if protected_mask is not None:
            relit_srgb = np.where(protected_mask[..., None], image_orig_srgb, relit_srgb)
        
        # Absolute luminance error map for diagnostic overlay
        lum_diff = np.abs(Y_relit - Y_orig)
        err_colormap = cv2.applyColorMap((np.clip(lum_diff * 2.0, 0.0, 1.0) * 255.0).astype(np.uint8), cv2.COLORMAP_TURBO)
        err_rgb = cv2.cvtColor(err_colormap, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        
        return {
            "relit_srgb": relit_srgb,
            "relit_linear": relit_rgb_lin,
            "Y_orig": Y_orig,
            "Y_relit": Y_relit,
            "R_eff": R_eff,
            "err_rgb": err_rgb
        }


def compute_DCI(img_orig: np.ndarray, img_relit: np.ndarray, mask: Optional[np.ndarray] = None) -> float:
    """
    Detail Conservation Index (DCI): Structural Laplacian SSIM correlation (Spike 1 standard).
    Measures preservation of high-frequency structural texture and fine micro-contrast.
    Formula: s_map = (2 * sigma_xy + C3) / (2 * sigma_x * sigma_y + C3) on 3x3 Laplacian maps.
    Supports whole-image and foreground-masked evaluation.
    """
    if img_orig.ndim == 3:
        Y_orig = linear_to_luminance(srgb_to_linear(img_orig))
    else:
        Y_orig = img_orig.astype(np.float32)

    if img_relit.ndim == 3:
        Y_relit = linear_to_luminance(srgb_to_linear(img_relit))
    else:
        Y_relit = img_relit.astype(np.float32)

    lap_orig = cv2.Laplacian(Y_orig, cv2.CV_32F, ksize=3)
    lap_relit = cv2.Laplacian(Y_relit, cv2.CV_32F, ksize=3)

    win_size = 11
    sigma = 1.5
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
        m_bool = (mask > 0.5) if mask.dtype != bool else mask
        return round(float(np.mean(s_map[m_bool])), 5)
    return round(float(np.mean(s_map)), 5)
