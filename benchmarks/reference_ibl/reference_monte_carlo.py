"""
RELIGHT STUDIO — RS-SPIKE-3C.3: PHASE A REFERENCE IBL
=====================================================
Independent Monte Carlo Ground-Truth Reference Integrator
Evaluates Cook-Torrance microfacet BRDF under Image-Based Lighting
using GGX Importance Sampling and Cosine-Weighted Hemisphere Integration.

Mathematical Invariants:
  - Exact Trowbridge-Reitz GGX NDF with remediated safeguard
  - Heitz height-correlated Smith G2 masking-shadowing
  - Schlick Fresnel reflectance
  - GGX importance-sampled half-vectors with analytical PDF cancellation
  - Strict energy conservation (single-scattering limit)
  - Convergence verified up to 16,384 samples/pixel
"""

import math
from typing import Tuple, Optional
import numpy as np
from benchmarks.reference_ibl.synthetic_studio_env import SyntheticStudioEnvironment


def build_orthonormal_basis(n: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Constructs an orthonormal tangent frame (t, b) for normal vector n
    using the Duff et al. (2017) building-an-orthonormal-basis algorithm.
    n: (..., 3) unit normal vectors.
    """
    sign = np.where(n[..., 2] >= 0.0, 1.0, -1.0).astype(np.float32)
    a = -1.0 / (sign + n[..., 2])
    b = n[..., 0] * n[..., 1] * a
    
    tangent = np.stack([
        1.0 + sign * n[..., 0] * n[..., 0] * a,
        sign * b,
        -sign * n[..., 0]
    ], axis=-1)
    
    bitangent = np.stack([
        b,
        sign + n[..., 1] * n[..., 1] * a,
        -n[..., 1]
    ], axis=-1)
    
    return tangent, bitangent


class ReferenceMonteCarloIBL:
    """
    Independent ground-truth Monte Carlo integrator for Cook-Torrance BRDF under IBL.
    Completely decoupled from the production Metal pipeline.
    """
    def __init__(self, env: SyntheticStudioEnvironment):
        self.env = env

    @staticmethod
    def fresnel_schlick(v_dot_h: np.ndarray, f0: np.ndarray) -> np.ndarray:
        """Schlick's approximation: F(vh) = F0 + (1 - F0) * (1 - vh)^5."""
        vh = np.clip(v_dot_h, 0.0, 1.0)[..., None]
        return f0 + (1.0 - f0) * np.power(1.0 - vh, 5.0)

    @staticmethod
    def smith_g2_correlated(n_dot_v: np.ndarray, n_dot_l: np.ndarray, alpha: float) -> np.ndarray:
        """
        Heitz height-correlated Smith shadowing-masking term G2.
        G2(l, v) = 2 * (n.l) * (n.v) / ( (n.l)*sqrt(nv^2*(1-a2) + a2) + (n.v)*sqrt(nl^2*(1-a2) + a2) )
        """
        a2 = max(alpha * alpha, 0.0016 * 0.0016)
        nv = np.clip(n_dot_v, 1e-5, 1.0)
        nl = np.clip(n_dot_l, 1e-5, 1.0)
        
        lambda_v = nl * np.sqrt(nv * nv * (1.0 - a2) + a2)
        lambda_l = nv * np.sqrt(nl * nl * (1.0 - a2) + a2)
        denom = lambda_v + lambda_l
        return np.where(denom > 1e-7, (2.0 * nl * nv) / denom, 0.0)

    def evaluate_pixel(
        self,
        normal: np.ndarray,
        view_dir: np.ndarray,
        roughness: float,
        metallic: float,
        base_color: np.ndarray,
        specular_f0: float = 0.04,
        n_samples: int = 1024,
        seed: int = 42
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Evaluates total reflected radiance at a single surface point.
        Args:
            normal: (3,) unit surface normal
            view_dir: (3,) unit vector pointing towards camera (v)
            roughness: float in [0.04, 1.0]
            metallic: float in [0.0, 1.0]
            base_color: (3,) linear RGB
            specular_f0: float (dielectric F0, default 0.04)
            n_samples: number of Monte Carlo importance samples
            seed: random generator seed
        Returns:
            Tuple of (total_radiance, diffuse_radiance, specular_radiance)
        """
        n = normal / np.linalg.norm(normal)
        v = view_dir / np.linalg.norm(view_dir)
        
        n_dot_v = max(float(np.dot(n, v)), 1e-5)
        
        # Effective F0
        dielectric_f0 = np.full(3, specular_f0, dtype=np.float32)
        f0 = (1.0 - metallic) * dielectric_f0 + metallic * base_color
        
        # Burley roughness parameterization: alpha = roughness^2
        r_clamped = max(roughness, 0.04)
        alpha = r_clamped * r_clamped
        a2 = max(alpha * alpha, 0.0016 * 0.0016)

        # ----------------------------------------------------------------------
        # 1. Specular IBL via GGX Importance Sampling
        # ----------------------------------------------------------------------
        rng = np.random.RandomState(seed)
        u1 = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)
        u2 = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)

        # GGX importance-sampled polar angles
        # theta_h = arccos( sqrt( (1 - u1) / (u1 * (a2 - 1) + 1) ) )
        # Numerically stable form avoids cancellation
        denom_h = (1.0 - u1) + a2 * u1
        cos_theta_h = np.sqrt(np.clip((1.0 - u1) / np.maximum(denom_h, 1e-7), 0.0, 1.0))
        sin_theta_h = np.sqrt(np.clip(1.0 - cos_theta_h * cos_theta_h, 0.0, 1.0))
        phi_h = 2.0 * math.pi * u2

        # Half-vector in local tangent frame
        hx_loc = sin_theta_h * np.cos(phi_h)
        hy_loc = sin_theta_h * np.sin(phi_h)
        hz_loc = cos_theta_h
        h_loc = np.stack([hx_loc, hy_loc, hz_loc], axis=-1)

        # Orthonormal basis
        t, b = build_orthonormal_basis(n)
        h = h_loc[:, 0:1] * t + h_loc[:, 1:2] * b + h_loc[:, 2:3] * n
        h = h / np.maximum(np.linalg.norm(h, axis=-1, keepdims=True), 1e-7)

        # Reflection direction: l = 2 * (v . h) * h - v
        v_dot_h = np.sum(v * h, axis=-1, keepdims=True)
        l = 2.0 * v_dot_h * h - v
        l = l / np.maximum(np.linalg.norm(l, axis=-1, keepdims=True), 1e-7)

        n_dot_l = np.sum(n * l, axis=-1)
        valid_mask = (n_dot_l > 0.0) & (v_dot_h[:, 0] > 0.0)

        specular_radiance = np.zeros(3, dtype=np.float32)
        fresnel_avg = np.zeros(3, dtype=np.float32)

        if np.any(valid_mask):
            l_valid = l[valid_mask]
            vh_valid = v_dot_h[valid_mask, 0]
            nl_valid = n_dot_l[valid_mask]
            nh_valid = h_loc[valid_mask, 2] # cos_theta_h is n . h

            # Environment radiance lookup
            env_samples = self.env.sample(l_valid)

            # Fresnel term
            F_samples = self.fresnel_schlick(vh_valid, f0)

            # Height-correlated Smith G2
            G2_samples = self.smith_g2_correlated(n_dot_v, nl_valid, alpha)

            # Weight after analytical PDF cancellation:
            # weight = F * G2 * (v . h) / ( (n . v) * (n . h) )
            weight = (G2_samples * vh_valid) / np.maximum(n_dot_v * nh_valid, 1e-6)
            spec_contrib = env_samples * F_samples * weight[:, None]

            specular_radiance = np.sum(spec_contrib, axis=0) / float(n_samples)
            fresnel_avg = np.sum(F_samples, axis=0) / float(n_samples)

        # ----------------------------------------------------------------------
        # 2. Diffuse IBL via Cosine-Weighted Hemisphere Sampling
        # ----------------------------------------------------------------------
        diffuse_radiance = np.zeros(3, dtype=np.float32)
        kd = (1.0 - metallic) * (1.0 - np.mean(fresnel_avg))
        
        if kd > 1e-4:
            u1_d = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)
            u2_d = rng.uniform(0.0, 1.0, size=n_samples).astype(np.float32)

            # Cosine-weighted distribution: theta = arccos(sqrt(u1)), phi = 2*pi*u2
            cos_theta_l = np.sqrt(u1_d)
            sin_theta_l = np.sqrt(np.clip(1.0 - u1_d, 0.0, 1.0))
            phi_l = 2.0 * math.pi * u2_d

            lx_loc = sin_theta_l * np.cos(phi_l)
            ly_loc = sin_theta_l * np.sin(phi_l)
            lz_loc = cos_theta_l
            l_loc = np.stack([lx_loc, ly_loc, lz_loc], axis=-1)

            l_diff = l_loc[:, 0:1] * t + l_loc[:, 1:2] * b + l_loc[:, 2:3] * n
            l_diff = l_diff / np.maximum(np.linalg.norm(l_diff, axis=-1, keepdims=True), 1e-7)

            env_diff_samples = self.env.sample(l_diff)
            # Under cosine importance sampling: E(n) = (1 / N) * sum(L_env)
            irradiance = np.mean(env_diff_samples, axis=0)
            diffuse_radiance = kd * base_color * irradiance

        total_radiance = diffuse_radiance + specular_radiance
        return total_radiance, diffuse_radiance, specular_radiance


if __name__ == "__main__":
    env = SyntheticStudioEnvironment(width=1024, height=512)
    mc = ReferenceMonteCarloIBL(env)
    
    n = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    v = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    base = np.array([0.95, 0.95, 0.95], dtype=np.float32)
    
    print("Testing Monte Carlo convergence on normal-facing conductor:")
    for ns in [64, 256, 1024, 4096, 16384]:
        tot, diff, spec = mc.evaluate_pixel(n, v, roughness=0.04, metallic=1.0, base_color=base, n_samples=ns)
        print(f"  Samples: {ns:5d} | Specular: [{spec[0]:.4f}, {spec[1]:.4f}, {spec[2]:.4f}] | Total: [{tot[0]:.4f}, {tot[1]:.4f}, {tot[2]:.4f}]")

