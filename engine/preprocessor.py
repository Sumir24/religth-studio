"""
Relight Studio — Scene Geometry & 2.5D Layer Preprocessor
Automates depth-to-normal conversion, camera-space 3D unprojection,
and background inpainting for Layered 2.5D Scene-Graph relighting.
"""

import numpy as np
import cv2
from typing import Tuple, Dict, Any, Optional

class ScenePreprocessor:
    def __init__(self, fov_degrees: float = 60.0):
        self.fov = fov_degrees

    def compute_camera_intrinsics(self, height: int, width: int) -> Tuple[float, float, float, float]:
        """Calculates focal length and principal center based on FOV."""
        fov_rad = np.radians(self.fov)
        f = (width / 2.0) / np.tan(fov_rad / 2.0)
        cx = width / 2.0
        cy = height / 2.0
        return f, f, cx, cy

    def depth_to_normals(self, depth: np.ndarray, smooth_ksize: int = 15) -> np.ndarray:
        """
        Converts a continuous depth map Z(x, y) into 3D unit surface normals.
        Uses bilateral smoothing to prevent contour stepping and terracing.
        """
        # Smooth depth slightly to remove camera sensor noise and quantization
        depth_smooth = cv2.bilateralFilter(depth.astype(np.float32), d=smooth_ksize, sigmaColor=0.1, sigmaSpace=smooth_ksize)
        
        # Spatial gradients
        dz_dx = cv2.Sobel(depth_smooth, cv2.CV_32F, 1, 0, ksize=3)
        dz_dy = cv2.Sobel(depth_smooth, cv2.CV_32F, 0, 1, ksize=3)
        
        # Unprojected tangent vectors:
        # N = cross([1, 0, dz_dx], [0, 1, dz_dy]) = [-dz_dx, -dz_dy, 1.0]
        nx = -dz_dx
        ny = -dz_dy
        nz = np.ones_like(depth_smooth)
        
        normals = np.stack([nx, ny, nz], axis=-1)
        norm_mag = np.linalg.norm(normals, axis=2, keepdims=True)
        normals = normals / np.clip(norm_mag, 1e-6, None)
        return normals

    def unproject_to_pointcloud(self, depth: np.ndarray) -> np.ndarray:
        """
        Unprojects 2D depth map into 3D camera-space coordinates P(u, v) = [X, Y, Z].
        """
        h, w = depth.shape
        fx, fy, cx, cy = self.compute_camera_intrinsics(h, w)
        
        u = np.arange(w, dtype=np.float32)
        v = np.arange(h, dtype=np.float32)
        u_grid, v_grid = np.meshgrid(u, v)
        
        z = np.clip(depth, 0.1, None)
        x = (u_grid - cx) * z / fx
        y = (v_grid - cy) * z / fy
        
        return np.stack([x, y, z], axis=-1)

    def inpaint_background(self, image: np.ndarray, mask: np.ndarray, inpaint_radius: int = 5) -> np.ndarray:
        """
        Inpaints background behind foreground subject mask to prevent edge tearing.
        Uses Navier-Stokes based inpainting for smooth lighting continuation.
        """
        img_uint8 = (np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8)
        mask_uint8 = (mask * 255.0).astype(np.uint8)
        
        inpainted_uint8 = cv2.inpaint(img_uint8, mask_uint8, inpaintRadius=inpaint_radius, flags=cv2.INPAINT_NS)
        return inpainted_uint8.astype(np.float32) / 255.0
