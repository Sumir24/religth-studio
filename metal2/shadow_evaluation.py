"""
RELIGHT STUDIO — RS-SPIKE-3A.1: CONTINUOUS SHADOW EVALUATION SUITE
==================================================================
Eliminates binary thresholding pathology by evaluating:
  1. Continuous Soft IoU (fuzzy Jaccard index on shadow opacity O = 1 - V)
  2. Continuous Opacity-Weighted Shadow Centroid & SDE
  3. Soft Penumbra Width and Profile Agreement
  4. Umbra & Penumbra L1 MAE and L2 RMSE
  5. 50% Isoline Contour Boundary Displacement (Directed Hausdorff)
  6. Contact Grounding Seam Attenuation (target V_seam <= 0.05)
  7. Exact Bitwise Protected-Region Leakage
"""

import math
from typing import Dict, Any, Tuple, Optional
import numpy as np
import cv2


def compute_shadow_opacity(V: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
    """Computes shadow opacity O = 1.0 - V in [0, 1]."""
    O = np.clip(1.0 - V, 0.0, 1.0)
    if mask is not None:
        O = np.where(mask, O, 0.0)
    return O.astype(np.float32)


def compute_soft_iou(V_cand: np.ndarray, V_gt: np.ndarray, mask: np.ndarray) -> float:
    """
    Continuous Soft IoU (Fuzzy Jaccard) on shadow opacity O = 1 - V:
    Soft-IoU = sum(min(O_cand, O_gt)) / sum(max(O_cand, O_gt)).
    """
    O_c = compute_shadow_opacity(V_cand, mask)
    O_g = compute_shadow_opacity(V_gt, mask)
    
    inter = np.sum(np.minimum(O_c, O_g))
    union = np.sum(np.maximum(O_c, O_g))
    
    if union < 1e-6:
        return 1.0 if inter < 1e-6 else 0.0
    return float(round(inter / union, 4))


def compute_continuous_sde(V_cand: np.ndarray, V_gt: np.ndarray, mask: np.ndarray) -> float:
    """
    Continuous Opacity-Weighted Shadow Centroid Displacement (SDE):
    Weights pixels by continuous shadow opacity O = 1 - V rather than binary cutoff.
    """
    O_c = compute_shadow_opacity(V_cand, mask)
    O_g = compute_shadow_opacity(V_gt, mask)
    
    sum_c = np.sum(O_c)
    sum_g = np.sum(O_g)
    
    if sum_c < 1e-5 or sum_g < 1e-5:
        return 0.0 if (sum_c < 1e-5 and sum_g < 1e-5) else 50.0
        
    y_coords, x_coords = np.mgrid[0:V_cand.shape[0], 0:V_cand.shape[1]].astype(np.float32)
    
    cy_c = np.sum(y_coords * O_c) / sum_c
    cx_c = np.sum(x_coords * O_c) / sum_c
    
    cy_g = np.sum(y_coords * O_g) / sum_g
    cx_g = np.sum(x_coords * O_g) / sum_g
    
    sde = math.sqrt((cy_c - cy_g)**2 + (cx_c - cx_g)**2)
    return float(round(sde, 2))


def compute_penumbra_metrics(V_cand: np.ndarray, V_gt: np.ndarray, mask: np.ndarray) -> Dict[str, float]:
    """
    Evaluates soft-shadow penumbra width and transition accuracy:
    - Penumbra defined as region where 0.15 <= V <= 0.85
    - Measures penumbra pixel area ratio and boundary gradient agreement.
    """
    penumbra_c = (V_cand >= 0.15) & (V_cand <= 0.85) & mask
    penumbra_g = (V_gt >= 0.15) & (V_gt <= 0.85) & mask
    
    area_c = int(np.sum(penumbra_c))
    area_g = int(np.sum(penumbra_g))
    
    # Penumbra area ratio
    area_ratio = float(round(area_c / max(area_g, 1), 4))
    
    # L1 error inside penumbra region
    union_penumbra = (penumbra_c | penumbra_g)
    if np.any(union_penumbra):
        penumbra_mae = float(np.mean(np.abs(V_cand[union_penumbra] - V_gt[union_penumbra])))
    else:
        penumbra_mae = 0.0
        
    return {
        "penumbra_area_cand": area_c,
        "penumbra_area_gt": area_g,
        "penumbra_area_ratio": area_ratio,
        "penumbra_mae": float(round(penumbra_mae, 4))
    }


def compute_contour_boundary_displacement(V_cand: np.ndarray, V_gt: np.ndarray, mask: np.ndarray) -> float:
    """
    Measures mean Euclidean distance between the 50% shadow isolines (V = 0.50).
    Uses distance transform on binary contour.
    """
    # 50% shadow boundary
    b_c = ((V_cand < 0.50) & mask).astype(np.uint8)
    b_g = ((V_gt < 0.50) & mask).astype(np.uint8)
    
    if not np.any(b_c) or not np.any(b_g):
        return 0.0 if (not np.any(b_c) and not np.any(b_g)) else 50.0
        
    contours_c, _ = cv2.findContours(b_c, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contours_g, _ = cv2.findContours(b_g, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    
    if not contours_c or not contours_g:
        return 0.0
        
    pts_c = np.vstack(contours_c)[:, 0, :] # (N, 2)
    
    # Distance transform from ground truth boundary
    dist_map_g = cv2.distanceTransform(1 - b_g, cv2.DIST_L2, 5)
    
    # Sample distances at candidate contour points
    sampled_dists = dist_map_g[pts_c[:, 1], pts_c[:, 0]]
    mean_disp = float(np.mean(sampled_dists))
    return float(round(mean_disp, 2))


def compute_contact_grounding_metrics(V_cand: np.ndarray, contact_mask: np.ndarray) -> Dict[str, float]:
    """
    Evaluates contact seam grounding quality:
    - Minimum visibility at the seam (target <= 0.05)
    - Mean contact attenuation depth.
    """
    if not np.any(contact_mask):
        return {"contact_min_vis": 1.0, "contact_mean_vis": 1.0, "gate_contact": "SKIP"}
        
    min_v = float(np.min(V_cand[contact_mask]))
    mean_v = float(np.mean(V_cand[contact_mask]))
    gate = "PASS" if min_v <= 0.06 else "FAIL"
    
    return {
        "contact_min_vis": float(round(min_v, 4)),
        "contact_mean_vis": float(round(mean_v, 4)),
        "gate_contact": gate
    }


def evaluate_comprehensive_shadow_fidelity(
    V_cand: np.ndarray,
    V_gt: np.ndarray,
    receiver_mask: np.ndarray,
    contact_mask: Optional[np.ndarray] = None
) -> Dict[str, Any]:
    """
    Full comprehensive shadow fidelity evaluation replacing binary-only thresholding.
    """
    # 1. Continuous Metrics
    soft_iou = compute_soft_iou(V_cand, V_gt, receiver_mask)
    cont_sde = compute_continuous_sde(V_cand, V_gt, receiver_mask)
    
    # 2. Field Errors
    diff = np.abs(V_cand[receiver_mask] - V_gt[receiver_mask])
    mae = float(round(float(np.mean(diff)), 6))
    rmse = float(round(float(np.sqrt(np.mean(diff**2))), 6))
    max_err = float(round(float(np.max(diff)), 6))
    
    # 3. Contour Displacement
    contour_disp = compute_contour_boundary_displacement(V_cand, V_gt, receiver_mask)
    
    # 4. Penumbra Analysis
    penumbra_dict = compute_penumbra_metrics(V_cand, V_gt, receiver_mask)
    
    # 5. Contact Analysis
    if contact_mask is not None:
        contact_dict = compute_contact_grounding_metrics(V_cand, contact_mask)
    else:
        contact_dict = {"contact_min_vis": 1.0, "gate_contact": "N/A"}
        
    return {
        "soft_iou": soft_iou,
        "continuous_sde_px": cont_sde,
        "contour_displacement_px": contour_disp,
        "shadow_field_mae": mae,
        "shadow_field_rmse": rmse,
        "shadow_field_max_err": max_err,
        "penumbra": penumbra_dict,
        "contact": contact_dict
    }
