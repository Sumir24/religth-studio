# RS-SPIKE-3C.1 — Engineering Report 01: Multi-Light Scene Architecture & Management

**Milestone:** RS-SPIKE-3C.1 (Multi-Light Architecture & Additive Illumination)  
**Author:** Principal Software Architect & 3D Systems Engineer  
**Branch:** `feature/RS-SPIKE-3C.1-multilight-architecture`  
**Module:** `studio3a/scene.py`  
**Status:** VALIDATED & CLOSED

---

## 1. Architectural Motivation & Requirements

In single-light rendering (RS-SPIKE-3A through RS-SPIKE-3C.0), scene state was restricted to a single active area light. While `StudioScene.lights` was defined as a list, downstream rendering paths and user manipulation treated it as a singleton (`scene.lights[0]`).

To enable a real virtual studio with standard commercial lighting configurations (3-point lighting: Key, Fill, Rim; plus kickers, background washes, and overhead softboxes), the scene state architecture must satisfy five mandatory invariants:
1. **Stable Identifiers:** Every light emitter possesses an immutable unique identifier (`id` / `light_id`) that persists across serialization, undo/redo, and session lifecycles.
2. **Per-Light Controls:** Each light independently exposes full geometric transforms (position, Euler rotation, dimensions), radiant intensity, blackbody correlated color temperature (CCT Kelvin), energy convention (`FIXED_RADIANCE` vs `FIXED_POWER`), emitter visibility toggle (`enabled`), and shadow generation toggle (`cast_shadows`).
3. **Deterministic Management API:** High-level manipulation primitives (`add_light`, `remove_light`, `duplicate_light`, `select_light`, `toggle_light`, `toggle_light_shadows`, `reorder_lights`) guarantee strict state invariants (minimum 1 light, maximum 8 lights, unique IDs, active light consistency).
4. **Backward-Compatible Schema Migration:** Legacy scene files authored in v3.0.0 or lacking multi-light attributes automatically deserialize cleanly, upgrade to schema v3.1.0, and provide safe fallback defaults.
5. **Exact Undo/Redo Invariance:** Every scene modification is an immutable state snapshot in `SceneStateManager`. Any sequence of additions, deletions, and edits reverts identically via `undo()` and reapplies cleanly via `redo()`.

---

## 2. Formal Schema Specification

### 2.1 `AreaLightData`
```python
@dataclass
class AreaLightData:
    id: str = "key_light_1"
    name: str = "Key Softbox"
    position: List[float] = field(default_factory=lambda: [1.2, 1.8, 1.5])
    rotation_deg: List[float] = field(default_factory=lambda: [-35.0, 30.0, 0.0])
    width: float = 0.60   # meters
    height: float = 0.60  # meters
    intensity: float = 1.0
    color_rgb: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    temperature_kelvin: float = 5600.0  # Daylight standard
    energy_convention: EnergyConvention = EnergyConvention.FIXED_RADIANCE
    enabled: bool = True
    cast_shadows: bool = True
```

### 2.2 `StudioScene` State Model
```python
@dataclass
class StudioScene:
    metadata: SceneMetadata = field(default_factory=lambda: SceneMetadata(version="3.1.0"))
    camera: CameraData = field(default_factory=CameraData)
    subject: SubjectProxyData = field(default_factory=SubjectProxyData)
    receiver: ReceiverData = field(default_factory=ReceiverData)
    lights: List[AreaLightData] = field(default_factory=lambda: [AreaLightData()])
    render_settings: RenderSettingsData = field(default_factory=RenderSettingsData)
    active_light_id: Optional[str] = None
```

---

## 3. Physical & Numerical Validation Invariants

In `StudioScene.validate()`:
1. **Light Count Bounds:** $1 \le |\text{lights}| \le 8$.
   - A scene must contain at least 1 light to maintain valid photographic illumination.
   - The upper bound of 8 lights is bounded by Apple Silicon Metal constant memory alignment and interactive frame time budgets.
2. **Identifier Uniqueness:** Light IDs must be non-empty strings, and no duplicate IDs are permitted.
3. **Active Light Coherence:** `active_light_id` must reference an existing light in `self.lights`. If unassigned or orphaned, it automatically defaults to `self.lights[0].id`.
4. **Finite Floats:** All numerical coordinates and radiant parameters are strictly validated via `validate_finite_floats()`.

---

## 4. Multi-Light Manipulation API

`StudioScene` provides high-level transaction methods:

| Method | Signature | Behavioral Contract |
|:---|:---|:---|
| `get_light` | `(light_id: str) -> Optional[AreaLightData]` | Looks up light by stable identifier. |
| `get_active_light` | `() -> AreaLightData` | Returns currently selected light; falls back to `lights[0]`. |
| `select_light` | `(light_id: str) -> bool` | Updates `active_light_id` if ID exists. |
| `add_light` | `(light: Optional[AreaLightData] = None) -> AreaLightData` | Adds new light (auto-generating unique ID and spatial offset), selects it. Raises `ValueError` if count exceeds 8. |
| `remove_light` | `(light_id: str) -> bool` | Deletes light by ID. Raises `ValueError` if attempting to delete the last remaining light. Reassigns `active_light_id`. |
| `duplicate_light` | `(light_id: str) -> AreaLightData` | Clones light with a physical 25 cm spatial offset and unique ID. |
| `toggle_light` | `(light_id: str, enabled: Optional[bool] = None) -> bool` | Toggles or sets light active emission. |
| `toggle_light_shadows` | `(light_id: str, cast_shadows: Optional[bool] = None) -> bool` | Toggles or sets per-light shadow ray tracing. |
| `reorder_lights` | `(order_ids: List[str]) -> None` | Reorders light list matching exact ID permutation. |

---

## 5. Backward Compatibility & Migration Verification

### 5.1 Legacy v3.0.0 Migration
When deserializing older scene files created during RS-SPIKE-3A through RS-SPIKE-3C.0:
- If `metadata.version` is `"3.0.0"`, it is seamlessly bumped to `"3.1.0"`.
- If `cast_shadows` is omitted from any light dictionary, it defaults to `True`.
- If `id` or `name` is omitted, stable identifiers (`"light_1"`, `"Studio Light 1"`) are generated.
- If `active_light_id` is omitted, it defaults to `lights[0].id`.

### 5.2 Deterministic Replay & Undo/Redo Test
In `SceneStateManager`:
```python
sm = SceneStateManager(StudioScene())
sm.current_scene.add_light()
sm.push_state(sm.current_scene)
assert len(sm.current_scene.lights) == 2

sm.undo()
assert len(sm.current_scene.lights) == 1

sm.redo()
assert len(sm.current_scene.lights) == 2
```
Every snapshot is fully validated JSON. Re-deserializing produced identical state dictionaries with zero float deviation.

---

## 6. Conclusion & Gate Sign-off

Phase 1 is complete and verified against all unit and regression tests. The multi-light scene architecture is stable and ready for **Phase 2: Additive Illumination Mathematics & CPU Reference**.
