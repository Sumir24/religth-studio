"""
Cook-Torrance Microfacet BRDF Implementation
Relight Studio — RS-SPIKE-3C.2

Formulation:
  f_r(l, v) = (1 - F) * f_diffuse + f_specular
  f_specular = D(h, alpha) * F(v, h, F0) * V(l, v, alpha)

Where:
  - D(h, alpha): GGX / Trowbridge-Reitz Normal Distribution Function
  - F(v, h, F0): Schlick's approximation for Fresnel reflectance
  - V(l, v, alpha): Heitz height-correlated Smith visibility term:
        V(l, v, alpha) = G(l, v, alpha) / (4 * (n . l) * (n . v))
  - alpha = roughness^2 (Burley / Disney perceptually linear roughness reparameterization)
"""

from typing import Union, Tuple
import numpy as np


# Numerical safeguard constants
MIN_ROUGHNESS: float = 0.04      # alpha_min = 0.04^2 = 0.0016 prevents singular delta spike
MIN_ALPHA: float = 0.0016        # Direct alpha floor
EPSILON_DOT: float = 1e-5        # Prevents division by zero in grazing angles
EPSILON_LEN: float = 1e-7        # Prevents division by zero in vector normalization


def clamp_dot(d: np.ndarray) -> np.ndarray:
    """Clamps cosine / dot product to physically valid [0.0, 1.0]."""
    return np.clip(d, 0.0, 1.0)


def safe_normalize(v: np.ndarray, axis: int = -1) -> np.ndarray:
    """Normalizes vector with division-by-zero protection."""
    norm = np.linalg.norm(v, axis=axis, keepdims=True)
    norm = np.maximum(norm, EPSILON_LEN)
    return v / norm


def roughness_to_alpha(roughness: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """
    Converts linear perceptual roughness in [0, 1] to GGX alpha parameter.
    alpha = roughness^2 (Burley parameterization).
    Clamped to [MIN_ALPHA, 1.0] to prevent numerical singularity at zero roughness.
    """
    r = np.clip(roughness, MIN_ROUGHNESS, 1.0)
    return r * r


def distribution_ggx(n_dot_h: np.ndarray, alpha: float) -> np.ndarray:
    """
    GGX / Trowbridge-Reitz Normal Distribution Function.

    D(h) = alpha^2 / (pi * ((n . h)^2 * (alpha^2 - 1) + 1)^2)

    Safeguards:
    - n_dot_h clamped to [0, 1].
    - alpha clamped to MIN_ALPHA.
    """
    a2 = max(alpha * alpha, MIN_ALPHA * MIN_ALPHA)
    nh = clamp_dot(n_dot_h)
    denom = (nh * nh * (a2 - 1.0) + 1.0)
    denom = np.maximum(denom, EPSILON_DOT)
    return a2 / (np.pi * denom * denom)


def fresnel_schlick(
    v_dot_h: np.ndarray,
    f0: Union[float, np.ndarray]
) -> np.ndarray:
    """
    Schlick's approximation for Fresnel reflectance.

    F(v, h) = F0 + (1 - F0) * (1 - (v . h))^5

    Parameters:
    - v_dot_h: Cosine of angle between view direction and microfacet normal (half-vector).
    - f0: Specular reflectance at normal incidence (scalar or RGB array).
    """
    vh = clamp_dot(v_dot_h)
    fresnel_term = np.power(np.maximum(1.0 - vh, 0.0), 5.0)
    if isinstance(f0, np.ndarray):
        # Broadcast across channel dimension
        return f0 + (1.0 - f0) * fresnel_term[..., np.newaxis]
    return f0 + (1.0 - f0) * fresnel_term


def visibility_smith_ggx_correlated(
    n_dot_v: np.ndarray,
    n_dot_l: np.ndarray,
    alpha: float
) -> np.ndarray:
    """
    Heitz height-correlated Smith visibility function:
      V(l, v, alpha) = G(l, v, alpha) / (4 * (n . l) * (n . v))
                     = 0.5 / ((n . v) * sqrt(alpha^2 + (1 - alpha^2)*(n . l)^2) +
                              (n . l) * sqrt(alpha^2 + (1 - alpha^2)*(n . v)^2))

    Benefits:
    - Exactly cancels the 4 * (n . l) * (n . v) Cook-Torrance denominator.
    - Prevents grazing angle explosion without artificial arbitrary clamping.
    """
    a2 = max(alpha * alpha, MIN_ALPHA * MIN_ALPHA)
    nv = clamp_dot(n_dot_v)
    nl = clamp_dot(n_dot_l)

    lambda_v = nl * np.sqrt(nv * nv * (1.0 - a2) + a2)
    lambda_l = nv * np.sqrt(nl * nl * (1.0 - a2) + a2)

    denom = lambda_v + lambda_l
    denom = np.maximum(denom, EPSILON_DOT)
    return 0.5 / denom


def cook_torrance_specular_brdf(
    n: np.ndarray,
    l: np.ndarray,
    v: np.ndarray,
    roughness: float,
    f0: Union[float, np.ndarray]
) -> np.ndarray:
    """
    Evaluates specular microfacet Cook-Torrance BRDF:
      f_specular = D(h, alpha) * F(v, h, F0) * V(l, v, alpha)

    Parameters:
      n: Unit surface normal (..., 3)
      l: Unit light direction (surface to light) (..., 3)
      v: Unit view direction (surface to camera) (..., 3)
      roughness: Linear roughness parameter in [0, 1]
      f0: Reflectance at normal incidence (scalar or RGB array)

    Returns:
      Specular BRDF value f_r (...,) or (..., 3) matching F0 shape.
      Returns 0 where n . l <= 0 or n . v <= 0.
    """
    alpha = roughness_to_alpha(roughness)

    # Compute dot products with surface normal
    n_dot_l = np.sum(n * l, axis=-1)
    n_dot_v = np.sum(n * v, axis=-1)

    # Valid illumination mask: surface must face both light and viewer
    valid_mask = (n_dot_l > 0.0) & (n_dot_v > 0.0)

    # Compute half-vector h = (l + v) / ||l + v||
    h_unnorm = l + v
    h = safe_normalize(h_unnorm, axis=-1)

    n_dot_h = np.sum(n * h, axis=-1)
    v_dot_h = np.sum(v * h, axis=-1)

    # Evaluate terms
    d_term = distribution_ggx(n_dot_h, alpha)
    v_term = visibility_smith_ggx_correlated(n_dot_v, n_dot_l, alpha)
    f_term = fresnel_schlick(v_dot_h, f0)

    # Multiply D * V
    dv = d_term * v_term

    # Combined specular BRDF
    if isinstance(f_term, np.ndarray) and f_term.ndim > dv.ndim:
        f_specular = f_term * dv[..., np.newaxis]
        f_specular = np.where(valid_mask[..., np.newaxis], f_specular, 0.0)
    else:
        f_specular = f_term * dv
        f_specular = np.where(valid_mask, f_specular, 0.0)

    return f_specular


def evaluate_diffuse_specular_brdf(
    n: np.ndarray,
    l: np.ndarray,
    v: np.ndarray,
    albedo: np.ndarray,
    roughness: float,
    metallic: float,
    specular_f0: float = 0.04
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Evaluates energy-conserving diffuse and specular BRDF contributions.

    Energy-conserving material parameterization:
    - F0 = mix(specular_f0, albedo, metallic)
    - diffuse_albedo = albedo * (1.0 - metallic)
    - kd = (1.0 - F) * (1.0 - metallic)
    - f_diffuse = kd * (albedo / pi)
    - f_specular = D * F * V

    Returns:
      (f_diffuse, f_specular)
    """
    albedo = np.asarray(albedo, dtype=np.float32)
    # Metallic material takes albedo as F0, dielectric uses specular_f0 (default 0.04)
    f0 = (1.0 - metallic) * specular_f0 + metallic * albedo

    # Specular BRDF
    f_spec = cook_torrance_specular_brdf(n, l, v, roughness, f0)

    # Diffuse BRDF
    # Compute Fresnel factor at current angle to subtract from diffuse (energy conservation)
    h_unnorm = l + v
    h = safe_normalize(h_unnorm, axis=-1)
    v_dot_h = clamp_dot(np.sum(v * h, axis=-1))
    f_term = fresnel_schlick(v_dot_h, f0)

    # Conductors (metallic=1) have zero diffuse reflection
    kd = (1.0 - f_term) * (1.0 - metallic)
    diffuse_albedo = albedo / np.pi
    f_diff = kd * diffuse_albedo

    n_dot_l = np.sum(n * l, axis=-1)
    n_dot_v = np.sum(n * v, axis=-1)
    valid_mask = (n_dot_l > 0.0) & (n_dot_v > 0.0)

    f_diff = np.where(valid_mask[..., np.newaxis] if f_diff.ndim > valid_mask.ndim else valid_mask, f_diff, 0.0)
    return f_diff, f_spec
