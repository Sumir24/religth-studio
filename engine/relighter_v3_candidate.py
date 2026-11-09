"""
Relight Studio engine v3.
Texture-preserving 3D-aware relighting for a single photo.

Pipeline
  1. sRGB -> linear float (HDR-safe working space)
  2. log-luminance base/detail split with an edge-aware guided filter
     (sub-quantization detail is suppressed = debanding)
  3. geometry: subject mask -> height map -> normals (or user depth/normals)
  4. shading: S_old (assumed original light) and S_new (user lights),
     wrap diffuse + screen-space contact shadows + light pools
  5. regularized, smooth RATIO R = S_new / S_old  (soft-clamped, guided-filtered
     with the BASE layer as guide so no texture leaks into R)
  6. detail coupling:  Y' = Yb*R + Yd*R**lam   (lam=0 locked, lam=1 physical)
  7. smooth colour-temperature tint (luminance neutral), soft highlight shoulder,
     dithered output
  8. metrics + quality gate (auto-reduces strength if checks fail)

Conventions: x right, y down, z toward the viewer. Light positions are in units
where the image short side spans [-1, 1].
"""
from __future__ import annotations

import json
import math
import argparse
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Tuple

import cv2
import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


# ----------------------------------------------------------------- basics
def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0 + 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def srgb_to_linear(x):
    x = np.clip(x.astype(np.float32), 0, None)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(x):
    x = np.clip(x.astype(np.float32), 0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(np.float32)


def luminance(lin):
    return (lin @ LUMA).astype(np.float32)


def box(x, r):
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REFLECT)


def guided_filter(guide, src, radius, eps):
    """He et al. guided filter, single-channel guide, single-channel src (no opencv-contrib needed)."""
    I = guide.astype(np.float32)
    p = src.astype(np.float32)
    mI, mp = box(I, radius), box(p, radius)
    cov = box(I * p, radius) - mI * mp
    var = box(I * I, radius) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    return box(a, radius) * I + box(b, radius)


def soft_clamp_log(x, lo, hi):
    """Smooth limit of a log-ratio to [lo, hi] (lo<0<hi). No hard edges."""
    return hi * np.tanh(np.maximum(x, 0) / hi) + lo * np.tanh(np.minimum(x, 0) / lo)


def kelvin_rgb_rel(K: float) -> np.ndarray:
    """Linear-RGB multiplier of a blackbody light relative to 6500K, luminance-normalized."""
    def raw(k):
        t = k / 100.0
        r = 255 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
        if t >= 66:
            b = 255
        elif t <= 19:
            b = 0
        else:
            b = 138.5177312231 * math.log(t - 10) - 305.0447927307
        return np.clip(np.array([r, g, b], np.float32), 1, 255) / 255.0
    w = srgb_to_linear(raw(K)) / srgb_to_linear(raw(6500.0))
    return (w / float(w @ LUMA)).astype(np.float32)


# ------------------------------------------------------------------- I/O
def load_srgb(path: str) -> np.ndarray:
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im is None:
        raise FileNotFoundError(path)
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    if im.shape[2] == 4:
        im = im[:, :, :3]
    scale = 65535.0 if im.dtype == np.uint16 else 255.0
    return cv2.cvtColor(im.astype(np.float32) / scale, cv2.COLOR_BGR2RGB)


def save_srgb(path: str, rgb: np.ndarray, bits: int = 8):
    bgr = cv2.cvtColor(np.clip(rgb, 0, 1).astype(np.float32), cv2.COLOR_RGB2BGR)
    if bits == 16:
        cv2.imwrite(path, np.round(bgr * 65535).astype(np.uint16))
    else:
        cv2.imwrite(path, np.round(bgr * 255).astype(np.uint8))


# ----------------------------------------------------------------- lights
@dataclass
class Light:
    kind: str = "directional"          # directional | point | spot
    pos: Tuple[float, float, float] = (-0.7, -0.3, 0.6)  # directional: direction TO the light
    intensity: float = 1.0
    kelvin: float = 6500.0
    k1: float = 0.0                     # point/spot linear falloff
    k2: float = 0.6                     # point/spot quadratic falloff
    spot_dir: Tuple[float, float, float] = (0.0, 0.0, -1.0)
    spot_inner_deg: float = 20.0
    spot_outer_deg: float = 40.0
    pool: float = 0.0                   # 0..1 : light pool on the backdrop around the light's projection
    pool_radius: float = 0.9
    shadow: float = 0.8                 # contact-shadow strength 0..1


@dataclass
class Params:
    lam: float = 0.7                    # detail coupling: 0 locked .. 1 physical
    strength: float = 1.0               # scales the log-ratio (and tint) 0..1
    r_min: float = 0.30
    r_max: float = 3.00
    ambient_new: float = 0.30
    ambient_old: float = 0.65
    wrap: float = 0.25
    ratio_eps: float = 0.05
    keep_exposure: bool = True
    tint_strength: float = 1.0
    depth_scale: float = 0.25           # subject height as fraction of short side
    lum_height: float = 0.35            # how much base luminance shapes the proxy height
    invert_lum: bool = False
    deband: float = 1.0                 # detail below ~1 LSB*deband is treated as quantization
    base_radius_frac: float = 0.008
    base_eps: float = 2e-3
    ratio_radius_frac: float = 0.015
    ratio_eps_guided: float = 1e-2
    shadow_steps: int = 24
    shadow_dist_frac: float = 0.12
    dither: bool = True


FLAT_OLD = [Light("directional", (0.0, -0.3, 1.0), 0.35)]

PRESETS: Dict[str, List[Light]] = {
    "warm_key_cool_rim": [
        Light("directional", (-0.8, -0.25, 0.55), 1.0, 3600, pool=0.5),
        Light("directional", (0.9, -0.3, 0.25), 0.8, 8000, shadow=0.0),
    ],
    "top_softbox": [Light("directional", (0.0, -0.9, 0.45), 1.1, 5600, pool=0.4)],
    "left_key": [Light("directional", (-0.8, -0.2, 0.5), 1.1, 5600, pool=0.4)],
    "right_heel_point": [Light("point", (0.7, -0.2, 0.5), 1.4, 4500, k2=0.8, pool=0.6)],
    "floor_uplight": [Light("directional", (0.0, 0.6, 0.3), 1.0, 4000, pool=0.3)],
    "three_point": [
        Light("directional", (-0.7, -0.4, 0.6), 1.0, 5200, pool=0.3),
        Light("directional", (0.8, -0.2, 0.2), 0.7, 8500, shadow=0.0),
        Light("directional", (0.3, 0.2, 0.9), 0.35, 4300, shadow=0.0),
    ],
}


# --------------------------------------------------------------- geometry
def _fill_largest(m: np.ndarray) -> np.ndarray:
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = np.zeros(m.shape, np.uint8)
    if cnts:
        cv2.drawContours(out, [max(cnts, key=cv2.contourArea)], -1, 1, thickness=-1)
    return out


def auto_mask(srgb: np.ndarray) -> np.ndarray:
    """Soft subject mask. FALLBACK ONLY: use a matting model (e.g. BiRefNet) in production.
    1) GrabCut from a frame rectangle  2) flat-backdrop colour key  3) centred ellipse."""
    H, W, _ = srgb.shape
    sc = 0.5
    sm = cv2.cvtColor(cv2.resize((srgb * 255).astype(np.uint8), (int(W * sc), int(H * sc)),
                                 interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR)
    h, w = sm.shape[:2]
    mx, my = max(2, int(0.015 * w)), max(2, int(0.015 * h))
    gm = np.zeros((h, w), np.uint8)
    try:
        cv2.grabCut(sm, gm, (mx, my, w - 2 * mx, h - 2 * my), np.zeros((1, 65)), np.zeros((1, 65)), 6,
                    cv2.GC_INIT_WITH_RECT)
        m = _fill_largest(cv2.resize(((gm == 1) | (gm == 3)).astype(np.uint8), (W, H),
                                     interpolation=cv2.INTER_NEAREST))
    except cv2.error:
        m = np.zeros((H, W), np.uint8)
    cov = float(m.mean())
    if cov < 0.12 or cov > 0.97:
        # flat-backdrop key: most common colour among FLAT border pixels is the backdrop
        lab = cv2.cvtColor(srgb.astype(np.float32), cv2.COLOR_RGB2Lab)
        Lc = lab[..., 0]
        mu = cv2.GaussianBlur(Lc, (0, 0), 2.0)
        tex_all = np.sqrt(np.maximum(cv2.GaussianBlur(Lc * Lc, (0, 0), 2.0) - mu * mu, 0))
        flat = tex_all < 0.6
        bw = max(3, int(0.02 * min(H, W)))
        edge = np.zeros((H, W), bool)
        edge[:bw] = edge[-bw:] = True
        edge[:, :bw] = edge[:, -bw:] = True
        cand = lab[flat & edge]
        if len(cand) > 200:
            q = np.round(cand / 4.0).astype(np.int32)
            keys, counts = np.unique(q, axis=0, return_counts=True)
            order = np.argsort(-counts)
            picked, best = [], None
            for idx in order[:12]:                         # distinct candidate backdrop colours
                c_ = keys[idx] * 4.0
                if any(np.linalg.norm(c_ - o) < 12 for o in picked):
                    continue
                picked.append(c_)
                if len(picked) > 3:
                    break
                d = cv2.GaussianBlur(np.linalg.norm(lab - c_, axis=2), (0, 0), 1.0)
                kk = max(3, int(0.012 * min(H, W)) | 1)
                se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kk, kk))
                m2 = cv2.morphologyEx((d > 6.0).astype(np.uint8), cv2.MORPH_CLOSE, se)
                m2 = _fill_largest(cv2.morphologyEx(m2, cv2.MORPH_OPEN, se))
                cv_ = float(m2.mean())
                if not (0.03 <= cv_ <= 0.97):
                    continue
                best = (0.0, m2)                              # candidates are in descending frequency order
                break
            if best is not None:
                m = best[1]
    cov = float(m.mean())
    if cov < 0.03 or cov > 0.97:                       # detection failed: centred ellipse
        m = np.zeros((H, W), np.uint8)
        cv2.ellipse(m, (W // 2, H // 2), (int(W * 0.42), int(H * 0.42)), 0, 0, 360, 1, -1)
    return cv2.GaussianBlur(m.astype(np.float32), (0, 0), max(1.0, 0.004 * max(H, W)))


def build_height(mask, base_gamma, p: Params, depth: Optional[np.ndarray] = None) -> np.ndarray:
    """Height (in pixels, toward viewer). Uses user depth if given, else dome(mask) + luminance proxy."""
    H, W = mask.shape
    short, long_ = min(H, W), max(H, W)
    if depth is not None:
        d = cv2.resize(depth.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)
        d = (d - d.min()) / (d.max() - d.min() + 1e-6)
        h = d * p.depth_scale * short
    else:
        m8 = (mask > 0.5).astype(np.uint8)
        dist = cv2.distanceTransform(m8, cv2.DIST_L2, 5)
        dome = np.sqrt(dist / (dist.max() + 1e-6))
        lum = base_gamma - (base_gamma * mask).sum() / (mask.sum() + 1e-6)
        lum = lum * (-1.0 if p.invert_lum else 1.0)
        hn = (1.0 - p.lum_height) * dome + p.lum_height * lum * mask * 1.5
        h = np.clip(hn, 0, None) * p.depth_scale * short
    return cv2.GaussianBlur(h.astype(np.float32), (0, 0), 0.012 * long_)


def normals_from_height(h: np.ndarray, gain: float = 1.0) -> np.ndarray:
    hx = cv2.Sobel(h, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    hy = cv2.Sobel(h, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    N = np.dstack([-hx * gain, -hy * gain, np.ones_like(h)])
    return N / np.linalg.norm(N, axis=2, keepdims=True)


def positions(h: np.ndarray) -> Tuple[np.ndarray, float, Tuple[float, float]]:
    H, W = h.shape
    S = min(H, W) / 2.0
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    xs, ys = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    P = np.dstack([(xs - cx) / S, (ys - cy) / S, h / S]).astype(np.float32)
    return P, S, (cx, cy)


# ---------------------------------------------------------------- shading
def contact_shadow(h, l, steps, dist_frac, softness_px):
    """Screen-space ray march toward the light over the height field. Returns occlusion 0..1."""
    H, W = h.shape
    lxy = l[..., :2]
    nxy = np.linalg.norm(lxy, axis=2) + 1e-6
    dirx, diry = lxy[..., 0] / nxy, lxy[..., 1] / nxy
    slope = np.maximum(l[..., 2], 0.05) / nxy
    xs, ys = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    maxd = dist_frac * max(H, W)
    occ = np.zeros((H, W), np.float32)
    for i in range(1, steps + 1):
        d = maxd * (i / steps) ** 1.5
        hs = cv2.remap(h, (xs + dirx * d).astype(np.float32), (ys + diry * d).astype(np.float32),
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        pen = (hs - (h + slope * d)) / softness_px
        occ = np.maximum(occ, smoothstep(0.0, 1.0, pen))
    return occ


def light_vectors(L: Light, P):
    H, W, _ = P.shape
    if L.kind == "directional":
        d = np.array(L.pos, np.float32)
        d /= np.linalg.norm(d)
        return np.broadcast_to(d, (H, W, 3)).copy(), np.ones((H, W), np.float32)
    v = np.array(L.pos, np.float32)[None, None, :] - P
    r = np.linalg.norm(v, axis=2, keepdims=True) + 1e-4
    l = v / r
    att = 1.0 / (1.0 + L.k1 * r[..., 0] + L.k2 * r[..., 0] ** 2)
    if L.kind == "spot":
        sd = np.array(L.spot_dir, np.float32)
        sd /= np.linalg.norm(sd)
        cosang = -(l * sd).sum(axis=2)
        att = att * smoothstep(math.cos(math.radians(L.spot_outer_deg)),
                               math.cos(math.radians(L.spot_inner_deg)), cosang)
    return l.astype(np.float32), att.astype(np.float32)


def shade(N, P, h, S, c, lights: List[Light], ambient, p: Params, shadows=True):
    H, W = h.shape
    total = np.full((H, W), ambient, np.float32)
    gains = []
    xs, ys = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    for L in lights:
        l, att = light_vectors(L, P)
        ndl = (N * l).sum(axis=2)
        diff = np.clip((ndl + p.wrap) / (1.0 + p.wrap), 0, 1) ** 1.1
        vis = np.ones((H, W), np.float32)
        if shadows and L.shadow > 0:
            occ = contact_shadow(h, l, p.shadow_steps, p.shadow_dist_frac, 0.03 * S)
            occ = cv2.GaussianBlur(occ, (0, 0), 0.004 * max(H, W))
            vis = 1.0 - L.shadow * occ
        pool = np.ones((H, W), np.float32)
        if L.pool > 0:
            if L.kind == "directional":
                d = np.array(L.pos, np.float32)
                d /= np.linalg.norm(d)
                px, py = c[0] + d[0] * S * 1.6, c[1] + d[1] * S * 1.6
            else:
                px, py = c[0] + L.pos[0] * S, c[1] + L.pos[1] * S
            g = np.exp(-((xs - px) ** 2 + (ys - py) ** 2) / (2 * (L.pool_radius * S) ** 2))
            pool = (1 - L.pool) + L.pool * g.astype(np.float32)
        g_k = (L.intensity * att * diff * vis * pool).astype(np.float32)
        gains.append(g_k)
        total += g_k
    return total, gains


# -------------------------------------------------------------- relighting
@dataclass
class Result:
    relit_lin: np.ndarray          # tone-mapped linear (pre-dither)
    relit_srgb: np.ndarray         # final float sRGB in [0,1] (dithered)
    ratio: np.ndarray              # R actually applied
    logR: np.ndarray
    mask: np.ndarray
    height: np.ndarray
    lam: float
    strength: float


def tone_map(rgb, knee=0.8, top=1.15):
    m = rgb.max(axis=2, keepdims=True)
    comp = knee + (top - knee) * np.tanh((m - knee) / (top - knee))
    f = np.where(m > knee, comp / np.maximum(m, 1e-6), 1.0)
    return np.clip(rgb * f, 0, 1)


def decompose(lin, p: Params):
    Y = np.maximum(luminance(lin), 1e-4)
    logY = np.log(Y)
    guide = linear_to_srgb(Y)
    long_ = max(Y.shape)
    r = max(4, int(round(p.base_radius_frac * long_)))
    B = guided_filter(guide, logY, r, p.base_eps)
    D = logY - B
    t = p.deband * (2.4 / 255.0) / np.maximum(guide, 0.05)       # ~1 LSB in log-luminance
    D = D * smoothstep(t, 2 * t, np.abs(D))                       # drop sub-LSB residual (banding)
    Yb = np.exp(B)
    Yd = np.exp(B + D) - Yb
    return Y, Yb, Yd


def relight(srgb, lights: List[Light], old_lights: Optional[List[Light]] = None,
            p: Optional[Params] = None, depth: Optional[np.ndarray] = None,
            mask: Optional[np.ndarray] = None, rng: Optional[np.random.Generator] = None) -> Result:
    p = p or Params()
    old_lights = old_lights if old_lights is not None else FLAT_OLD
    rng = rng or np.random.default_rng(0)
    H, W, _ = srgb.shape
    long_ = max(H, W)

    lin = srgb_to_linear(srgb)
    Y, Yb, Yd = decompose(lin, p)
    base_gamma = linear_to_srgb(Yb)

    if mask is None:
        mask = auto_mask(srgb)
    h = build_height(mask, base_gamma, p, depth)
    N = normals_from_height(h)
    P, S, c = positions(h)

    S_old, _ = shade(N, P, h, S, c, old_lights, p.ambient_old, p, shadows=False)
    S_new, gains = shade(N, P, h, S, c, lights, p.ambient_new, p, shadows=True)
    inside = mask > 0.5
    if p.keep_exposure and inside.any():
        k = np.median(S_old[inside]) / max(np.median(S_new[inside]), 1e-4)
        S_new = S_new * k
        gains = [g * k for g in gains]

    logR = np.log((S_new + p.ratio_eps) / (S_old + p.ratio_eps))
    logR = soft_clamp_log(logR, math.log(p.r_min), math.log(p.r_max))
    r_r = max(8, int(round(p.ratio_radius_frac * long_)))
    logR = guided_filter(base_gamma, logR, r_r, p.ratio_eps_guided)   # BASE as guide: no texture leaks into R
    logR = logR * p.strength
    R = np.exp(logR).astype(np.float32)

    Y2 = np.maximum(Yb * R + Yd * np.power(R, p.lam), 0.0)
    scale = (Y2 / Y)[..., None]

    # colour temperature: luminance-neutral, smooth, relative to a neutral (6500K) original light
    tot = np.maximum(S_new, 1e-4)
    tint = np.ones((H, W, 3), np.float32)
    for L, g in zip(lights, gains):
        frac = np.clip(g / tot, 0, 1)[..., None]
        tint += p.tint_strength * p.strength * frac * (kelvin_rgb_rel(L.kelvin)[None, None, :] - 1.0)
    tint = cv2.GaussianBlur(tint, (0, 0), 0.004 * long_)
    tint = tint / (tint @ LUMA)[..., None]

    out_lin = tone_map(lin * scale * tint)
    out = linear_to_srgb(out_lin)
    if p.dither:
        out = out + ((rng.random(out.shape) - rng.random(out.shape)) / 255.0).astype(np.float32)
    out = np.clip(out, 0, 1).astype(np.float32)
    return Result(out_lin, out, R, logR, mask, h, p.lam, p.strength)


# -------------------------------------------------- hybrid (Smart mode core)
def ratio_transfer(orig_srgb, gen_srgb, p: Optional[Params] = None, sigma_frac: float = 0.02,
                   mask: Optional[np.ndarray] = None) -> Result:
    """
    Take lighting from a generated/neural relit image (low frequencies only) and apply it to the
    ORIGINAL photo with detail coupling. All high-frequency content of `gen` is discarded.
    """
    p = p or Params()
    H, W, _ = orig_srgb.shape
    gen = cv2.resize(gen_srgb, (W, H), interpolation=cv2.INTER_AREA) if gen_srgb.shape[:2] != (H, W) else gen_srgb
    lin = srgb_to_linear(orig_srgb)
    lg = srgb_to_linear(gen)
    Y, Yb, Yd = decompose(lin, p)
    sig = sigma_frac * max(H, W)
    lo = cv2.GaussianBlur(lin, (0, 0), sig)
    lgl = cv2.GaussianBlur(lg, (0, 0), sig)
    Rc = (lgl + 0.02) / (lo + 0.02)                       # per-channel low-pass ratio
    Rl = (Rc @ LUMA)
    logR = soft_clamp_log(np.log(Rl), math.log(p.r_min), math.log(p.r_max))
    base_gamma = linear_to_srgb(Yb)
    r_r = max(8, int(round(p.ratio_radius_frac * max(H, W))))
    logR = guided_filter(base_gamma, logR, r_r, p.ratio_eps_guided) * p.strength
    R = np.exp(logR).astype(np.float32)
    tint = Rc / np.maximum(Rl, 1e-4)[..., None]
    tint = np.clip(tint, 0.5, 2.0)
    tint = 1.0 + p.strength * p.tint_strength * (tint - 1.0)
    tint = cv2.GaussianBlur(tint, (0, 0), 0.004 * max(H, W))
    tint = tint / (tint @ LUMA)[..., None]
    Y2 = np.maximum(Yb * R + Yd * np.power(R, p.lam), 0.0)
    out_lin = tone_map(lin * (Y2 / Y)[..., None] * tint)
    out = linear_to_srgb(out_lin)
    if p.dither:
        rng = np.random.default_rng(0)
        out = out + ((rng.random(out.shape) - rng.random(out.shape)) / 255.0).astype(np.float32)
    out = np.clip(out, 0, 1).astype(np.float32)
    m = mask if mask is not None else auto_mask(orig_srgb)
    return Result(out_lin, out, R, logR, m, np.zeros((H, W), np.float32), p.lam, p.strength)


# ------------------------------------------------------------------ metrics
def _hp(x, sigma):
    return x - cv2.GaussianBlur(x, (0, 0), sigma)


def _block_rms(x, bs=32):
    H, W = x.shape
    x = x[: H // bs * bs, : W // bs * bs]
    return np.sqrt((x.reshape(H // bs, bs, W // bs, bs) ** 2).mean(axis=(1, 3)))


def _block_mean(x, bs=32):
    H, W = x.shape
    x = x[: H // bs * bs, : W // bs * bs]
    return x.reshape(H // bs, bs, W // bs, bs).mean(axis=(1, 3))


def _coherence(r, mask, sigma=3.0):
    r = cv2.GaussianBlur(r, (0, 0), 0.7)
    gx, gy = cv2.Sobel(r, cv2.CV_32F, 1, 0), cv2.Sobel(r, cv2.CV_32F, 0, 1)
    Jxx = cv2.GaussianBlur(gx * gx, (0, 0), sigma)
    Jyy = cv2.GaussianBlur(gy * gy, (0, 0), sigma)
    Jxy = cv2.GaussianBlur(gx * gy, (0, 0), sigma)
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / (Jxx + Jyy + 1e-12)
    w = (Jxx + Jyy) * mask
    return float((coh * w).sum() / (w.sum() + 1e-12))


def banding_score(srgb):
    """Structured (line-like) residual energy in smooth regions. White noise ~0.1-0.3, contour lines ~0.7+."""
    Ys = linear_to_srgb(luminance(srgb_to_linear(srgb)))
    smooth = cv2.GaussianBlur(Ys, (0, 0), 3.0)
    res = Ys - cv2.GaussianBlur(Ys, (0, 0), 2.0)
    gmag = np.hypot(cv2.Sobel(smooth, cv2.CV_32F, 1, 0), cv2.Sobel(smooth, cv2.CV_32F, 0, 1)) / 8.0
    lvar = cv2.GaussianBlur(res * res, (0, 0), 6.0)
    mask = ((gmag < 0.01) & (lvar < 0.012 ** 2)).astype(np.float32)
    return _coherence(res, mask), float(mask.mean())


def compute_metrics(orig_srgb, res: Result, p: Params) -> Dict[str, float]:
    H, W, _ = orig_srgb.shape
    sig = 0.004 * max(H, W)
    Yo = np.log(np.maximum(luminance(srgb_to_linear(orig_srgb)), 1e-4))
    Yr = np.log(np.maximum(luminance(srgb_to_linear(res.relit_srgb)), 1e-4))
    ro, rr = _block_rms(_hp(Yo, sig)), _block_rms(_hp(Yr, sig))
    Rb = _block_mean(res.logR)
    valid = ro > 0.01
    if valid.sum() > 5:
        meas = np.log(np.maximum(rr, 1e-6) / ro)[valid]
        exp_ = ((res.lam - 1.0) * Rb)[valid]
        detail_ratio = float(np.exp(np.median(meas)))
        detail_err = float(np.median(np.abs(meas - exp_)))
    else:
        detail_ratio, detail_err = float("nan"), 0.0
    b0, frac0 = banding_score(orig_srgb)
    b1, frac1 = banding_score(res.relit_srgb)
    lab_o = cv2.cvtColor(orig_srgb.astype(np.float32), cv2.COLOR_RGB2Lab)
    lab_r = cv2.cvtColor(res.relit_srgb.astype(np.float32), cv2.COLOR_RGB2Lab)
    inside = res.mask > 0.5
    dc = np.linalg.norm(lab_r[..., 1:] - lab_o[..., 1:], axis=2)
    chroma_p95 = float(np.percentile(dc[inside], 95)) if inside.any() else 0.0
    out = res.relit_srgb
    return {
        "detail_ratio_median": detail_ratio,
        "detail_lock_error_log": detail_err,
        "banding_orig": b0,
        "banding_relit": b1,
        "banding_gain": b1 - b0,
        "smooth_area_frac": frac1,
        "chroma_shift_p95_in_subject": chroma_p95,
        "min": float(out.min()), "max": float(out.max()),
        "finite": bool(np.isfinite(out).all()),
    }


def quality_gate(m: Dict[str, float], max_banding_gain=0.10, max_detail_err=0.25) -> Tuple[bool, List[str]]:
    fails = []
    if not m["finite"] or m["min"] < 0 or m["max"] > 1:
        fails.append("range/NaN")
    if m["banding_gain"] > max_banding_gain:
        fails.append(f"banding +{m['banding_gain']:.2f}")
    if m["detail_lock_error_log"] > max_detail_err:
        fails.append(f"detail lock error {m['detail_lock_error_log']:.2f}")
    return (not fails), fails


def relight_with_gate(srgb, lights, old_lights=None, p: Optional[Params] = None, depth=None, mask=None,
                      levels=(1.0, 0.75, 0.5, 0.25)):
    """Run relight; if a quality check fails, reduce strength and retry. Returns (result, metrics, log)."""
    p = p or Params()
    log = []
    last = None
    for s in levels:
        q = Params(**{**asdict(p), "strength": p.strength * s})
        res = relight(srgb, lights, old_lights, q, depth, mask)
        m = compute_metrics(srgb, res, q)
        ok, fails = quality_gate(m)
        log.append({"strength": q.strength, "ok": ok, "fails": fails})
        last = (res, m)
        if ok:
            break
    return last[0], last[1], log


# -------------------------------------------------------------- visual board
def lock_error_map(orig_srgb, res: Result, amp=8.0):
    H, W, _ = orig_srgb.shape
    sig = 0.004 * max(H, W)
    Yo = np.log(np.maximum(luminance(srgb_to_linear(orig_srgb)), 1e-4))
    Yr = np.log(np.maximum(luminance(srgb_to_linear(res.relit_srgb)), 1e-4))
    err = np.abs(_hp(Yr, sig) - _hp(Yo, sig) * np.exp((res.lam - 1.0) * res.logR))
    v = np.clip(err * amp, 0, 1)
    cm = cv2.applyColorMap((v * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    return cv2.cvtColor(cm, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0


def ratio_map(res: Result):
    v = np.clip(res.logR / math.log(2) * 0.5 + 0.5, 0, 1)
    cm = cv2.applyColorMap((v * 255).astype(np.uint8), cv2.COLORMAP_TWILIGHT_SHIFTED)
    return cv2.cvtColor(cm, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0


def make_board(orig, res: Result, m: Dict[str, float], title: str, path: str):
    from PIL import Image, ImageDraw, ImageFont
    H, W, _ = orig.shape
    # aligned 300% crop at the strongest texture, identical coords for both
    Yo = luminance(srgb_to_linear(orig))
    en = cv2.GaussianBlur(_hp(Yo, 2.0) ** 2, (0, 0), 12.0) * (res.mask > 0.5)
    cy, cx = np.unravel_index(int(en.argmax()), en.shape)
    cw, ch = W // 6, H // 3
    x0 = int(np.clip(cx - cw // 2, 0, W - cw)); y0 = int(np.clip(cy - ch // 2, 0, H - ch))
    a = orig[y0:y0 + ch, x0:x0 + cw]; b = res.relit_srgb[y0:y0 + ch, x0:x0 + cw]
    pair = np.concatenate([a, np.ones((ch, 2, 3), np.float32), b], axis=1)
    pair = cv2.resize(pair, (pair.shape[1] * 3, pair.shape[0] * 3), interpolation=cv2.INTER_NEAREST)
    canvas = np.zeros((H, pair.shape[1], 3), np.float32); canvas[:pair.shape[0]] = pair
    marker = orig.copy(); cv2.rectangle(marker, (x0, y0), (x0 + cw, y0 + ch), (1, 0.2, 0.2), 2)
    panels = [(marker, "1. ORIGINAL", f"red box = crop region"),
              (ratio_map(res), "2. SHADING RATIO R", "blue = darker, red = brighter (log scale)"),
              (res.relit_srgb, "3. RELIT", f"lam={res.lam:.2f} strength={res.strength:.2f}"),
              (lock_error_map(orig, res), "4. DETAIL-LOCK ERROR", "black = detail exactly as expected"),
              (canvas, "5. ALIGNED 300% CROP", "left original | right relit, same coords")]
    metr = (f"detail ratio {m['detail_ratio_median']:.2f} | lock err {m['detail_lock_error_log']:.3f} | "
            f"banding {m['banding_orig']:.2f}->{m['banding_relit']:.2f}")
    
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    f1 = f2 = None
    for fp in font_paths:
        try:
            f1 = ImageFont.truetype(fp, 15)
            f2 = ImageFont.truetype(fp, 11)
            break
        except Exception:
            continue
    if f1 is None:
        f1 = f2 = ImageFont.load_default()

    widths = [p_[0].shape[1] for p_ in panels]
    bar = 62
    img = Image.new("RGB", (sum(widths), H + bar + 22), (24, 24, 26))
    d = ImageDraw.Draw(img)
    x = 0
    for (im, t1, t2), w_ in zip(panels, widths):
        d.text((x + 10, 8), t1, fill=(255, 255, 255), font=f1)
        d.text((x + 10, 32), t2, fill=(170, 170, 175), font=f2)
        img.paste(Image.fromarray((np.clip(im, 0, 1) * 255).astype(np.uint8)), (x, bar))
        x += w_
    d.text((10, H + bar + 4), f"{title}   {metr}", fill=(200, 200, 205), font=f2)
    img.save(path)


# ---------------------------------------------------------------------- CLI
def lights_from_arg(arg: str) -> List[Light]:
    if arg in PRESETS:
        return PRESETS[arg]
    with open(arg) as f:
        return [Light(**{**d, **({"pos": tuple(d["pos"])} if "pos" in d else {})}) for d in json.load(f)]


def main():
    ap = argparse.ArgumentParser(description="Relight Studio engine v3")
    ap.add_argument("input"); ap.add_argument("output")
    ap.add_argument("--preset", default="warm_key_cool_rim", help=f"{list(PRESETS)} or path to lights JSON")
    ap.add_argument("--lam", type=float, default=0.7)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--depth", help="optional .npy depth (near=large)")
    ap.add_argument("--mask", help="optional mask image (white=subject)")
    ap.add_argument("--no-gate", action="store_true")
    ap.add_argument("--bits", type=int, default=8, choices=[8, 16])
    ap.add_argument("--board", help="write verification board png")
    ap.add_argument("--report", help="write metrics json")
    a = ap.parse_args()

    srgb = load_srgb(a.input)
    p = Params(lam=a.lam, strength=a.strength)
    depth = np.load(a.depth) if a.depth else None
    mask = (cv2.imread(a.mask, 0).astype(np.float32) / 255.0) if a.mask else None
    lights = lights_from_arg(a.preset)
    if a.no_gate:
        res = relight(srgb, lights, None, p, depth, mask)
        m = compute_metrics(srgb, res, p); log = []
    else:
        res, m, log = relight_with_gate(srgb, lights, None, p, depth, mask)
    save_srgb(a.output, res.relit_srgb, a.bits)
    if a.board:
        make_board(srgb, res, m, a.preset, a.board)
    if a.report:
        with open(a.report, "w") as f:
            json.dump({"metrics": m, "gate_log": log}, f, indent=2)
    print(json.dumps({"metrics": m, "gate_log": log}, indent=2))


if __name__ == "__main__":
    main()

