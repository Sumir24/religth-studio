"""
RELIGHT STUDIO — RS-SPIKE-3A: RECTANGULAR AREA LIGHT & DIRECT DIFFUSE ENGINE
=============================================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Strict Invariant: Physical energy conventions are explicitly separated:
  • FIXED_RADIANCE: Surface brightness Le is constant; total flux scales with area.
  • FIXED_POWER: Total flux Phi is constant; surface radiance Le scales inversely with area.
"""

from __future__ import annotations

import math
from typing import Tuple, List, Optional
import numpy as np

from studio3a.geometry import euler_to_rotation_matrix
from studio3a.scene import EnergyConvention


def kelvin_to_linear_rgb(temp_k: float) -> np.ndarray:
    """
    Converts correlated color temperature (Kelvin) to normalized linear RGB
    using Tanner Helland's Planckian radiator approximation.
    """
    t = float(np.clip(temp_k, 1000.0, 40000.0)) / 100.0
    
    # Red
    if t <= 66.0:
        r = 255.0
    else:
        r = 329.698727446 * ((t - 60.0) ** -0.1332047592)
        
    # Green
    if t <= 66.0:
        g = 99.4708025861 * math.log(max(1.0, t)) - 161.1195681661
    else:
        g = 288.1221695283 * ((t - 60.0) ** -0.0755148492)
        
    # Blue
    if t >= 66.0:
        b = 255.0
    elif t <= 19.0:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(max(1.0, t - 10.0)) - 305.0447927307
        
    srgb = np.clip(np.array([r, g, b], dtype=np.float32) / 255.0, 0.0, 1.0)
    # Convert sRGB to Linear RGB
    lin_rgb = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    # Normalize by luminance to keep intensity independent of temperature
    luma = 0.2126 * lin_rgb[0] + 0.7152 * lin_rgb[1] + 0.0722 * lin_rgb[2]
    return (lin_rgb / max(luma, 1e-4)).astype(np.float32)


class RectangularAreaLight:
    """
    Physical Rectangular Area Light Emitter (Softbox / Flat Panel).
    Defined in 3D by position, orientation, dimensions (width, height), and emission parameters.
    """
    def __init__(
        self,
        position=(1.2, 1.8, 1.5),
        rotation_euler=(-35.0, 30.0, 0.0),
        width=0.60,
        height=0.60,
        intensity=1.0,
        color_rgb=(1.0, 1.0, 1.0),
        temperature_kelvin=5600.0,
        energy_convention=EnergyConvention.FIXED_RADIANCE,
        enabled=True
    ):
        self.pos = np.array(position, dtype=np.float32)
        self.rot_euler = tuple(rotation_euler)
        self.width = max(0.01, float(width))
        self.height = max(0.01, float(height))
        self.intensity = max(0.0, float(intensity))
        self.color_rgb = np.array(color_rgb, dtype=np.float32)
        self.temperature = float(temperature_kelvin)
        self.convention = energy_convention
        self.enabled = bool(enabled)

        # Orthonormal orientation vectors
        self.R = euler_to_rotation_matrix(*self.rot_euler)
        # In canonical space, emitter points along -Z, width along +X, height along +Y
        self.u_tangent = (self.R @ np.array([1.0, 0.0, 0.0], dtype=np.float32)).astype(np.float32)
        self.v_bitangent = (self.R @ np.array([0.0, 1.0, 0.0], dtype=np.float32)).astype(np.float32)
        self.normal = (self.R @ np.array([0.0, 0.0, -1.0], dtype=np.float32)).astype(np.float32)

    @property
    def area(self) -> float:
        return self.width * self.height

    def get_emitted_radiance(self) -> np.ndarray:
        """Computes emitted radiance Le in Watts / (m^2 * sr)."""
        temp_tint = kelvin_to_linear_rgb(self.temperature)
        base_color = self.color_rgb * temp_tint
        if self.convention == EnergyConvention.FIXED_RADIANCE:
            return base_color * self.intensity
        else:
            # FIXED_POWER: intensity represents total flux Phi
            return (base_color * self.intensity) / max(self.area * math.pi, 1e-4)

    def sample_emitter_points(
        self,
        n_samples: int = 16,
        seed: Optional[int] = None,
        stratified_centers: bool = True
    ) -> np.ndarray:
        """
        Generates stratified sample points across the rectangular emitter quad.
        By default (stratified_centers=True), evaluates deterministic cell centers
        matching the Metal shader and eliminating temporal flickering during artist manipulation.
        When stratified_centers=False and seed is provided, jitters within cells.
        Returns array of shape (n_samples, 3).
        """
        if seed is not None:
            np.random.seed(seed)
            
        n_side = int(math.ceil(math.sqrt(n_samples)))
        actual_samples = []
        
        for i in range(n_side):
            for j in range(n_side):
                if len(actual_samples) >= n_samples:
                    break
                if stratified_centers:
                    u = (float(i) + 0.5) / float(n_side) - 0.5
                    v = (float(j) + 0.5) / float(n_side) - 0.5
                else:
                    u = (float(i) + np.random.uniform(0.1, 0.9)) / float(n_side) - 0.5
                    v = (float(j) + np.random.uniform(0.1, 0.9)) / float(n_side) - 0.5
                p = self.pos + (u * self.width) * self.u_tangent + (v * self.height) * self.v_bitangent
                actual_samples.append(p)
                
        return np.array(actual_samples, dtype=np.float32)

    def evaluate_unshadowed_irradiance(
        self,
        surface_pos: np.ndarray,
        surface_norm: np.ndarray,
        n_samples: int = 16,
        seed: Optional[int] = 42
    ) -> np.ndarray:
        """
        Evaluates unshadowed direct diffuse irradiance at surface positions.
        Args:
            surface_pos: (..., 3) array of surface hit positions.
            surface_norm: (..., 3) array of surface hit normals.
        Returns:
            irradiance: (..., 3) linear RGB irradiance values.
        """
        if not self.enabled:
            return np.zeros(surface_pos.shape[:-1] + (3,), dtype=np.float32)
            
        emitter_pts = self.sample_emitter_points(n_samples=n_samples, seed=seed)
        L_e = self.get_emitted_radiance()
        dA = self.area / float(len(emitter_pts))
        
        # Flatten input positions for vectorized batching
        shape = surface_pos.shape[:-1]
        p_flat = surface_pos.reshape(-1, 3)
        n_flat = surface_norm.reshape(-1, 3)
        
        irr_acc = np.zeros((len(p_flat), 3), dtype=np.float32)
        
        for p_emitter in emitter_pts:
            # Vector from surface to emitter
            L_vec = p_emitter[None, :] - p_flat
            dist_sq = np.sum(L_vec * L_vec, axis=-1)
            dist = np.sqrt(np.maximum(dist_sq, 1e-6))
            L_dir = L_vec / dist[:, None]
            
            # Emitter emission angle (must be emitted from front face)
            cos_emitter = np.maximum(0.0, -np.sum(L_dir * self.normal[None, :], axis=-1))
            
            # Surface incident angle
            cos_surface = np.maximum(0.0, np.sum(L_dir * n_flat, axis=-1))
            
            # Solid angle geometry term: G = (cos_e * cos_s) / dist^2
            G = (cos_emitter * cos_surface) / np.maximum(dist_sq, 1e-4)
            irr_acc += L_e[None, :] * (G[:, None] * dA)
            
        return irr_acc.reshape(shape + (3,))
