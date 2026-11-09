# RELIGHT STUDIO — RS-SPIKE-3A
## Scene Data Model, State Management & Serialization Specification

**Document:** `docs/RS-SPIKE-3A/03_SCENE_MODEL.md`  
**Status:** Approved Engineering Baseline  
**Milestone:** RS-SPIKE-3A  
**Date:** November 2026  

---

### 1. Scene Data Model Principles

The scene data model is the single source of truth for all spatial, optical, and algorithmic configuration in Relight Studio. It must satisfy three strict engineering invariants:
1. **Physical Defensibility:** All geometric, camera, and lighting parameters map to physical units (meters, degrees, Kelvins, Watts/sr/m²).
2. **Defensive Validation:** Every numerical property is audited before assignment. NaNs, infinities, negative dimensions, and degenerate vectors are immediately rejected with descriptive errors.
3. **Lossless Roundtrip Serialization:** Complete serialization to and from human-readable JSON. The deserialized state must match the source state to floating-point machine precision.

---

### 2. Scene Schema Definition

The authoritative scene schema is implemented in `studio3a/scene.py`.

```json
{
  "version": "RS-SPIKE-3A-v1.0",
  "camera": {
    "position": [0.0, 0.4, 2.2],
    "target": [0.0, 0.25, 0.0],
    "up": [0.0, 1.0, 0.0],
    "fov_deg": 45.0,
    "near_clip": 0.05,
    "far_clip": 50.0
  },
  "subject_proxy": {
    "proxy_type": "BOX",
    "position": [0.0, 0.25, 0.0],
    "rotation_euler_deg": [0.0, 0.0, 0.0],
    "dimensions": [0.35, 0.45, 0.25],
    "superquadric_e1": 1.0,
    "superquadric_e2": 1.0
  },
  "receiver": {
    "receiver_type": "CYCLORAMA",
    "plane_height": 0.0,
    "cove_radius": 0.35,
    "cove_center_z": -0.85,
    "wall_normal_z": 1.0
  },
  "lights": [
    {
      "name": "Key Softbox",
      "position": [-0.9, 1.2, 0.8],
      "rotation_euler_deg": [35.0, 45.0, 0.0],
      "dimensions": [0.6, 0.6],
      "intensity": 2.5,
      "color_temperature_k": 5600.0,
      "color_tint_rgb": [1.0, 1.0, 1.0],
      "energy_convention": "FIXED_RADIANCE",
      "is_active": true
    }
  ],
  "render_settings": {
    "quality": "FINAL",
    "mc_samples_preview": 4,
    "mc_samples_final": 32,
    "enable_shadows": true,
    "enable_contact": true,
    "contact_distance_threshold": 0.12,
    "contact_falloff_exponent": 1.5,
    "enable_oklab_gamut_mapping": true,
    "enable_uncertainty": true,
    "output_width": 1024,
    "output_height": 768
  }
}
```

---

### 3. Numerical Bounds and Validation Rules

The `_validate_finite_float` and dataclass validation methods enforce the following boundaries:

| Entity | Parameter | Constraints | Rejection Behavior |
| :--- | :--- | :--- | :--- |
| **Float Values** | All coordinates / scalars | $\text{isfinite}(x) == \text{True}$ | Raises `ValueError` on NaN / $\pm\infty$ |
| **Camera** | `fov_deg` | $5.0^\circ \le \text{fov} \le 160.0^\circ$ | Clamped / Rejected if non-finite |
| **Camera** | Distance to Target | $\|P_{\text{cam}} - P_{\text{target}}\| > 10^{-4}$ | Raises `ValueError` for coincident points |
| **Proxy** | `dimensions` $(w, h, d)$ | $w, h, d \ge 10^{-4}\text{ m}$ | Raises `ValueError` for zero or negative extents |
| **Proxy** | Superquadric exponents | $e_1, e_2 \in [0.1, 4.0]$ | Clamped to stable numerical envelope |
| **Receiver** | `cove_radius` | $r \ge 10^{-4}\text{ m}$ | Raises `ValueError` if $\le 0$ |
| **Light** | `dimensions` $(w, h)$ | $w, h \ge 10^{-4}\text{ m}$ | Raises `ValueError` if zero or negative |
| **Light** | `intensity` | $I \ge 0.0$ | Raises `ValueError` if negative |
| **Light** | `color_temperature_k`| $1000\text{K} \le T \le 15000\text{K}$ | Values outside range rejected or clamped |
| **Render** | `mc_samples` | $S \ge 1$, integer | Raises `ValueError` if $< 1$ |

---

### 4. Undo/Redo State History Architecture

The `SceneStateManager` provides full transactional undo and redo capabilities for interactive editing sessions:

1. **Snapshot Isolation:**
   When an artist modifies any parameter in the inspector, `save_state(scene)` creates a deep clone of the scene dataclass and appends it to the undo stack.
2. **Circular Buffer Bounds:**
   The history buffer is bounded to a maximum depth (default: 50 states) to maintain a deterministic memory footprint. When capacity is exceeded, the oldest state is evicted.
3. **Branch Invalidation:**
   Executing a new edit action while positioned midway through the history stack clears all forward redo states.
4. **Deterministic Replay Guarantee:**
   Because each state snapshot contains complete, uncompressed configuration data, restoring a state via `undo()` or `redo()` is mathematically idempotent.
