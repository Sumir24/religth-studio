"""
Relight Studio engine v4
Texture-preserving 3D-aware relighting of a single photo, with lights from ANY side.

Light placement (photographer-friendly polar coordinates)
    azimuth   0 = from the TOP of the frame, 90 = from the RIGHT, 180 = from BELOW, 270 = from the LEFT
    elevation +90 = straight at the camera (frontal), 0 = grazing across the frame,
              negative = from BEHIND the subject (back / rim light), -90 = directly behind
    distance  scene units (image short side spans [-1, 1]); `intensity` is the irradiance at the scene
              centre, so moving a light changes its falloff pattern, not its overall brightness.

Light types
    directional  sun / distant key        point    bulb / lamp (inverse-square falloff)
    spot         cone + soft edge         area     rectangular softbox (sampled -> soft shadows & wide speculars)
    ring         ring light (catchlights) hemisphere  sky above / ground bounce below (ambient fill)
    rim          edge / back light with Fresnel-style glow at the silhouette

Pipeline (unchanged philosophy)
    linear light -> log-luminance base/detail split (debanded) -> mask/height/normals (+ silhouette bending)
    -> shading S_old vs S_new -> smooth regularized ratio R (mask-aware guided filter) ->
    Y' = Yb*R + Yd*R**lam -> colour-temperature tint -> GGX specular layer (additive, smooth) ->
    soft highlight shoulder -> dithered output -> metrics + quality gate.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


# ------------------------------------------------------------------ basics
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
    I = guide.astype(np.float32)
    p = src.astype(np.float32)
    mI, mp = box(I, radius), box(p, radius)
    cov = box(I * p, radius) - mI * mp
    var = box(I * I, radius) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    return box(a, radius) * I + box(b, radius)


def masked_guided(guide, x, m, radius, eps):
    """Guided filter that does not bleed across the subject boundary (kills silhouette halos)."""
    m = np.clip(m, 0, 1).astype(np.float32)
    out = np.zeros_like(x, np.float32)
    for w in (m, 1.0 - m):
        num = guided_filter(guide, x * w, radius, eps)
        den = guided_filter(guide, w, radius, eps)
        out += w * np.where(den > 0.05, num / np.maximum(den, 0.05), x)
    return out


def soft_clamp_log(x, lo, hi):
    return hi * np.tanh(np.maximum(x, 0) / hi) + lo * np.tanh(np.minimum(x, 0) / lo)


def kelvin_rgb_rel(K: float) -> np.ndarray:
    """Linear-RGB multiplier of a blackbody relative to 6500K, luminance-normalized."""
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


def polar(az_deg: float, el_deg: float) -> np.ndarray:
    """Unit vector surface->light. x right, y down, z toward viewer."""
    a, e = math.radians(az_deg), math.radians(el_deg)
    return np.array([math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)], np.float32)


# --------------------------------------------------------------------- I/O
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


# ------------------------------------------------------------------ lights
KINDS = ("directional", "point", "spot", "area", "ring", "hemisphere", "rim")


@dataclass
class Light:
    kind: str = "directional"
    azimuth: Optional[float] = None          # polar placement (see module docstring)
    elevation: Optional[float] = None
    pos: Optional[Tuple[float, float, float]] = None   # explicit xyz (directional: direction TO the light)
    distance: float = 1.5                    # polar placement distance for positional lights
    intensity: float = 1.0
    kelvin: float = 6500.0
    size: Tuple[float, float] = (0.8, 0.6)   # area: (width, height); ring: (radius, unused)
    samples: int = 3                         # area: samples per side; ring: 4*samples points
    softness: float = 0.3                    # shadow softness 0..1
    k1: float = 0.0                          # linear falloff
    k2: float = 0.35                         # quadratic falloff
    cone_outer_deg: float = 40.0             # spot
    cone_inner_deg: Optional[float] = None
    aim: Tuple[float, float] = (0.0, 0.0)    # spot aim point (scene xy)
    pool: float = 0.0                        # 0..1 light pool on the backdrop
    pool_radius: float = 0.9
    shadow: float = 0.8                      # contact-shadow strength
    specular: float = 1.0                    # per-light specular multiplier
    ground_intensity: float = 0.3            # hemisphere: ground bounce
    ground_kelvin: float = 4000.0
    rim_power: float = 2.5                   # rim: edge sharpness

    # ---- geometry helpers
    def _az_el(self):
        az = 270.0 if self.azimuth is None else self.azimuth
        el = (20.0 if self.kind == "rim" else 30.0) if self.elevation is None else self.elevation
        return az, el

    def direction(self) -> np.ndarray:
        if self.pos is not None and self.kind in ("directional", "rim"):
            v = np.array(self.pos, np.float32)
            return v / np.linalg.norm(v)
        return polar(*self._az_el())

    def position(self) -> np.ndarray:
        if self.pos is not None and self.kind not in ("directional", "rim", "hemisphere"):
            return np.array(self.pos, np.float32)
        return polar(*self._az_el()) * self.distance

    def emitter_frame(self):
        c = self.position()
        n = -c / (np.linalg.norm(c) + 1e-6)                   # emitter faces the scene centre
        up = np.array([0, -1, 0], np.float32) if abs(n[1]) < 0.95 else np.array([1, 0, 0], np.float32)
        u = np.cross(up, n)
        u /= np.linalg.norm(u) + 1e-9
        v = np.cross(n, u)
        return c, n, u, v

    def emit_points(self) -> List[Tuple[np.ndarray, float]]:
        c, n, u, v = self.emitter_frame()
        if self.kind in ("point", "spot"):
            return [(c, 1.0)]
        if self.kind == "area":
            k = max(1, self.samples)
            out = []
            for i in range(k):
                for j in range(k):
                    oi = ((i + 0.5) / k - 0.5) * self.size[0]
                    oj = ((j + 0.5) / k - 0.5) * self.size[1]
                    out.append((c + oi * u + oj * v, 1.0 / (k * k)))
            return out
        if self.kind == "ring":
            n_pts = max(6, 4 * self.samples)
            return [(c + self.size[0] * (math.cos(t) * u + math.sin(t) * v), 1.0 / n_pts)
                    for t in np.linspace(0, 2 * math.pi, n_pts, endpoint=False)]
        raise ValueError(self.kind)

    def front_weight(self) -> float:
        """How much this light acts on the camera-facing side (0 = pure back light)."""
        if self.kind == "hemisphere":
            return self.intensity
        z = self.direction()[2] if self.kind in ("directional", "rim") else self.position()[2] / (np.linalg.norm(self.position()) + 1e-6)
        return float(self.intensity * np.clip(z * 2.0, 0, 1))


def L(kind="directional", az=None, el=None, **kw) -> Light:
    return Light(kind=kind, azimuth=az, elevation=el, **kw)


@dataclass
class Params:
    lam: float = 0.7                  # detail coupling: 0 locked .. 1 physical
    strength: float = 1.0
    r_min: float = 0.25
    r_max: float = 3.0
    ambient_new: float = 0.30
    ambient_old: float = 0.65
    wrap: float = 0.25
    ratio_eps: float = 0.05
    keep_exposure: bool = True
    tint_strength: float = 1.0
    depth_scale: float = 0.25
    lum_height: float = 0.35
    invert_lum: bool = False
    edge_bend: float = 0.85           # bends silhouette normals outward so back/rim lights work
    edge_bend_width: float = 0.035
    deband: float = 1.0
    base_radius_frac: float = 0.008
    base_eps: float = 2e-3
    ratio_radius_frac: float = 0.015
    ratio_eps_guided: float = 1e-2
    shadow_steps: int = 24
    shadow_dist_frac: float = 0.14
    shadow_target_px: int = 512       # shadows are marched at this resolution then upsampled
    gloss: float = 0.25               # 0 matte (paper, ink, cloth) .. 1 mirror-like
    roughness: float = 0.4
    spec_gain: float = 2.5
    dither: bool = True


MATERIALS = {
    "matte": dict(gloss=0.0, roughness=0.8),
    "satin": dict(gloss=0.25, roughness=0.45),
    "glossy": dict(gloss=0.65, roughness=0.25),
    "mirror": dict(gloss=1.0, roughness=0.12),
}

FLAT_OLD = [Light("directional", pos=(0.0, -0.3, 1.0), intensity=0.35, shadow=0.0)]

PRESETS: Dict[str, List[Light]] = {
    # --- single-source looks, one per direction family
    "left_key": [L("directional", 270, 30, intensity=1.1, kelvin=5600, pool=0.4)],
    "right_key": [L("directional", 90, 30, intensity=1.1, kelvin=5600, pool=0.4)],
    "top_light": [L("directional", 0, 55, intensity=1.1, kelvin=5600, pool=0.4)],
    "under_light": [L("directional", 180, 35, intensity=1.1, kelvin=4500, pool=0.3)],
    "split_light": [L("directional", 270, 4, intensity=1.3, kelvin=5600, shadow=0.9)],
    "backlight": [L("rim", 0, -35, intensity=1.5, kelvin=6500), L("hemisphere", intensity=0.18, ground_intensity=0.1)],
    # --- light types from the same side
    "softbox_left": [L("area", 290, 35, distance=1.3, size=(0.9, 0.7), intensity=1.2, kelvin=5600, pool=0.3)],
    "spot_drama": [L("spot", 300, 40, distance=1.3, intensity=1.9, kelvin=3800, cone_outer_deg=30, softness=0.25, pool=0.5)],
    "point_bulb": [L("point", 300, 35, distance=1.0, intensity=1.4, kelvin=3000, k2=0.8, pool=0.6)],
    "ring_light": [L("ring", 90, 90, distance=1.2, size=(0.45, 0.45), intensity=1.0, kelvin=5600, shadow=0.2)],
    "window_right": [L("area", 90, 25, distance=1.3, size=(0.5, 1.3), intensity=1.2, kelvin=6800, pool=0.5),
                     L("hemisphere", intensity=0.25, kelvin=7500, ground_intensity=0.12)],
    # --- classic studio rigs
    "warm_key_cool_rim": [L("area", 290, 35, distance=1.3, size=(0.8, 0.7), intensity=1.0, kelvin=3600, pool=0.5),
                          L("rim", 100, -25, intensity=0.9, kelvin=8000)],
    "three_point": [L("area", 300, 40, distance=1.3, size=(0.8, 0.7), intensity=1.0, kelvin=5200, pool=0.3),
                    L("directional", 60, 30, intensity=0.4, kelvin=6500, shadow=0.0),
                    L("rim", 0, -30, intensity=0.8, kelvin=8500)],
    "rembrandt": [L("area", 315, 38, distance=1.3, size=(0.7, 0.7), intensity=1.2, kelvin=4800),
                  L("hemisphere", intensity=0.18, ground_intensity=0.08)],
    "butterfly_beauty": [L("area", 0, 55, distance=1.3, size=(0.9, 0.5), intensity=1.1, kelvin=5600),
                         L("directional", 180, 40, intensity=0.35, kelvin=5600, shadow=0.0)],
    "golden_hour_back": [L("rim", 60, -15, intensity=1.5, kelvin=2800),
                         L("directional", 270, 20, intensity=0.5, kelvin=6500, shadow=0.3),
                         L("hemisphere", intensity=0.2, kelvin=7000, ground_intensity=0.12, ground_kelvin=3000)],
    "product_white_sweep": [L("area", 0, 65, distance=1.2, size=(1.4, 0.8), intensity=1.0, kelvin=5600, shadow=0.4),
                            L("hemisphere", intensity=0.35, ground_intensity=0.3, kelvin=5600, ground_kelvin=5600)],
    "right_heel_point": [L("point", 80, 20, distance=0.9, intensity=1.4, kelvin=4500, k2=0.8, pool=0.6)],
    "floor_uplight": [L("directional", 180, 20, intensity=1.0, kelvin=4000, pool=0.3)],
}


# ------------------------------------------------------------ geometry/scene
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
            for idx in np.argsort(-counts)[:4]:
                c_ = keys[idx] * 4.0
                d = cv2.GaussianBlur(np.linalg.norm(lab - c_, axis=2), (0, 0), 1.0)
                kk = max(3, int(0.012 * min(H, W)) | 1)
                se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kk, kk))
                m2 = cv2.morphologyEx((d > 6.0).astype(np.uint8), cv2.MORPH_CLOSE, se)
                m2 = _fill_largest(cv2.morphologyEx(m2, cv2.MORPH_OPEN, se))
                if 0.03 <= float(m2.mean()) <= 0.97:
                    m = m2
                    break
    cov = float(m.mean())
    if cov < 0.03 or cov > 0.97:
        m = np.zeros((H, W), np.uint8)
        cv2.ellipse(m, (W // 2, H // 2), (int(W * 0.42), int(H * 0.42)), 0, 0, 360, 1, -1)
    return cv2.GaussianBlur(m.astype(np.float32), (0, 0), max(1.0, 0.004 * max(H, W)))


def build_height(mask, base_gamma, p: Params, depth: Optional[np.ndarray] = None) -> np.ndarray:
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


def normals_from_height(h, mask, p: Params, gain: float = 1.0) -> np.ndarray:
    H, W = h.shape
    hx = cv2.Sobel(h, cv2.CV_32F, 1, 0, ksize=3) / 8.0
    hy = cv2.Sobel(h, cv2.CV_32F, 0, 1, ksize=3) / 8.0
    N = np.dstack([-hx * gain, -hy * gain, np.ones_like(h)])
    N /= np.linalg.norm(N, axis=2, keepdims=True)
    if p.edge_bend > 0:
        m8 = (mask > 0.5).astype(np.uint8)
        dist = cv2.distanceTransform(m8, cv2.DIST_L2, 5)
        ds = cv2.GaussianBlur(dist, (0, 0), 0.004 * max(H, W))
        gx = cv2.Sobel(ds, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(ds, cv2.CV_32F, 0, 1, ksize=3)
        gn = np.sqrt(gx * gx + gy * gy) + 1e-6
        out_xy = np.dstack([-gx / gn, -gy / gn])                     # outward from the subject
        e = (np.exp(-dist / (p.edge_bend_width * min(H, W))) * p.edge_bend * (m8 > 0)).astype(np.float32)
        nxy = N[..., :2] * (1 - e[..., None]) + out_xy * e[..., None]
        nz = N[..., 2] * (1 - e)
        N = np.dstack([nxy, nz])
        N /= np.linalg.norm(N, axis=2, keepdims=True) + 1e-6
        N = cv2.GaussianBlur(N.astype(np.float32), (0, 0), 0.0025 * max(H, W))
        N /= np.linalg.norm(N, axis=2, keepdims=True) + 1e-6
    return N.astype(np.float32)


def tone_map(rgb, knee=0.8, top=1.15):
    m = rgb.max(axis=2, keepdims=True)
    comp = knee + (top - knee) * np.tanh((m - knee) / (top - knee))
    f = np.where(m > knee, comp / np.maximum(m, 1e-6), 1.0)
    return np.clip(rgb * f, 0, 1)


def decompose(lin, p: Params):
    Y = np.maximum(luminance(lin), 1e-4)
    logY = np.log(Y)
    guide = linear_to_srgb(Y)
    r = max(4, int(round(p.base_radius_frac * max(Y.shape))))
    B = guided_filter(guide, logY, r, p.base_eps)
    D = logY - B
    t = p.deband * (2.4 / 255.0) / np.maximum(guide, 0.05)
    D = D * smoothstep(t, 2 * t, np.abs(D))
    Yb = np.exp(B)
    Yd = np.exp(B + D) - Yb
    return Y, Yb, Yd


@dataclass
class Scene:
    """Everything that does NOT depend on the lights. Build once, relight many times (interactive use)."""
    srgb: np.ndarray
    lin: np.ndarray
    Y: np.ndarray
    Yb: np.ndarray
    Yd: np.ndarray
    base_gamma: np.ndarray
    mask: np.ndarray
    h: np.ndarray
    N: np.ndarray
    P: np.ndarray
    S: float
    c: Tuple[float, float]
    xs: np.ndarray
    ys: np.ndarray
    long: int


def prepare_scene(srgb, p: Optional[Params] = None, depth=None, mask=None) -> Scene:
    p = p or Params()
    H, W, _ = srgb.shape
    lin = srgb_to_linear(srgb)
    Y, Yb, Yd = decompose(lin, p)
    base_gamma = linear_to_srgb(Yb)
    if mask is None:
        mask = auto_mask(srgb)
    h = build_height(mask, base_gamma, p, depth)
    N = normals_from_height(h, mask, p)
    S = min(H, W) / 2.0
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    xs, ys = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    P = np.dstack([(xs - cx) / S, (ys - cy) / S, h / S]).astype(np.float32)
    return Scene(srgb, lin, Y, Yb, Yd, base_gamma, mask.astype(np.float32), h, N, P, S, (cx, cy), xs, ys, max(H, W))


# --------------------------------------------------------------- shading
def contact_shadow(h, l, steps, dist_frac, softness_px, target_px):
    """Screen-space ray march toward the light. Returns occlusion 0..1 (full resolution)."""
    H, W = h.shape
    ds = max(1.0, max(H, W) / float(target_px))
    if ds > 1.0:
        w2, h2 = int(round(W / ds)), int(round(H / ds))
        hs_ = cv2.resize(h, (w2, h2), interpolation=cv2.INTER_AREA) / ds
        ls = cv2.resize(l.astype(np.float32), (w2, h2), interpolation=cv2.INTER_AREA)
        softness_px = softness_px / ds
    else:
        hs_, ls = h, l
        h2, w2 = H, W
    lxy = ls[..., :2]
    nxy = np.linalg.norm(lxy, axis=2) + 1e-6
    dirx, diry = lxy[..., 0] / nxy, lxy[..., 1] / nxy
    slope = np.maximum(ls[..., 2], 0.05) / nxy
    xs, ys = np.meshgrid(np.arange(w2, dtype=np.float32), np.arange(h2, dtype=np.float32))
    maxd = dist_frac * max(h2, w2)
    occ = np.zeros((h2, w2), np.float32)
    for i in range(1, steps + 1):
        d = maxd * (i / steps) ** 1.5
        hs = cv2.remap(hs_, (xs + dirx * d).astype(np.float32), (ys + diry * d).astype(np.float32),
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        pen = (hs - (hs_ + slope * d)) / max(softness_px, 1e-3)
        occ = np.maximum(occ, smoothstep(0.0, 1.0, pen))
    occ *= smoothstep(0.0, 0.18, ls[..., 2])          # lights from behind cast no shadow toward the lens
    if ds > 1.0:
        occ = cv2.resize(occ, (W, H), interpolation=cv2.INTER_LINEAR)
    return occ


def ggx_spec(N, l, rough):
    """Cook-Torrance GGX with Schlick Fresnel, view = +z. Returns D*G*F/(4 N.V) (already includes N.L)."""
    Hh = l.copy()
    Hh[..., 2] += 1.0
    Hh /= np.linalg.norm(Hh, axis=2, keepdims=True) + 1e-6
    NdH = np.clip((N * Hh).sum(axis=2), 0, 1)
    NdL = np.clip((N * l).sum(axis=2), 0, 1)
    NdV = np.clip(N[..., 2], 1e-2, 1)
    a2 = (rough ** 2) ** 2
    D = a2 / (math.pi * (NdH ** 2 * (a2 - 1) + 1) ** 2 + 1e-6)
    k = (rough + 1) ** 2 / 8.0
    G = (NdL / (NdL * (1 - k) + k + 1e-6)) * (NdV / (NdV * (1 - k) + k + 1e-6))
    F = 0.04 + 0.96 * (1 - np.clip(Hh[..., 2], 0, 1)) ** 5
    return (D * G * F / (4 * NdV + 1e-4)).astype(np.float32)


def _vectors(Lt: Light, pt: np.ndarray, sc: Scene, directional: bool):
    P, m = sc.P, sc.mask
    H, W, _ = P.shape
    if directional:
        l = np.broadcast_to(pt.astype(np.float32), (H, W, 3)).copy()
        att = np.ones((H, W), np.float32)
    else:
        v = pt[None, None, :] - P
        r = np.linalg.norm(v, axis=2) + 1e-4
        l = (v / r[..., None]).astype(np.float32)
        d0 = float(np.linalg.norm(Lt.position()))
        att = ((1 + Lt.k1 * d0 + Lt.k2 * d0 * d0) / (1 + Lt.k1 * r + Lt.k2 * r * r)).astype(np.float32)
        if Lt.kind in ("area", "ring"):
            _, n_L, _, _ = Lt.emitter_frame()
            att = att * np.clip(-(l * n_L).sum(axis=2), 0, 1)
        if Lt.kind == "spot":
            tgt = np.array([Lt.aim[0], Lt.aim[1], 0.0], np.float32)
            sd = tgt - Lt.position()
            sd /= np.linalg.norm(sd) + 1e-9
            cosang = -(l * sd).sum(axis=2)
            outer = math.radians(Lt.cone_outer_deg)
            inner = math.radians(Lt.cone_inner_deg if Lt.cone_inner_deg is not None else Lt.cone_outer_deg * 0.6)
            att = att * smoothstep(math.cos(outer), math.cos(inner), cosang)
    # a light behind the subject still washes the backdrop (art-directable glow behind the product)
    l[..., 2] = m * l[..., 2] + (1 - m) * np.abs(l[..., 2])
    return l, att


def shade(sc: Scene, lights: Sequence[Light], ambient: float, p: Params, shadows=True, spec_on=False):
    H, W = sc.h.shape
    N, m = sc.N, sc.mask
    total = np.full((H, W), ambient, np.float32)
    comps: List[Tuple[np.ndarray, float]] = []
    spec = np.zeros((H, W, 3), np.float32)
    for Lt in lights:
        if Lt.kind == "hemisphere":
            ty = np.clip((sc.ys - sc.c[1]) / sc.S * 0.6, -1, 1)
            up = m * (-N[..., 1]) + (1 - m) * (-ty)
            sky = (Lt.intensity * (0.5 + 0.5 * up)).astype(np.float32)
            gnd = (Lt.ground_intensity * (0.5 - 0.5 * up)).astype(np.float32)
            comps += [(sky, Lt.kelvin), (gnd, Lt.ground_kelvin)]
            total += sky + gnd
            continue
        if Lt.kind == "rim":
            d = Lt.direction()
            dxy = d[:2] / (np.linalg.norm(d[:2]) + 1e-6)
            nxy = N[..., :2] / (np.linalg.norm(N[..., :2], axis=2, keepdims=True) + 1e-6)
            side = smoothstep(-0.1, 0.7, (nxy * dxy).sum(axis=2))
            fres = (1.0 - np.clip(N[..., 2], 0, 1)) ** Lt.rim_power
            g = (Lt.intensity * fres * side * 1.6 * (m > 0.02)).astype(np.float32)
            # backdrop glow behind the subject on the light's side
            glow = np.exp(-((sc.xs - (sc.c[0] + dxy[0] * sc.S * 1.4)) ** 2 + (sc.ys - (sc.c[1] + dxy[1] * sc.S * 1.4)) ** 2)
                          / (2 * (0.9 * sc.S) ** 2))
            g = g + (Lt.intensity * 0.35 * glow * (1 - m)).astype(np.float32)
            comps.append((g, Lt.kelvin))
            total += g
            continue

        directional = Lt.kind == "directional"
        pts = [(Lt.direction(), 1.0)] if directional else Lt.emit_points()
        g_acc = np.zeros((H, W), np.float32)
        s_acc = np.zeros((H, W), np.float32)
        for pt, w in pts:
            l, att = _vectors(Lt, pt, sc, directional)
            ndl = (N * l).sum(axis=2)
            diff = np.clip((ndl + p.wrap) / (1.0 + p.wrap), 0, 1) ** 1.1
            vis = np.ones((H, W), np.float32)
            if shadows and Lt.shadow > 0:
                occ = contact_shadow(sc.h, l, p.shadow_steps, p.shadow_dist_frac, 0.03 * sc.S, p.shadow_target_px)
                vis = 1.0 - Lt.shadow * occ
            g_acc += w * att * diff * vis
            if spec_on and Lt.specular > 0 and p.gloss > 0:
                s_acc += w * att * vis * ggx_spec(N, l, p.roughness)
        sigma = (0.003 + 0.02 * Lt.softness) * sc.long
        if shadows and Lt.shadow > 0:
            g_acc = cv2.GaussianBlur(g_acc, (0, 0), sigma * 0.5)       # penumbra softening
        pool = np.ones((H, W), np.float32)
        if Lt.pool > 0:
            if directional:
                d = Lt.direction()
                px, py = sc.c[0] + d[0] * sc.S * 1.6, sc.c[1] + d[1] * sc.S * 1.6
            else:
                cpos = Lt.position()
                px, py = sc.c[0] + cpos[0] * sc.S, sc.c[1] + cpos[1] * sc.S
            gg = np.exp(-((sc.xs - px) ** 2 + (sc.ys - py) ** 2) / (2 * (Lt.pool_radius * sc.S) ** 2))
            pool = ((1 - Lt.pool) + Lt.pool * gg).astype(np.float32)
        g = (Lt.intensity * g_acc * pool).astype(np.float32)
        comps.append((g, Lt.kelvin))
        total += g
        if spec_on and s_acc.any():
            spec += (Lt.intensity * Lt.specular * s_acc)[..., None] * kelvin_rgb_rel(Lt.kelvin)[None, None, :]
    return total, comps, spec


# -------------------------------------------------------------- relighting
@dataclass
class Result:
    relit_lin: np.ndarray
    relit_srgb: np.ndarray
    ratio: np.ndarray
    logR: np.ndarray
    mask: np.ndarray
    height: np.ndarray
    lam: float
    strength: float
    spec: Optional[np.ndarray] = None


def relight_scene(sc: Scene, lights: Sequence[Light], old_lights: Optional[Sequence[Light]] = None,
                  p: Optional[Params] = None, rng: Optional[np.random.Generator] = None,
                  gloss_map: Optional[np.ndarray] = None) -> Result:
    p = p or Params()
    old_lights = FLAT_OLD if old_lights is None else old_lights
    rng = rng or np.random.default_rng(0)
    H, W = sc.h.shape

    S_old, _, _ = shade(sc, old_lights, p.ambient_old, p, shadows=False, spec_on=False)
    S_new, comps, spec = shade(sc, lights, p.ambient_new, p, shadows=True, spec_on=p.gloss > 0)

    inside = sc.mask > 0.5
    if p.keep_exposure and inside.any():
        front = sum(Lt.front_weight() for Lt in lights)
        wgt = float(np.clip(front / 0.8, 0, 1))              # pure back-lit looks stay dark in front
        k = float(np.clip(np.median(S_old[inside]) / max(np.median(S_new[inside]), 1e-4), 0.4, 2.5)) ** wgt
        S_new = S_new * k
        comps = [(g * k, K) for g, K in comps]
        spec = spec * k

    logR = np.log((S_new + p.ratio_eps) / (S_old + p.ratio_eps))
    logR = soft_clamp_log(logR, math.log(p.r_min), math.log(p.r_max))
    r_r = max(8, int(round(p.ratio_radius_frac * sc.long)))
    logR = masked_guided(sc.base_gamma, logR, sc.mask, r_r, p.ratio_eps_guided) * p.strength
    R = np.exp(logR).astype(np.float32)

    Y2 = np.maximum(sc.Yb * R + sc.Yd * np.power(R, p.lam), 0.0)
    scale = (Y2 / sc.Y)[..., None]

    tot = np.maximum(S_new, 1e-4)
    tint = np.ones((H, W, 3), np.float32)
    for g, K in comps:
        frac = np.clip(g / tot, 0, 1)[..., None]
        tint += p.tint_strength * p.strength * frac * (kelvin_rgb_rel(K)[None, None, :] - 1.0)
    tint = cv2.GaussianBlur(tint, (0, 0), 0.004 * sc.long)
    tint = np.clip(tint, 0.2, 5.0)
    tint = tint / (tint @ LUMA)[..., None]

    base_rgb = sc.lin * scale * tint
    spec_lin = np.zeros_like(base_rgb)
    if p.gloss > 0 and spec.any():
        gm = sc.mask if gloss_map is None else gloss_map
        amount = p.spec_gain * p.gloss * p.strength * gm[..., None] * spec
        spec_lin = (1.0 - np.exp(-amount)).astype(np.float32)
    out_lin = tone_map(base_rgb + spec_lin)
    out = linear_to_srgb(out_lin)
    if p.dither:
        out = out + ((rng.random(out.shape) - rng.random(out.shape)) / 255.0).astype(np.float32)
    out = np.clip(out, 0, 1).astype(np.float32)
    return Result(out_lin, out, R, logR, sc.mask, sc.h, p.lam, p.strength, spec_lin)


def relight(srgb, lights, old_lights=None, p: Optional[Params] = None, depth=None, mask=None, rng=None) -> Result:
    p = p or Params()
    return relight_scene(prepare_scene(srgb, p, depth, mask), lights, old_lights, p, rng)


# ------------------------------------------------ hybrid (Smart mode core)
def ratio_transfer(orig_srgb, gen_srgb, p: Optional[Params] = None, sigma_frac: float = 0.02,
                   mask: Optional[np.ndarray] = None) -> Result:
    """Lighting from a generated/neural relit image (low frequencies only) applied to the ORIGINAL photo."""
    p = p or Params()
    H, W, _ = orig_srgb.shape
    gen = cv2.resize(gen_srgb, (W, H), interpolation=cv2.INTER_AREA) if gen_srgb.shape[:2] != (H, W) else gen_srgb
    lin = srgb_to_linear(orig_srgb)
    lg = srgb_to_linear(gen)
    Y, Yb, Yd = decompose(lin, p)
    sig = sigma_frac * max(H, W)
    lo = cv2.GaussianBlur(lin, (0, 0), sig)
    lgl = cv2.GaussianBlur(lg, (0, 0), sig)
    Rc = (lgl + 0.02) / (lo + 0.02)
    Rl = Rc @ LUMA
    m = mask if mask is not None else auto_mask(orig_srgb)
    logR = soft_clamp_log(np.log(Rl), math.log(p.r_min), math.log(p.r_max))
    base_gamma = linear_to_srgb(Yb)
    r_r = max(8, int(round(p.ratio_radius_frac * max(H, W))))
    logR = masked_guided(base_gamma, logR, m, r_r, p.ratio_eps_guided) * p.strength
    R = np.exp(logR).astype(np.float32)
    tint = np.clip(Rc / np.maximum(Rl, 1e-4)[..., None], 0.5, 2.0)
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
    b0, _ = banding_score(orig_srgb)
    b1, frac1 = banding_score(res.relit_srgb)
    lab_o = cv2.cvtColor(orig_srgb.astype(np.float32), cv2.COLOR_RGB2Lab)
    lab_r = cv2.cvtColor(res.relit_srgb.astype(np.float32), cv2.COLOR_RGB2Lab)
    inside = res.mask > 0.5
    dc = np.linalg.norm(lab_r[..., 1:] - lab_o[..., 1:], axis=2)
    out = res.relit_srgb
    return {
        "detail_ratio_median": detail_ratio,
        "detail_lock_error_log": detail_err,
        "banding_orig": b0, "banding_relit": b1, "banding_gain": b1 - b0,
        "smooth_area_frac": frac1,
        "chroma_shift_p95_in_subject": float(np.percentile(dc[inside], 95)) if inside.any() else 0.0,
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
                      levels=(1.0, 0.75, 0.5, 0.25), scene: Optional[Scene] = None):
    """Relight; if a quality check fails, reduce strength and retry. The Scene is built once."""
    p = p or Params()
    sc = scene or prepare_scene(srgb, p, depth, mask)
    log, last = [], None
    for s in levels:
        q = Params(**{**asdict(p), "strength": p.strength * s})
        res = relight_scene(sc, lights, old_lights, q)
        m = compute_metrics(srgb, res, q)
        ok, fails = quality_gate(m)
        log.append({"strength": q.strength, "ok": ok, "fails": fails})
        last = (res, m)
        if ok:
            break
    return last[0], last[1], log


# --------------------------------------------------------- visual outputs
def lock_error_map(orig_srgb, res: Result, amp=8.0):
    H, W, _ = orig_srgb.shape
    sig = 0.004 * max(H, W)
    Yo = np.log(np.maximum(luminance(srgb_to_linear(orig_srgb)), 1e-4))
    Yr = np.log(np.maximum(luminance(srgb_to_linear(res.relit_srgb)), 1e-4))
    err = np.abs(_hp(Yr, sig) - _hp(Yo, sig) * np.exp((res.lam - 1.0) * res.logR))
    cm = cv2.applyColorMap((np.clip(err * amp, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    return cv2.cvtColor(cm, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0


def ratio_map(res: Result):
    v = np.clip(res.logR / math.log(2) * 0.5 + 0.5, 0, 1)
    cm = cv2.applyColorMap((v * 255).astype(np.uint8), cv2.COLORMAP_TWILIGHT_SHIFTED)
    return cv2.cvtColor(cm, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0


def _fonts():
    from PIL import ImageFont
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for fp in font_paths:
        try:
            return (ImageFont.truetype(fp, 15), ImageFont.truetype(fp, 11))
        except Exception:
            continue
    d = ImageFont.load_default()
    return d, d


def make_board(orig, res: Result, m: Dict[str, float], title: str, path: str):
    from PIL import Image, ImageDraw
    H, W, _ = orig.shape
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
    panels = [(marker, "1. ORIGINAL", "red box = crop region"),
              (ratio_map(res), "2. SHADING RATIO R", "blue = darker, red = brighter (log scale)"),
              (res.relit_srgb, "3. RELIT", f"lam={res.lam:.2f} strength={res.strength:.2f}"),
              (lock_error_map(orig, res), "4. DETAIL-LOCK ERROR", "black = detail exactly as expected"),
              (canvas, "5. ALIGNED 300% CROP", "left original | right relit, same coords")]
    metr = (f"detail ratio {m['detail_ratio_median']:.2f} | lock err {m['detail_lock_error_log']:.3f} | "
            f"banding {m['banding_orig']:.2f}->{m['banding_relit']:.2f}")
    f1, f2 = _fonts()
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


def _sheet(cells: List[Tuple[str, np.ndarray]], cols: int, path: str, title: str, thumb_w: int = 288):
    from PIL import Image, ImageDraw
    f1, f2 = _fonts()
    H, W = cells[0][1].shape[:2]
    th = int(round(thumb_w * H / W))
    rows = math.ceil(len(cells) / cols)
    head = 34
    img = Image.new("RGB", (cols * thumb_w, rows * (th + 22) + head), (24, 24, 26))
    d = ImageDraw.Draw(img)
    d.text((10, 9), title, fill=(255, 255, 255), font=f1)
    for i, (lab, im) in enumerate(cells):
        r, c = divmod(i, cols)
        t = cv2.resize(np.clip(im, 0, 1), (thumb_w, th), interpolation=cv2.INTER_AREA)
        x, y = c * thumb_w, head + r * (th + 22)
        img.paste(Image.fromarray((t * 255).astype(np.uint8)), (x, y + 22))
        d.text((x + 6, y + 4), lab, fill=(210, 210, 215), font=f2)
    img.save(path)


def sweep_wheel(sc: Scene, p: Params, path: str, kind: str = "directional", elevation: float = 30.0,
                intensity: float = 1.2, kelvin: float = 5600, extra: Optional[dict] = None):
    """3x3 compass: original in the centre, the light placed at 8 azimuths around it."""
    extra = extra or {}
    grid = {0: (0, 1), 45: (0, 2), 90: (1, 2), 135: (2, 2), 180: (2, 1), 225: (2, 0), 270: (1, 0), 315: (0, 0)}
    cells = [None] * 9
    cells[4] = ("ORIGINAL", sc.srgb)
    for az, (r, c) in grid.items():
        lt = Light(kind, azimuth=az, elevation=elevation, intensity=intensity, kelvin=kelvin, **extra)
        res = relight_scene(sc, [lt], None, p)
        cells[r * 3 + c] = (f"{kind} from {az}° (el {elevation:.0f}°)", res.relit_srgb)
    _sheet(cells, 3, path, f"LIGHT WHEEL  |  azimuth 0=top, 90=right, 180=below, 270=left  |  elevation {elevation:.0f}°")


def sweep_elevation(sc: Scene, p: Params, path: str, azimuth: float = 270.0):
    """Same side, light moved from frontal through grazing to behind the subject."""
    els = [90, 60, 30, 0, -20, -40, -60, -80]
    cells = [("ORIGINAL", sc.srgb)]
    for el in els:
        kind = "directional" if el >= 0 else "rim"
        lt = Light(kind, azimuth=azimuth, elevation=el, intensity=1.3 if el >= 0 else 1.6, kelvin=5600)
        cells.append((f"{kind} el {el}°", relight_scene(sc, [lt], None, p).relit_srgb))
    _sheet(cells, 3, path, f"ELEVATION SWEEP from azimuth {azimuth:.0f}°  |  +90 frontal  ->  0 grazing  ->  negative = behind")


def sweep_types(sc: Scene, p: Params, path: str, azimuth: float = 300.0, elevation: float = 35.0):
    rigs = [
        ("directional (sun)", [L("directional", azimuth, elevation, intensity=1.2, kelvin=5600)]),
        ("point (bulb, 3000K)", [L("point", azimuth, elevation, distance=1.0, intensity=1.4, kelvin=3000, k2=0.8, pool=0.6)]),
        ("spot (30° cone)", [L("spot", azimuth, elevation, distance=1.3, intensity=1.9, kelvin=3800, cone_outer_deg=30, pool=0.5)]),
        ("area softbox", [L("area", azimuth, elevation, distance=1.3, size=(0.9, 0.7), intensity=1.2, kelvin=5600)]),
        ("ring light", [L("ring", 90, 90, distance=1.2, size=(0.45, 0.45), intensity=1.0, kelvin=5600, shadow=0.2)]),
        ("hemisphere (sky/ground)", [L("hemisphere", intensity=0.9, kelvin=7500, ground_intensity=0.3, ground_kelvin=3500)]),
        ("rim / backlight", [L("rim", (azimuth + 180) % 360, -30, intensity=1.6, kelvin=8000)]),
        ("warm key + cool rim", PRESETS["warm_key_cool_rim"]),
    ]
    cells = [("ORIGINAL", sc.srgb)] + [(n, relight_scene(sc, ls, None, p).relit_srgb) for n, ls in rigs]
    _sheet(cells, 3, path, f"LIGHT TYPES from azimuth {azimuth:.0f}°, elevation {elevation:.0f}°")


# --------------------------------------------------------------------- CLI
_KEYMAP = {"az": "azimuth", "el": "elevation", "dist": "distance", "int": "intensity", "k": "kelvin",
           "soft": "softness", "spec": "specular", "cone": "cone_outer_deg", "inner": "cone_inner_deg",
           "n": "samples", "gk": "ground_intensity", "gkelvin": "ground_kelvin", "rp": "rim_power",
           "pool": "pool", "shadow": "shadow", "k1": "k1", "k2": "k2", "poolr": "pool_radius"}


def parse_light(spec: str) -> Light:
    """e.g. 'spot:az=300,el=40,dist=1.3,int=1.8,k=3200,cone=30'  |  'area:az=270,el=30,size=0.9x0.6'
             'rim:az=90,el=-30'  |  'hemisphere:int=0.6,gk=0.2'  |  'directional:pos=-0.8/-0.2/0.5'"""
    kind, _, rest = spec.partition(":")
    kind = kind.strip()
    if kind not in KINDS:
        raise ValueError(f"unknown light kind '{kind}', choose from {KINDS}")
    kw = {}
    for item in filter(None, (s.strip() for s in rest.split(","))):
        k, _, v = item.partition("=")
        if k == "pos":
            kw["pos"] = tuple(float(x) for x in v.split("/"))
        elif k == "size":
            kw["size"] = tuple(float(x) for x in v.split("x"))
        elif k == "aim":
            kw["aim"] = tuple(float(x) for x in v.split("/"))
        elif k in _KEYMAP:
            f = _KEYMAP[k]
            kw[f] = int(v) if f == "samples" else float(v)
        else:
            raise ValueError(f"unknown light key '{k}'")
    return Light(kind=kind, **kw)


def lights_from_arg(arg: str) -> List[Light]:
    if arg in PRESETS:
        return PRESETS[arg]
    with open(arg) as f:
        out = []
        for d in json.load(f):
            for key in ("pos", "size", "aim"):
                if key in d:
                    d[key] = tuple(d[key])
            out.append(Light(**d))
        return out


def main():
    ap = argparse.ArgumentParser(description="Relight Studio engine v4 (lights from any side)")
    ap.add_argument("input"); ap.add_argument("output", nargs="?", default="relit.png")
    ap.add_argument("--preset", help=f"one of {sorted(PRESETS)} or a lights JSON path")
    ap.add_argument("--light", action="append", default=[], help="inline light, repeatable (see parse_light)")
    ap.add_argument("--material", choices=sorted(MATERIALS), default="satin")
    ap.add_argument("--lam", type=float, default=0.7)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--depth"); ap.add_argument("--mask")
    ap.add_argument("--no-gate", action="store_true")
    ap.add_argument("--bits", type=int, default=8, choices=[8, 16])
    ap.add_argument("--board"); ap.add_argument("--report")
    ap.add_argument("--sweep", choices=["wheel", "types", "elevation", "all"], help="write contact sheet(s)")
    ap.add_argument("--sweep-prefix", default="sweep")
    ap.add_argument("--list-presets", action="store_true")
    a = ap.parse_args()
    if a.list_presets:
        for k, v in PRESETS.items():
            print(f"{k:22s} " + " + ".join(f"{l.kind}" for l in v))
        return

    srgb = load_srgb(a.input)
    p = Params(lam=a.lam, strength=a.strength, **MATERIALS[a.material])
    depth = np.load(a.depth) if a.depth else None
    mask = (cv2.imread(a.mask, 0).astype(np.float32) / 255.0) if a.mask else None
    sc = prepare_scene(srgb, p, depth, mask)

    if a.sweep:
        if a.sweep in ("wheel", "all"):
            sweep_wheel(sc, p, f"{a.sweep_prefix}_wheel.png")
        if a.sweep in ("elevation", "all"):
            sweep_elevation(sc, p, f"{a.sweep_prefix}_elevation.png")
        if a.sweep in ("types", "all"):
            sweep_types(sc, p, f"{a.sweep_prefix}_types.png")
        if not (a.preset or a.light):
            return

    lights: List[Light] = []
    if a.preset:
        lights += lights_from_arg(a.preset)
    lights += [parse_light(s) for s in a.light]
    if not lights:
        lights = PRESETS["warm_key_cool_rim"]

    if a.no_gate:
        res = relight_scene(sc, lights, None, p)
        m = compute_metrics(srgb, res, p); log = []
    else:
        res, m, log = relight_with_gate(srgb, lights, None, p, scene=sc)
    save_srgb(a.output, res.relit_srgb, a.bits)
    if a.board:
        make_board(srgb, res, m, a.preset or "custom", a.board)
    if a.report:
        with open(a.report, "w") as f:
            json.dump({"metrics": m, "gate_log": log}, f, indent=2)
    print(json.dumps({"metrics": m, "gate_log": log}, indent=2))


if __name__ == "__main__":
    main()

