"""
RELIGHT STUDIO — RS-SPIKE-3C.3: IMAGE-BASED LIGHTING (IBL)
===========================================================
Environment Representation, Preintegrated BRDF LUT & Prefiltering Architecture
Conforms to Split-Sum Approximation (Karis 2013 / Epic Games) and
Authoritative Scene Model Contract.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import cv2

from studio3a.material import MaterialData


@dataclass
class EnvironmentData:
    """
    Authoritative Scene State representation for Image-Based Lighting.
    Supports deterministic serialization, undo/redo, and artist controls.
    """
    id: str = "env_default"
    name: str = "Default Studio Environment"
    enabled: bool = False
    asset_path: Optional[str] = None
    intensity: float = 1.0
    rotation_deg: float = 0.0          # Azimuthal rotation around +Y axis in degrees [0, 360]
    diffuse_weight: float = 1.0        # Diffuse environment contribution
    specular_weight: float = 1.0       # Specular environment contribution
    is_hdr: bool = True                # Flag whether environment source is HDR or approximate SDR
    tint_rgb: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Environment ID cannot be empty.")
        if self.intensity < 0.0:
            raise ValueError(f"Environment intensity cannot be negative: {self.intensity}")
        if not (0.0 <= self.diffuse_weight <= 5.0):
            raise ValueError(f"Diffuse weight out of valid range [0, 5]: {self.diffuse_weight}")
        if not (0.0 <= self.specular_weight <= 5.0):
            raise ValueError(f"Specular weight out of valid range [0, 5]: {self.specular_weight}")
        for c in self.tint_rgb:
            if not (0.0 <= c <= 2.0):
                raise ValueError(f"Tint channel out of valid range [0, 2]: {self.tint_rgb}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnvironmentData":
        d = data.copy()
        return cls(**d)


class PreintegratedBRDFLUT:
    """
    Computes the 2D Preintegrated BRDF Lookup Table (Karis 2013)
    Coordinates:
      X axis: cos_theta_v in [0, 1]
      Y axis: roughness in [0, 1]
    Channels:
      Channel 0 (R): Fresnel scale term
      Channel 1 (G): Fresnel bias term
    """
    _cached_lut: Optional[np.ndarray] = None

    @classmethod
    def get_lut(cls, size: int = 256, n_samples: int = 1024) -> np.ndarray:
        """Returns (size, size, 2) float32 array."""
        if cls._cached_lut is not None and cls._cached_lut.shape[0] == size:
            return cls._cached_lut

        lut = np.zeros((size, size, 2), dtype=np.float32)
        
        # Grid: nv is cos(theta_v), r is roughness
        nv_vals = (np.arange(size, dtype=np.float32) + 0.5) / float(size)
        r_vals = (np.arange(size, dtype=np.float32) + 0.5) / float(size)

        # Vectorized generation across 2D grid
        for y_idx, roughness in enumerate(r_vals):
            alpha = max(roughness * roughness, 0.0016)
            a2 = max(alpha * alpha, 0.0016 * 0.0016)

            for x_idx, nv in enumerate(nv_vals):
                n_dot_v = max(float(nv), 1e-4)
                v = np.array([math.sqrt(max(1.0 - n_dot_v * n_dot_v, 0.0)), 0.0, n_dot_v], dtype=np.float32)

                # Importance sample GGX distribution
                scale = 0.0
                bias = 0.0

                rng = np.random.RandomState(42)
                u1 = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)
                u2 = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)

                denom_h = (1.0 - u1) + a2 * u1
                cos_theta_h = np.sqrt(np.clip((1.0 - u1) / np.maximum(denom_h, 1e-7), 0.0, 1.0))
                sin_theta_h = np.sqrt(np.clip(1.0 - cos_theta_h * cos_theta_h, 0.0, 1.0))
                phi_h = 2.0 * math.pi * u2

                hx = sin_theta_h * np.cos(phi_h)
                hy = sin_theta_h * np.sin(phi_h)
                hz = cos_theta_h
                h = np.stack([hx, hy, hz], axis=-1)

                v_dot_h = np.sum(v * h, axis=-1)
                l = 2.0 * v_dot_h[:, None] * h - v
                n_dot_l = l[:, 2]

                valid = (n_dot_l > 0.0) & (v_dot_h > 0.0)
                if np.any(valid):
                    vh = v_dot_h[valid]
                    nl = n_dot_l[valid]
                    nh = h[valid, 2]

                    # Smith G2
                    lambda_v = nl * np.sqrt(n_dot_v * n_dot_v * (1.0 - a2) + a2)
                    lambda_l = n_dot_v * np.sqrt(nl * nl * (1.0 - a2) + a2)
                    denom = lambda_v + lambda_l
                    g2 = np.where(denom > 1e-7, (2.0 * nl * n_dot_v) / denom, 0.0)

                    # G_vis = (G2 * vh) / (n_dot_v * nh)
                    g_vis = (g2 * vh) / np.maximum(n_dot_v * nh, 1e-6)
                    fc = np.power(1.0 - vh, 5.0)

                    scale = float(np.sum((1.0 - fc) * g_vis)) / float(n_samples)
                    bias = float(np.sum(fc * g_vis)) / float(n_samples)

                lut[y_idx, x_idx, 0] = scale
                lut[y_idx, x_idx, 1] = bias

        cls._cached_lut = lut
        return lut


class EnvironmentMapProcessor:
    """
    Handles environment prefiltering:
      1. Diffuse Irradiance Convolution (Cosine hemisphere integration)
      2. Specular Prefiltered Environment Mips (GGX importance sampling convolution)
    """
    @staticmethod
    def compute_diffuse_irradiance_map(
        env_map: np.ndarray,
        out_width: int = 128,
        out_height: int = 64,
        n_samples: int = 256
    ) -> np.ndarray:
        """
        Convolves equirectangular environment map with cosine lobe
        to produce diffuse irradiance map E(n).
        """
        in_h, in_w = env_map.shape[:2]
        irr_map = np.zeros((out_height, out_width, 3), dtype=np.float32)

        px = (np.arange(out_width, dtype=np.float32) + 0.5) / float(out_width)
        py = (np.arange(out_height, dtype=np.float32) + 0.5) / float(out_height)
        gx, gy = np.meshgrid(px, py)

        theta_out = gy * math.pi
        phi_out = gx * (2.0 * math.pi) - math.pi

        # Normal directions corresponding to each pixel in irradiance map
        nx = np.sin(theta_out) * np.cos(phi_out)
        ny = np.cos(theta_out)
        nz = np.sin(theta_out) * np.sin(phi_out)
        normals = np.stack([nx, ny, nz], axis=-1).reshape(-1, 3)

        # Pre-generate cosine-weighted hemisphere sample directions in local space
        rng = np.random.RandomState(42)
        u1 = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)
        u2 = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)

        cos_t = np.sqrt(u1)
        sin_t = np.sqrt(np.clip(1.0 - u1, 0.0, 1.0))
        phi_s = 2.0 * math.pi * u2

        lx_loc = sin_t * np.cos(phi_s)
        ly_loc = sin_t * np.sin(phi_s)
        lz_loc = cos_t
        l_loc = np.stack([lx_loc, ly_loc, lz_loc], axis=-1)

        # Vectorized convolution
        from benchmarks.reference_ibl.reference_monte_carlo import build_orthonormal_basis
        tangents, bitangents = build_orthonormal_basis(normals)

        # Loop over batches of normals
        batch_size = 512
        num_pixels = normals.shape[0]
        irr_accum = np.zeros((num_pixels, 3), dtype=np.float32)

        for b_start in range(0, num_pixels, batch_size):
            b_end = min(b_start + batch_size, num_pixels)
            n_batch = normals[b_start:b_end]
            t_batch = tangents[b_start:b_end]
            bt_batch = bitangents[b_start:b_end]

            # Transform samples to world frame: (B, N, 3)
            l_world = (
                l_loc[None, :, 0:1] * t_batch[:, None, :] +
                l_loc[None, :, 1:2] * bt_batch[:, None, :] +
                l_loc[None, :, 2:3] * n_batch[:, None, :]
            )
            l_world = l_world / np.maximum(np.linalg.norm(l_world, axis=-1, keepdims=True), 1e-7)

            # Sample environment map
            dirs_flat = l_world.reshape(-1, 3)
            x, y, z = dirs_flat[:, 0], dirs_flat[:, 1], dirs_flat[:, 2]
            th = np.arccos(np.clip(y, -1.0, 1.0))
            ph = np.arctan2(z, x)
            u = (ph + math.pi) / (2.0 * math.pi)
            v = th / math.pi

            px_in = np.clip(u * float(in_w) - 0.5, 0, in_w - 1).astype(np.int32)
            py_in = np.clip(v * float(in_h) - 0.5, 0, in_h - 1).astype(np.int32)

            env_samples = env_map[py_in, px_in].reshape(b_end - b_start, n_samples, 3)
            irr_accum[b_start:b_end] = np.mean(env_samples, axis=1)

        irr_map = irr_accum.reshape(out_height, out_width, 3)
        return irr_map

    @staticmethod
    def compute_specular_prefiltered_map(
        env_map: np.ndarray,
        roughness: float,
        out_width: int = 256,
        out_height: int = 128,
        n_samples: int = 256
    ) -> np.ndarray:
        """
        Convolves equirectangular environment map with GGX distribution for roughness r
        to produce specular prefiltered map L_prefiltered(R, roughness).
        """
        if roughness <= 0.04:
            # Level 0 is direct bilinear downsample of environment map
            return cv2.resize(env_map, (out_width, out_height), interpolation=cv2.INTER_LINEAR)

        in_h, in_w = env_map.shape[:2]
        r_clamped = max(roughness, 0.04)
        alpha = r_clamped * r_clamped
        a2 = max(alpha * alpha, 0.0016 * 0.0016)

        px = (np.arange(out_width, dtype=np.float32) + 0.5) / float(out_width)
        py = (np.arange(out_height, dtype=np.float32) + 0.5) / float(out_height)
        gx, gy = np.meshgrid(px, py)

        theta_out = gy * math.pi
        phi_out = gx * (2.0 * math.pi) - math.pi

        rx = np.sin(theta_out) * np.cos(phi_out)
        ry = np.cos(theta_out)
        rz = np.sin(theta_out) * np.sin(phi_out)
        r_dirs = np.stack([rx, ry, rz], axis=-1).reshape(-1, 3)

        # Karis approximation: assume v = r = n
        from benchmarks.reference_ibl.reference_monte_carlo import build_orthonormal_basis
        tangents, bitangents = build_orthonormal_basis(r_dirs)

        rng = np.random.RandomState(42)
        u1 = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)
        u2 = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)

        denom_h = (1.0 - u1) + a2 * u1
        cos_t = np.sqrt(np.clip((1.0 - u1) / np.maximum(denom_h, 1e-7), 0.0, 1.0))
        sin_t = np.sqrt(np.clip(1.0 - cos_t * cos_t, 0.0, 1.0))
        phi_h = 2.0 * math.pi * u2

        hx_loc = sin_t * np.cos(phi_h)
        hy_loc = sin_t * np.sin(phi_h)
        hz_loc = cos_t
        h_loc = np.stack([hx_loc, hy_loc, hz_loc], axis=-1)

        batch_size = 512
        num_pixels = r_dirs.shape[0]
        spec_accum = np.zeros((num_pixels, 3), dtype=np.float32)

        for b_start in range(0, num_pixels, batch_size):
            b_end = min(b_start + batch_size, num_pixels)
            r_batch = r_dirs[b_start:b_end]
            t_batch = tangents[b_start:b_end]
            bt_batch = bitangents[b_start:b_end]

            # Half-vectors in world frame: (B, N, 3)
            h_world = (
                h_loc[None, :, 0:1] * t_batch[:, None, :] +
                h_loc[None, :, 1:2] * bt_batch[:, None, :] +
                h_loc[None, :, 2:3] * r_batch[:, None, :]
            )
            h_world = h_world / np.maximum(np.linalg.norm(h_world, axis=-1, keepdims=True), 1e-7)

            # Reflection: l = 2 * (v . h) * h - v (here v = r_batch)
            v_dot_h = np.sum(r_batch[:, None, :] * h_world, axis=-1, keepdims=True)
            l_world = 2.0 * v_dot_h * h_world - r_batch[:, None, :]
            n_dot_l = np.sum(r_batch[:, None, :] * l_world, axis=-1)

            valid = n_dot_l > 0.0
            nl_weights = np.where(valid, n_dot_l, 0.0)

            dirs_flat = l_world.reshape(-1, 3)
            x, y, z = dirs_flat[:, 0], dirs_flat[:, 1], dirs_flat[:, 2]
            th = np.arccos(np.clip(y, -1.0, 1.0))
            ph = np.arctan2(z, x)
            u = (ph + math.pi) / (2.0 * math.pi)
            v = th / math.pi

            px_in = np.clip(u * float(in_w) - 0.5, 0, in_w - 1).astype(np.int32)
            py_in = np.clip(v * float(in_h) - 0.5, 0, in_h - 1).astype(np.int32)

            env_samples = env_map[py_in, px_in].reshape(b_end - b_start, n_samples, 3)
            weighted_samples = env_samples * nl_weights[..., None]

            weight_sum = np.sum(nl_weights, axis=1, keepdims=True)
            spec_batch = np.where(weight_sum > 1e-6, np.sum(weighted_samples, axis=1) / np.maximum(weight_sum, 1e-6), 0.0)
            spec_accum[b_start:b_end] = spec_batch

        return spec_accum.reshape(out_height, out_width, 3)

