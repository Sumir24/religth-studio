"""
RELIGHT STUDIO — RS-SPIKE-3C.3: PHASE A REFERENCE IBL
=====================================================
Synthetic Studio Environment Map Generator & Sampler
Produces a deterministic, high-dynamic-range equirectangular environment map
specifically calibrated to test:
  - Bright high-intensity key emitter reflection
  - Dark negative-fill absorption
  - Neutral midtone studio bounce
  - Tinted / colored accent strip reflection
  - High-contrast edge boundary sharpness & continuity
"""

import math
from typing import Tuple, Optional
import numpy as np
import cv2


class SyntheticStudioEnvironment:
    """
    Equirectangular 2:1 HDR linear floating-point environment map generator and sampler.
    World coordinates: +Y is Up, +Z is Forward, +X is Right.
    Spherical coordinates:
      theta in [0, pi] (0 at +Y pole, pi at -Y pole)
      phi in [-pi, pi] (atan2(z, x))
    UV coordinates:
      u = (phi + pi) / (2 * pi) in [0, 1]
      v = theta / pi in [0, 1]
    """
    def __init__(self, width: int = 1024, height: int = 512):
        self.width = width
        self.height = height
        self.data: np.ndarray = self._generate_environment_map()

    def _generate_environment_map(self) -> np.ndarray:
        """Constructs calibrated linear RGB radiance map (H, W, 3)."""
        W, H = self.width, self.height
        env = np.zeros((H, W, 3), dtype=np.float32)

        # Generate coordinate grid
        # v is vertical [0, 1], u is horizontal [0, 1]
        v_coords = (np.arange(H, dtype=np.float32) + 0.5) / float(H)
        u_coords = (np.arange(W, dtype=np.float32) + 0.5) / float(W)
        u_grid, v_grid = np.meshgrid(u_coords, v_coords)

        theta = v_grid * math.pi           # [0, pi]
        phi = u_grid * (2.0 * math.pi) - math.pi  # [-pi, pi]

        # 1. Neutral Midtone Studio Bounce / Floor (Lower Hemisphere: theta > pi/2)
        # Smooth gradient from 0.35 at horizon to 0.15 at bottom pole
        floor_mask = theta > (math.pi * 0.5)
        floor_gradient = np.clip(np.cos(theta - math.pi * 0.5), 0.0, 1.0)
        floor_radiance = 0.35 * floor_gradient + 0.15 * (1.0 - floor_gradient)
        env[floor_mask] = floor_radiance[floor_mask, None] * np.array([0.45, 0.45, 0.48], dtype=np.float32)

        # Upper hemisphere baseline: subtle studio ambient
        sky_mask = ~floor_mask
        sky_gradient = np.clip(np.cos(theta), 0.0, 1.0)
        env[sky_mask] = (0.08 * sky_gradient[sky_mask, None] + 0.04) * np.array([0.5, 0.5, 0.55], dtype=np.float32)

        # 2. Bright Key Softbox (High Intensity Rectangular Emitter)
        # Positioned at upper-right: phi in [35 deg, 75 deg], theta in [35 deg, 70 deg]
        # Radiance L = 14.0 (Linear daylight D65: [14.0, 13.8, 13.2])
        phi_deg = np.degrees(phi)
        theta_deg = np.degrees(theta)
        
        softbox_mask = (
            (phi_deg >= 35.0) & (phi_deg <= 75.0) &
            (theta_deg >= 35.0) & (theta_deg <= 70.0)
        )
        env[softbox_mask] = np.array([14.0, 13.8, 13.2], dtype=np.float32)

        # 3. High-Contrast Edge Demarcation: Dark Absorber / Black Flag
        # Immediately adjacent to softbox: phi in [75 deg, 95 deg], theta in [35 deg, 70 deg]
        # Radiance L = 0.01 (Near total absorption)
        flag_mask = (
            (phi_deg >= 75.0) & (phi_deg <= 95.0) &
            (theta_deg >= 35.0) & (theta_deg <= 70.0)
        )
        env[flag_mask] = np.array([0.01, 0.01, 0.01], dtype=np.float32)

        # 4. Coloured Accent Feature: Warm Amber Rim Strip
        # Positioned at left: phi in [-120 deg, -85 deg], theta in [45 deg, 75 deg]
        # Radiance L = 6.0, Tint = Amber [1.0, 0.55, 0.08]
        amber_mask = (
            (phi_deg >= -120.0) & (phi_deg <= -85.0) &
            (theta_deg >= 45.0) & (theta_deg <= 75.0)
        )
        env[amber_mask] = 6.0 * np.array([1.0, 0.55, 0.08], dtype=np.float32)

        # 5. Cold Rim Accent: Subtle Cyan Strip on Opposite Side
        # phi in [150 deg, 175 deg], theta in [45 deg, 70 deg]
        # Radiance L = 3.5, Tint = Cyan [0.15, 0.70, 0.95]
        cyan_mask = (
            (phi_deg >= 150.0) & (phi_deg <= 175.0) &
            (theta_deg >= 45.0) & (theta_deg <= 70.0)
        )
        env[cyan_mask] = 3.5 * np.array([0.15, 0.70, 0.95], dtype=np.float32)

        # 6. Deep Dark Negative Fill (Opposite hemisphere)
        # phi in [-60 deg, -20 deg], theta in [20 deg, 80 deg]
        # Radiance L = 0.02
        dark_mask = (
            (phi_deg >= -60.0) & (phi_deg <= -20.0) &
            (theta_deg >= 20.0) & (theta_deg <= 80.0)
        )
        env[dark_mask] = np.array([0.02, 0.02, 0.025], dtype=np.float32)

        return env

    def sample(self, direction: np.ndarray) -> np.ndarray:
        """
        Bilinear equirectangular environment lookup.
        Args:
            direction: (..., 3) unit 3D vectors in world coordinates.
        Returns:
            (..., 3) linear RGB radiance values.
        """
        orig_shape = direction.shape[:-1]
        dirs = direction.reshape(-1, 3).astype(np.float32)
        norm = np.linalg.norm(dirs, axis=-1, keepdims=True)
        dirs = dirs / np.maximum(norm, 1e-7)

        x, y, z = dirs[:, 0], dirs[:, 1], dirs[:, 2]

        # Spherical mapping
        theta = np.arccos(np.clip(y, -1.0, 1.0))
        phi = np.arctan2(z, x)

        u = (phi + math.pi) / (2.0 * math.pi)
        v = theta / math.pi

        # Convert to continuous pixel coordinates
        W, H = self.width, self.height
        px = u * float(W) - 0.5
        py = v * float(H) - 0.5

        # Bilinear interpolation with toroidal wrap on X and clamp on Y
        x0 = np.floor(px).astype(np.int32)
        y0 = np.floor(py).astype(np.int32)
        x1 = x0 + 1
        y1 = y0 + 1

        fx = (px - x0).astype(np.float32)[:, None]
        fy = (py - y0).astype(np.float32)[:, None]

        # Horizontal wrap (toroidal)
        x0_wrapped = x0 % W
        x1_wrapped = x1 % W

        # Vertical clamp
        y0_clamped = np.clip(y0, 0, H - 1)
        y1_clamped = np.clip(y1, 0, H - 1)

        c00 = self.data[y0_clamped, x0_wrapped]
        c10 = self.data[y0_clamped, x1_wrapped]
        c01 = self.data[y1_clamped, x0_wrapped]
        c11 = self.data[y1_clamped, x1_wrapped]

        c0 = c00 * (1.0 - fx) + c10 * fx
        c1 = c01 * (1.0 - fx) + c11 * fx
        samples = c0 * (1.0 - fy) + c1 * fy

        return samples.reshape(orig_shape + (3,))

    def save_tonemapped_preview(self, path: str, exposure: float = 0.5) -> None:
        """Saves a tone-mapped 8-bit preview of the environment map for inspection."""
        hdr = self.data * exposure
        # Reinhard tonemapping + gamma 2.2
        ldr = hdr / (hdr + 1.0)
        srgb = np.power(np.clip(ldr, 0.0, 1.0), 1.0 / 2.2)
        bgr = (srgb[..., ::-1] * 255.0).astype(np.uint8)
        cv2.imwrite(path, bgr)


if __name__ == "__main__":
    env = SyntheticStudioEnvironment(width=1024, height=512)
    preview_path = "benchmarks/reference_ibl/diagnostic_boards/synthetic_studio_env_preview.png"
    env.save_tonemapped_preview(preview_path)
    print(f"Synthetic studio environment created: shape {env.data.shape}, range [{env.data.min():.4f}, {env.data.max():.4f}]")
    print(f"Saved preview to {preview_path}")

