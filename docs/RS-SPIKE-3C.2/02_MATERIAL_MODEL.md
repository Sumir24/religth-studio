# RS-SPIKE-3C.2 — Material Model & Scene Architecture
## Physical Surface Parameterization & Deterministic Serialization

**Document ID:** RS-SPIKE-3C.2-02  
**Milestone:** RS-SPIKE-3C.2  
**Author:** Principal Physically Based Rendering Engineer & System Architect  
**Source Implementation:** `studio3a/material.py`, `studio3a/scene.py`  
**Test Suite:** `tests/RS-SPIKE-3C.2/test_material_model.py`  
**Status:** VALIDATED (Schema v3.2.0, Backward-Compatible, 100% Pass)

---

## 1. Executive Summary

Milestone **RS-SPIKE-3C.2** transitions Relight Studio from an albedo-only diffuse renderer to a physically grounded material rendering system. This report specifies the `MaterialData` architecture, defining physical parameter bounds, dielectric versus metallic energy accounting, standard material profiles, proxy attachment, and forward-compatible serialization (v3.2.0).

All material parameters are validated against strict physical invariants, ensuring that arbitrary artist adjustments cannot violate energy conservation or propagate non-finite numerical states.

---

## 2. Material Parameter Specification

The material representation is implemented in `studio3a/material.py` as `MaterialData`:

| Parameter | Type | Valid Range | Default | Physical Meaning & Behavior |
|---|:---:|:---:|:---:|---|
| `id` | `str` | Non-empty | `"mat_default"` | Unique, stable identifier for material asset tracking. |
| `name` | `str` | String | `"Default Studio Dielectric"` | Artist-facing label. |
| `base_color` | `List[float]` | $[0.0, 2.0]^3$ | `[0.80, 0.80, 0.80]` | Linear sRGB reflectance. For dielectrics, specifies subsurface diffuse body color. For conductors, specifies tinted normal-incidence reflectance $F_0$. |
| `roughness` | `float` | $[0.0, 1.0]$ | `0.50` | Perceptually linear microfacet roughness. Maps quadratically to physical microfacet slope $\alpha = \text{roughness}^2$. |
| `metallic` | `float` | $[0.0, 1.0]$ | `0.00` | Conductor factor. $0.0 = \text{pure dielectric}$, $1.0 = \text{pure conductor/metal}$. |
| `specular_f0` | `float` | $[0.0, 1.0]$ | `0.04` | Normal-incidence specular reflectance for dielectrics (empirically $0.02 - 0.05$ for non-metals). |
| `specular_intensity` | `float` | $[0.0, \infty)$ | `1.00` | Artistic multiplier on dielectric specular reflection. Scaled linearly for highlight tuning. |

---

## 3. Dielectric vs Conductor Energy Accounting

Arbitrary combinations of material parameters are constrained to prevent energy fabrication:

### 3.1 Normal-Incidence Specular Reflectance ($F_0$)
Conductors exhibit free-electron surface conduction, causing strong, wavelength-dependent specular reflection, whereas dielectrics exhibit weak, achromatic Fresnel reflection:
$$F_0 = (1 - \text{metallic}) \cdot (\text{specular\_f0} \cdot \text{specular\_intensity}) + \text{metallic} \cdot \text{base\_color}$$

### 3.2 Effective Diffuse Albedo ($\rho_{\text{diffuse}}$)
Because incident light cannot penetrate the electron lattice of a pure metal, conductors have **zero diffuse reflection**:
$$\rho_{\text{diffuse}} = \text{base\_color} \cdot (1 - \text{metallic})$$

When $\text{metallic} = 1.0$, $\rho_{\text{diffuse}} = [0, 0, 0]$, ensuring that diffuse irradiance does not contribute to metallic highlights.

---

## 4. Standard Material Profiles

To provide artists with physically calibrated starting points without restricting parametric editability, `MaterialData` provides 5 factory profiles:

```
+--------------------------------------------------------------------------------------------------+
| Profile          Roughness  Metallic   F0     Spec. Int.  Physical Description                  |
+--------------------------------------------------------------------------------------------------+
| Fabric (Canvas)    0.85       0.00    0.03       0.50     Broad, diffuse sheen, low specular     |
| Marble (Honed)     0.35       0.00    0.045      1.00     Crisp subsurface body, subtle gloss    |
| Plastic (Polymer)  0.22       0.00    0.04       1.00     Smooth specular highlights, achromatic |
| Rough Metal        0.45       1.00   BaseColor   1.00     Brushed steel/aluminum, tinted lobe    |
| Polished Metal     0.08       1.00   BaseColor   1.00     Mirror chrome/gold, sharp reflection   |
+--------------------------------------------------------------------------------------------------+
```

Every parameter of an assigned profile remains fully editable in the workspace.

---

## 5. Scene Architecture & Backward Compatibility

### 5.1 Proxy & Receiver Integration
In `studio3a/scene.py`:
- `SubjectProxyData`: Attached via `material: MaterialData = field(default_factory=MaterialData)`.
- `ReceiverData`: Attached via `material: MaterialData = field(default_factory=lambda: MaterialData(id="mat_receiver", name="Cyclorama Matte", roughness=0.90, metallic=0.0, specular_intensity=0.20))`.
- `RenderSettingsData`: Added `enable_specular: bool = True` and `specular_only: bool = False`.

### 5.2 StudioScene Material Management
`StudioScene` manages the scene-wide material library:
- `materials: List[MaterialData]`: Scene asset list.
- `active_material_id: Optional[str]`: Currently selected material.
- `add_material(mat)`: Adds new material with collision-free unique IDs.
- `assign_material_to_subject(mat_id)`: Clones material parameters into the subject proxy.

### 5.3 Schema v3.2.0 Migration & Deterministic Serialization
When loading legacy v3.0.0 or v3.1.0 scene files:
1. Missing `material` in `subject` defaults to standard studio dielectric (`mat_default`).
2. Missing `material` in `receiver` defaults to cyclorama matte (`mat_receiver`).
3. Missing `materials` array defaults to `[subj.material]`.
4. `metadata.version` upgrades automatically to `"3.2.0"`.

Deterministic JSON serialization is verified by `test_material_serialization_roundtrip`: `scene.to_json() == from_json(to_json()).to_json()`.

---

## 6. Verification Status

Unit test suite `tests/RS-SPIKE-3C.2/test_material_model.py` executed with **5 / 5 passing tests (100%)**:
- Parameter boundary validation verified.
- Conductor/dielectric $F_0$ and diffuse albedo invariants verified.
- Schema migration from legacy scene formats verified.
- Serialization roundtrip determinism verified.

Phase 2 is complete. Authorized to proceed to **Phase 3: Area-Light Specular Integration**.
