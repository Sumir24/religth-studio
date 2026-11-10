"""
RELIGHT STUDIO — RS-SPIKE-3A: MULTI-CHANNEL UNCERTAINTY SUPERVISOR
===================================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Strict Invariant: Evaluates three independent physical uncertainty channels:
  1. GeometryUncertainty (sigma_geom^2): Normal divergence & depth cliff proximity.
  2. OcclusionUncertainty (sigma_occl^2): Unknown back-volume ray travel distance.
  3. MaterialUncertainty (sigma_mat^2): High-frequency texture vs flat geometry ambiguity.
"""

from __future__ import annotations

import cv2
import numpy as np


class UncertaintySupervisor:
    """
    Evaluates and exposes decoupled spatial uncertainty channels without
    silently overriding artist parameters.
    """
    def __init__(self, tau_cliff: float = 0.04):
        self.tau_cliff = float(tau_cliff)

    def evaluate_uncertainty(
        self,
        depth: np.ndarray,
        normals: np.ndarray,
        view_dir: np.ndarray,
        image_lin: np.ndarray,
        fg_mask: np.ndarray
    ) -> dict[str, np.ndarray]:
        """
        Evaluates the three distinct uncertainty channels.
        Returns dictionary containing:
            sigma_geom: (H, W) geometric measurement uncertainty in [0, 1].
            sigma_occl: (H, W) back-volume occlusion uncertainty in [0, 1].
            sigma_mat: (H, W) material ambiguity uncertainty in [0, 1].
            composite_confidence: (H, W) combined confidence for diagnostic visualization.
        """
        H, W = depth.shape[:2]
        
        # 1. Geometry Uncertainty sigma_geom^2
        gx = cv2.Sobel(depth, cv2.CV_32F, 1, 0, ksize=3) / 8.0
        gy = cv2.Sobel(depth, cv2.CV_32F, 0, 1, ksize=3) / 8.0
        grad_mag_sq = gx**2 + gy**2
        cliff_factor = np.exp(-grad_mag_sq / (2.0 * (self.tau_cliff**2)))
        
        # Camera grazing factor (magnitude of alignment with view ray)
        cos_view = np.clip(np.abs(np.sum(normals * view_dir, axis=-1)), 0.0, 1.0)
        
        # Confidence U_geom in [0, 1]
        u_geom = np.clip(cliff_factor * (cos_view**0.5), 0.0, 1.0)
        sigma_geom = np.clip(1.0 - u_geom, 0.0, 1.0).astype(np.float32)
        
        # 2. Occlusion Uncertainty sigma_occl^2
        # Higher near silhouettes where 3D back-volume is unobserved
        dist_to_edge = cv2.distanceTransform((~fg_mask).astype(np.uint8), cv2.DIST_L2, 3)
        edge_proximity = np.clip(1.0 - (dist_to_edge / 20.0), 0.0, 1.0)
        sigma_occl = np.where(fg_mask, edge_proximity * 0.75, 0.0).astype(np.float32)
        
        # 3. Material Uncertainty sigma_mat^2
        # Local luminance variance vs normal variance
        luma = 0.2126 * image_lin[..., 0] + 0.7152 * image_lin[..., 1] + 0.0722 * image_lin[..., 2]
        luma_blur = cv2.GaussianBlur(luma, (5, 5), 1.0)
        luma_var = np.abs(luma - luma_blur)
        sigma_mat = np.clip(luma_var * 3.0, 0.0, 1.0).astype(np.float32)
        
        # Composite confidence
        composite_confidence = np.clip(1.0 - np.maximum(sigma_geom, sigma_occl), 0.0, 1.0)
        
        return {
            "sigma_geom": sigma_geom,
            "sigma_occl": sigma_occl,
            "sigma_mat": sigma_mat,
            "composite_confidence": composite_confidence
        }

    @staticmethod
    def evaluate_environment_uncertainty(env_data: Any) -> dict[str, Any]:
        """
        Assesses environment information status.
        Distinguishes:
          - KNOWN_HDR: User-provided calibrated HDR environment map
          - ESTIMATED_SDR: SDR photograph approximate estimation
          - SYNTHETIC_DEFAULT: Built-in synthetic studio environment
          - DISABLED: Environment illumination disabled or missing
        """
        if env_data is None or not getattr(env_data, "enabled", False) or getattr(env_data, "intensity", 0.0) <= 1e-4:
            return {
                "status": "DISABLED",
                "confidence": 0.0,
                "is_physically_calibrated": False,
                "description": "Environment lighting is disabled."
            }
        asset = getattr(env_data, "asset_path", None)
        is_hdr = getattr(env_data, "is_hdr", True)
        if asset:
            if is_hdr:
                return {
                    "status": "KNOWN_HDR",
                    "confidence": 0.95,
                    "is_physically_calibrated": True,
                    "description": "User-supplied HDR environment map."
                }
            else:
                return {
                    "status": "ESTIMATED_SDR",
                    "confidence": 0.50,
                    "is_physically_calibrated": False,
                    "description": "SDR environment approximation (not calibrated radiance)."
                }
        return {
            "status": "SYNTHETIC_DEFAULT",
            "confidence": 0.80,
            "is_physically_calibrated": True,
            "description": "Deterministic synthetic HDR studio environment."
        }
