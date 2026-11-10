"""
Independent Ground-Truth Mathematical BRDF Reference.
Relight Studio — RS-SPIKE-3C.2.1 Audit

This file is authored independently from studio3a/brdf.py.
It implements Cook-Torrance microfacet BRDF directly from academic literature:
- Trowbridge & Reitz (1975) / Walter et al. (2007) GGX NDF
- Heitz (2014) height-correlated Smith masking-shadowing
- Schlick (1994) Fresnel approximation
- Burley (2012) Disney perceptual roughness mapping: alpha = roughness^2
"""

import math
from typing import Tuple, Union
import numpy as np


class IndependentBRDFReference:
    """
    Independent high-precision reference implementation of Cook-Torrance GGX BRDF.
    Uses double-precision float64 for all calculations.
    """
    MIN_ROUGHNESS = 0.04
    MIN_ALPHA = 0.0016  # 0.04^2

    @classmethod
    def roughness_to_alpha(cls, roughness: float) -> float:
        r = max(float(roughness), cls.MIN_ROUGHNESS)
        r = min(r, 1.0)
        return r * r

    @classmethod
    def ggx_d(cls, n_dot_h: float, alpha: float) -> float:
        """
        Trowbridge-Reitz GGX Normal Distribution Function:
        D(h) = alpha^2 / (pi * ((n.h)^2 * (alpha^2 - 1) + 1)^2)
        """
        nh = max(0.0, min(1.0, float(n_dot_h)))
        a = max(float(alpha), cls.MIN_ALPHA)
        a2 = a * a
        denom = nh * nh * (a2 - 1.0) + 1.0
        return a2 / (math.pi * denom * denom)

    @classmethod
    def fresnel_schlick(cls, v_dot_h: float, f0: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
        """
        Schlick's approximation for Fresnel reflectance:
        F(v, h) = F0 + (1 - F0) * (1 - v.h)^5
        """
        vh = max(0.0, min(1.0, float(v_dot_h)))
        spherical_gaussian = (1.0 - vh) ** 5.0
        if isinstance(f0, np.ndarray):
            f0_arr = f0.astype(np.float64)
            return f0_arr + (1.0 - f0_arr) * spherical_gaussian
        return float(f0) + (1.0 - float(f0)) * spherical_gaussian

    @classmethod
    def smith_g2_height_correlated_vis(cls, n_dot_v: float, n_dot_l: float, alpha: float) -> float:
        """
        Heitz (2014) height-correlated Smith visibility function:
        V(l, v) = G2(l, v) / (4 * (n.l) * (n.v))
                = 0.5 / ( (n.v)*sqrt((n.l)^2 * (1 - a^2) + a^2) + (n.l)*sqrt((n.v)^2 * (1 - a^2) + a^2) )
        """
        nv = max(0.0, min(1.0, float(n_dot_v)))
        nl = max(0.0, min(1.0, float(n_dot_l)))
        if nv <= 0.0 or nl <= 0.0:
            return 0.0

        a = max(float(alpha), cls.MIN_ALPHA)
        a2 = a * a
        lambda_v = nl * math.sqrt(nv * nv * (1.0 - a2) + a2)
        lambda_l = nv * math.sqrt(nl * nl * (1.0 - a2) + a2)
        denom = lambda_v + lambda_l
        if denom < 1e-15:
            return 0.0
        return 0.5 / denom

    @classmethod
    def cook_torrance_specular(
        cls,
        n: np.ndarray,
        l: np.ndarray,
        v: np.ndarray,
        roughness: float,
        f0: Union[float, np.ndarray]
    ) -> Union[float, np.ndarray]:
        """
        Complete specular Cook-Torrance BRDF:
        f_spec = D * V * F
        """
        n_u = n / np.linalg.norm(n)
        l_u = l / np.linalg.norm(l)
        v_u = v / np.linalg.norm(v)

        nl = float(np.dot(n_u, l_u))
        nv = float(np.dot(n_u, v_u))

        if nl <= 0.0 or nv <= 0.0:
            if isinstance(f0, np.ndarray):
                return np.zeros_like(f0, dtype=np.float64)
            return 0.0

        h = l_u + v_u
        h_norm = np.linalg.norm(h)
        if h_norm < 1e-12:
            if isinstance(f0, np.ndarray):
                return np.zeros_like(f0, dtype=np.float64)
            return 0.0
        h_u = h / h_norm

        nh = float(np.dot(n_u, h_u))
        vh = float(np.dot(v_u, h_u))

        alpha = cls.roughness_to_alpha(roughness)
        d_val = cls.ggx_d(nh, alpha)
        v_val = cls.smith_g2_height_correlated_vis(nv, nl, alpha)
        f_val = cls.fresnel_schlick(vh, f0)

        return d_val * v_val * f_val
