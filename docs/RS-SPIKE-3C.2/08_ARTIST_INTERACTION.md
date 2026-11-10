# RELIGHT STUDIO — RS-SPIKE-3C.2
## Technical Report 08: Artist Interaction & Workspace Material Control Architecture

**Author:** Principal Product Interaction Engineer & Graphics Systems Builder  
**Milestone:** RS-SPIKE-3C.2 — Specular Microfacet BRDFs & Material Transport  
**Implementation Source:** `studio3a/workspace.py`, `studio3a/material.py`, `studio3a/scene.py`  
**Test Suite:** `tests/RS-SPIKE-3C.2/test_artist_interaction.py` (5/5 PASSED, 0.38s)

---

### 1. Executive Summary & Artist Experience

In RS-SPIKE-3C.2, Relight Studio expands from diffuse lighting manipulation into an artist-controlled material studio.
The artist can now alter the physical surface response of any photographic subject:
- Changing a dull sneaker into glossy patent leather or high-sheen synthetic polymer.
- Shifting a limestone sculpture into smooth honed marble or polished bronze.
- Inspecting specular highlights independently without diffuse illumination distractors.

Every material interaction maintains the core product guarantees:
1. **Interactive Fluidity:** Slider adjustments re-render in real time on Apple Silicon GPU ($< 10\,\text{ms}$).
2. **Deterministic State:** Every parameter adjustment pushes an immutable scene snapshot onto the `SceneStateManager` stack, enabling complete multi-level Undo/Redo.
3. **Lossless Preset Serialization:** Material parameters serialize directly into the version 3.2.0 JSON schema.

---

### 2. Workspace Control Architecture

#### 2.1 The Material Inspector (`StudioWorkspaceSession`)

The session controller exposes four primary material interaction methods:

```python
class StudioWorkspaceSession:
    def set_material_profile(self, profile_name: str) -> Dict[str, Any]:
        """Switches material to one of the 5 canonical PBR profiles."""
        ...
        
    def update_material_params(
        self,
        roughness: float,
        metallic: float,
        specular_f0: float = 0.04,
        specular_intensity: float = 1.0,
        base_color: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """Modulates continuous microfacet BRDF sliders with Undo support."""
        ...
        
    def toggle_specular(self, enable_specular: Optional[bool] = None) -> Dict[str, Any]:
        """Toggles specular transport calculation."""
        ...
        
    def toggle_specular_only(self, specular_only: Optional[bool] = None) -> Dict[str, Any]:
        """Toggles specular highlight isolation diagnostic view."""
        ...
```

#### 2.2 Canonical Physical Material Profiles

Artists can pick from five curated factory presets:

| Profile Label | Physical Target | Roughness ($\alpha$) | Metallic ($m$) | Dielectric $F_0$ | Specular Multiplier | Visual Response |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Fabric** | Knit Canvas / Wool | $0.85$ | $0.00$ | $0.030$ | $0.50$ | Wide diffuse scattering, very broad and soft sheen. |
| **Marble** | Honed Stone / Plaster | $0.35$ | $0.00$ | $0.045$ | $1.00$ | Smooth surface with tight curvature gleams. |
| **Plastic** | Molded Polymer / Vinyl | $0.22$ | $0.00$ | $0.040$ | $1.00$ | Sharp, crisp softbox highlights, achromatic reflections. |
| **Rough Metal** | Brushed Steel / Bronze | $0.45$ | $1.00$ | $\text{base\_color}$ | $1.00$ | Tinted metallic sheen across geometry contours. |
| **Polished Metal**| Mirror Chrome / Gold | $0.08$ | $1.00$ | $\text{base\_color}$ | $1.00$ | Mirror-like pinpoint specular softbox reflections. |

---

### 3. Viewport Display & Inspection Modes

In `build_gradio_workspace`, the photograph viewport supports six display modes:
1. **Relit Output:** Full photographic composite with Two-Scale diffuse regularized ratio and specular radiance.
2. **Side-by-Side Split:** Interactive split-slider comparison between the original photograph and relit composite.
3. **Specular Highlight Only:** Darkens all diffuse illumination, displaying pure isolated specular reflections from virtual lights. Allows artists to position lights for maximum geometric rim highlights.
4. **Proxy Wireframe Overlay:** Superimposes 3D geometry bounds over the 2D photograph.
5. **Direct Visibility Heatmap:** Visualizes geometric occlusion and penumbral shadows.
6. **Original Photograph:** Raw input plate for instant A/B comparison.

---

### 4. Verification Evidence

All 5 automated interaction tests in `tests/RS-SPIKE-3C.2/test_artist_interaction.py` pass cleanly:
- `test_workspace_material_profile_selection`: Verified profile initialization and parameter binding.
- `test_workspace_material_parameter_adjustment`: Verified real-time slider manipulation.
- `test_workspace_specular_toggles`: Verified specular-only isolation and specular kill-switch.
- `test_workspace_undo_redo_material_history`: Verified multi-step undo/redo stack consistency across material changes.
- `test_workspace_scene_preset_save_and_load`: Verified backward-compatible JSON preset roundtripping.
