"""
RELIGHT STUDIO — RS-SPIKE-3A: GEOMETRIC SHADOW TRANSPORT & VISIBILITY ENGINE
=============================================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Strict Isolation Contract:
  1. Direct-light visibility: Evaluated via Monte Carlo shadow rays to area-light emitter samples.
  2. Self-occlusion: Evaluated on subject surface against proxy geometry.
  3. Cast-shadow visibility: Evaluated on receiver geometry against proxy geometry.
  4. Contact occlusion: Near-field geometric grounding term separated from ambient occlusion.
"""

from __future__ import annotations

import math
from typing import Tuple, List, Optional
import numpy as np

from studio3a.geometry import (
    OrientedBoundingBox, SuperquadricEllipsoid, LowPolyMesh,
    GroundPlaneReceiver, CycloramaReceiver
)
from studio3a.lighting import RectangularAreaLight


class ShadowEngine:
    """
    Independent Geometric Shadow Transport Subsystem.
    Evaluates exact visibility between surface points and area-light emitter samples
    using analytical 3D proxy ray intersections.
    """
    def __init__(self, proxy, receiver):
        self.proxy = proxy
        self.receiver = receiver

    def compute_direct_visibility(
        self,
        surface_pos: np.ndarray,
        surface_norm: np.ndarray,
        light: RectangularAreaLight,
        n_samples: int = 16,
        seed: Optional[int] = 42
    ) -> np.ndarray:
        """
        Computes direct visibility V_direct in [0, 1] by casting shadow rays
        from surface points to jittered area-light emitter samples.
        Args:
            surface_pos: (H, W, 3) surface hit positions.
            surface_norm: (H, W, 3) surface hit normals.
            light: RectangularAreaLight instance.
            n_samples: Number of emitter sample points.
        Returns:
            V_direct: (H, W) float array of visibility values.
        """
        H, W = surface_pos.shape[:2]
        emitter_pts = light.sample_emitter_points(n_samples=n_samples, seed=seed)
        
        # Valid hit points where normal is non-zero
        valid_mask = np.linalg.norm(surface_norm, axis=-1) > 1e-4
        if not np.any(valid_mask):
            return np.ones((H, W), dtype=np.float32)
            
        p_flat = surface_pos[valid_mask]
        n_flat = surface_norm[valid_mask]
        
        # Surface offset to prevent self-intersection acne
        p_bias = p_flat + 1e-3 * n_flat
        
        vis_acc = np.zeros(len(p_flat), dtype=np.float32)
        
        for p_emitter in emitter_pts:
            # Ray from surface point towards emitter sample
            L_vec = p_emitter[None, :] - p_bias
            dist = np.sqrt(np.maximum(np.sum(L_vec * L_vec, axis=-1), 1e-6))
            ray_d = L_vec / dist[:, None]
            
            # Test intersection against subject proxy
            hit_proxy, t_hit, _ = self.proxy.intersect_rays(p_bias, ray_d)
            
            # An occluder blocks light if it hits proxy before reaching the light emitter
            is_blocked = hit_proxy & (t_hit > 1e-3) & (t_hit < dist - 1e-3)
            vis_acc += (~is_blocked).astype(np.float32)
            
        out_vis = np.ones((H, W), dtype=np.float32)
        out_vis[valid_mask] = vis_acc / float(len(emitter_pts))
        return np.clip(out_vis, 0.0, 1.0).astype(np.float32)

    def compute_cast_shadow_mask(
        self,
        receiver_pos: np.ndarray,
        receiver_norm: np.ndarray,
        receiver_mask: np.ndarray,
        light: RectangularAreaLight,
        n_samples: int = 16,
        seed: Optional[int] = 42
    ) -> np.ndarray:
        """
        Computes cast shadow visibility V_cast on receiver surfaces.
        """
        H, W = receiver_pos.shape[:2]
        V_cast = np.ones((H, W), dtype=np.float32)
        
        if not np.any(receiver_mask):
            return V_cast
            
        emitter_pts = light.sample_emitter_points(n_samples=n_samples, seed=seed)
        p_flat = receiver_pos[receiver_mask]
        n_flat = receiver_norm[receiver_mask]
        p_bias = p_flat + 1e-3 * n_flat
        
        vis_acc = np.zeros(len(p_flat), dtype=np.float32)
        for p_emitter in emitter_pts:
            L_vec = p_emitter[None, :] - p_bias
            dist = np.sqrt(np.maximum(np.sum(L_vec * L_vec, axis=-1), 1e-6))
            ray_d = L_vec / dist[:, None]
            
            hit_proxy, t_hit, _ = self.proxy.intersect_rays(p_bias, ray_d)
            is_blocked = hit_proxy & (t_hit > 1e-3) & (t_hit < dist - 1e-3)
            vis_acc += (~is_blocked).astype(np.float32)
            
        V_cast[receiver_mask] = vis_acc / float(len(emitter_pts))
        return np.clip(V_cast, 0.0, 1.0).astype(np.float32)

    def compute_contact_occlusion(
        self,
        surface_pos: np.ndarray,
        is_receiver: np.ndarray,
        ground_y: float = 0.0,
        r_contact: float = 0.08
    ) -> np.ndarray:
        """
        Near-field geometric contact occlusion C_contact in [0, 1].
        Evaluates proximity between receiver points and proxy base contact boundary.
        """
        H, W = surface_pos.shape[:2]
        C_contact = np.ones((H, W), dtype=np.float32)
        
        # Points on the receiver near the contact plane
        dist_to_ground = np.abs(surface_pos[..., 1] - ground_y)
        near_ground = is_receiver & (dist_to_ground < 0.02)
        
        if not np.any(near_ground):
            return C_contact
            
        # Distance to proxy center in horizontal XZ plane
        px_center_xz = np.array([self.proxy.center[0], self.proxy.center[2]], dtype=np.float32)
        p_xz = surface_pos[near_ground][:, [0, 2]]
        d_center = np.linalg.norm(p_xz - px_center_xz, axis=-1)
        
        # Approximate footprint radius from proxy dimensions
        if hasattr(self.proxy, 'half_extents'):
            footprint_r = float(np.max(self.proxy.half_extents[[0, 2]]))
        elif hasattr(self.proxy, 'radii'):
            footprint_r = float(np.max(self.proxy.radii[[0, 2]]))
        else:
            footprint_r = 0.25
            
        # Proximity to contact perimeter: distance to boundary
        dist_to_edge = np.maximum(0.0, d_center - footprint_r)
        contact_weight = np.clip(1.0 - (dist_to_edge / max(r_contact, 1e-3)), 0.0, 1.0)
        # Cubic Hermite smoothing
        contact_att = contact_weight * contact_weight * (3.0 - 2.0 * contact_weight)
        
        # Minimum visibility at contact seam is 0.05
        C_contact[near_ground] = 1.0 - 0.95 * contact_att
        return np.clip(C_contact, 0.0, 1.0).astype(np.float32)
