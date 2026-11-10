"""
RELIGHT STUDIO — RS-SPIKE-3A: 3D PINHOLE CAMERA & IMAGE REGISTRATION
=====================================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Strict Invariant: The virtual scene viewport and image viewport share
the identical mathematical camera model. No arbitrary coordinate shifts.
"""

from __future__ import annotations

import math
from typing import Tuple, List, Optional
import numpy as np


def fov_to_focal_length_mm(fov_deg: float, sensor_height_mm: float = 24.0) -> float:
    """Computes 35mm full-frame equivalent focal length (in mm) from vertical FOV (in degrees)."""
    rad = math.radians(max(1.0, min(170.0, fov_deg)))
    return round(float((sensor_height_mm / 2.0) / math.tan(rad / 2.0)), 2)


def focal_length_to_fov_deg(focal_length_mm: float, sensor_height_mm: float = 24.0) -> float:
    """Computes vertical FOV (in degrees) from 35mm full-frame equivalent focal length (in mm)."""
    fl = max(5.0, min(1200.0, float(focal_length_mm)))
    rad = 2.0 * math.atan((sensor_height_mm / 2.0) / fl)
    return round(float(math.degrees(rad)), 4)


class Camera3D:
    """
    Vectorized 3D Pinhole Camera with explicit coordinate conventions:
      • World Coordinate System: Right-handed (+X right, +Y up, +Z towards camera / studio floor at Y=0).
      • Screen Coordinates: (0, 0) at top-left, (+X right, +Y down).
    """
    def __init__(
        self,
        pos: Tuple[float, float, float] | List[float] = (0.0, 1.2, 2.5),
        target: Tuple[float, float, float] | List[float] = (0.0, 0.35, 0.0),
        up: Tuple[float, float, float] | List[float] = (0.0, 1.0, 0.0),
        fov_deg: float = 45.0,
        width: int = 384,
        height: int = 256
    ):
        self.pos = np.array(pos, dtype=np.float32)
        self.target = np.array(target, dtype=np.float32)
        self.up = np.array(up, dtype=np.float32)
        self.W = int(width)
        self.H = int(height)
        self.fov_deg = float(fov_deg)

        if self.W <= 0 or self.H <= 0:
            raise ValueError(f"Invalid camera dimensions: {self.W}x{self.H}")
        if np.allclose(self.pos, self.target):
            raise ValueError("Camera position cannot coincide with target.")

        # Camera Orthonormal Basis
        forward = self.target - self.pos
        self.forward = forward / np.linalg.norm(forward)
        right = np.cross(self.forward, self.up)
        if np.linalg.norm(right) < 1e-6:
            # Handle degenerate collinear look/up vector
            up_alt = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            right = np.cross(self.forward, up_alt)
        self.right = right / np.linalg.norm(right)
        self.up_cam = np.cross(self.right, self.forward)

        # FOV and projection parameters
        self.fov_rad = math.radians(self.fov_deg)
        self.tan_half_fov = math.tan(self.fov_rad / 2.0)
        self.aspect = float(self.W) / float(self.H)

        # Focal length in pixels and 35mm equivalent in mm
        self.fy = (self.H / 2.0) / self.tan_half_fov
        self.fx = self.fy  # Square pixels assumption
        self.cx = self.W / 2.0
        self.cy = self.H / 2.0
        self.focal_length_mm = fov_to_focal_length_mm(self.fov_deg)

        # Construct Extrinsic View Matrix (World -> Camera)
        # R_view rows are camera axes: right, up_cam, -forward
        # Camera looks down -Z in its local coordinate system
        R_view = np.eye(4, dtype=np.float32)
        R_view[0, :3] = self.right
        R_view[1, :3] = self.up_cam
        R_view[2, :3] = -self.forward
        
        T_view = np.eye(4, dtype=np.float32)
        T_view[:3, 3] = -self.pos
        
        self.view_matrix = R_view @ T_view
        self.inv_view_matrix = np.linalg.inv(self.view_matrix)

    def world_to_camera(self, pts_world: np.ndarray) -> np.ndarray:
        """Transforms 3D points from World space to Camera space."""
        orig_shape = pts_world.shape
        flat_pts = pts_world.reshape(-1, 3)
        pts_homo = np.hstack([flat_pts, np.ones((len(flat_pts), 1), dtype=np.float32)])
        pts_cam = (self.view_matrix @ pts_homo.T).T[:, :3]
        return pts_cam.reshape(orig_shape)

    def camera_to_world(self, pts_cam: np.ndarray) -> np.ndarray:
        """Transforms 3D points from Camera space to World space."""
        orig_shape = pts_cam.shape
        flat_pts = pts_cam.reshape(-1, 3)
        pts_homo = np.hstack([flat_pts, np.ones((len(flat_pts), 1), dtype=np.float32)])
        pts_world = (self.inv_view_matrix @ pts_homo.T).T[:, :3]
        return pts_world.reshape(orig_shape)

    def project_point(self, pt_world: np.ndarray) -> Tuple[float, float, float]:
        """
        Projects a 3D world point into 2D image coordinates (pixel_x, pixel_y)
        and returns camera depth Z.
        """
        p_cam = self.world_to_camera(pt_world.reshape(1, 3)).reshape(3)
        cam_z = -p_cam[2]  # Distance in front of camera
        if cam_z <= 1e-4:
            return -1.0, -1.0, float(cam_z)
        
        px = (p_cam[0] / cam_z) * self.fx + self.cx
        py = (-p_cam[1] / cam_z) * self.fy + self.cy  # Invert Y for screen coordinates
        return float(px), float(py), float(cam_z)

    def generate_camera_rays(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generates vectorized primary camera rays through pixel centers.
        Returns:
            ray_o: (H, W, 3) array of ray origins in world coordinates.
            ray_d: (H, W, 3) array of normalized ray directions in world coordinates.
        """
        y_idx, x_idx = np.mgrid[0:self.H, 0:self.W].astype(np.float32)
        
        # Normalized Device Coordinates in [-1, 1]
        ndc_x = (2.0 * (x_idx + 0.5) / self.W - 1.0) * self.tan_half_fov * self.aspect
        ndc_y = (1.0 - 2.0 * (y_idx + 0.5) / self.H) * self.tan_half_fov
        
        ray_d = (ndc_x[..., None] * self.right +
                 ndc_y[..., None] * self.up_cam +
                 self.forward)
        ray_d /= np.linalg.norm(ray_d, axis=-1, keepdims=True)
        
        ray_o = np.broadcast_to(self.pos, ray_d.shape).copy()
        return ray_o.astype(np.float32), ray_d.astype(np.float32)
