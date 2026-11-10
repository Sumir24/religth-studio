# RELIGHT STUDIO — RS-PRODUCT-1.2 BASELINE & ARCHITECTURE AUDIT
## Photographic Scene Alignment & Geometry Editing

**Milestone:** RS-PRODUCT-1.2  
**Role:** Principal 3D Graphics Engineer, Computational Photography Researcher, macOS Product Architect  
**Starting Commit:** `39cbc66` (Branch: `feature/RS-PRODUCT-1.2-photo-alignment`)  
**Parent Milestone:** RS-PRODUCT-1.1 (`feature/RS-PRODUCT-1.1-interactive-scene`)  
**Platform:** macOS / Apple Silicon / Metal 3  
**Audit Date:** 2026-11-11  

---

## 1. EXISTING ARCHITECTURE & COMPLETE DATA FLOW

Relight Studio is currently implemented as an Apple Silicon-accelerated local web application consisting of a FastAPI server and HTML5 Canvas client interfacing via ctypes C-ABI directly with native compiled Metal shaders (`libmetal2.dylib`).

```
+----------------------------------------------------------------------------------------------------+
|                                    RELIGHT STUDIO SYSTEM ARCHITECTURE                              |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [ Photograph Asset ] (.jpg/.png)                                                                   |
|          |                                                                                         |
|          v                                                                                         |
|  [ RelightProject ] (Bundle persistence, manifest.json, scene.json, immutable original source)     |
|          |                                                                                         |
|          v                                                                                         |
|  [ StudioScene ] (Authoritative state: CameraData, SubjectProxyData, ReceiverData, AreaLightData)  |
|          |                                                                                         |
|          +----------------------------------+----------------------------------+                   |
|          |                                  |                                  |                   |
|          v                                  v                                  v                   |
|  [ StudioAppController ]           [ SceneStateManager ]          [ RenderingOrchestrator ]        |
|  - 3D Gizmo Drag Projection        - Undo/Redo Snapshots          - Worker thread                  |
|  - Stage Orbit/Pan/Focus/Reset     - Monotonic History            - Stale request cancellation     |
|  - Preset Application              - State Deep Copy              - Metal GPU & CPU Dispatch       |
|          |                                                                     |                   |
|          v                                                                     v                   |
|  [ FastAPI HTTP Server ]                                          [ MetalRenderBackend ]           |
|  - /api/state/full                                                - Zero-copy unified memory       |
|  - /api/stage/projection_meta                                     - Cook-Torrance GGX & IBL        |
|  - /api/stage/drag                                                - E.1 Guided-Filter Reconstruct  |
|  - /api/camera/params, /api/subject/params                                     |                   |
|          |                                                                     |                   |
|          +----------------------------------+----------------------------------+                   |
|                                             |                                                      |
|                                             v                                                      |
|                             [ HTML5 Canvas Client (app.js) ]                                       |
|                             - Region A: Photograph Viewport (Relit / Split Wipe)                   |
|                             - Region B: 3D Studio Stage (Frustum, Grid, Area Lights, Gizmos)       |
|                             - Region C: Scene Hierarchy Tree                                       |
|                             - Region D: Context Inspector                                          |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

### Complete End-to-End Data Flow:
$$\text{Photograph} \longrightarrow \text{Camera3D} \longrightarrow \text{Proxy Geometry} \longrightarrow \text{Receiver Surface} \longrightarrow \text{Multi-Light Shaders} \longrightarrow \text{E.1 Reconstruction} \longrightarrow \text{Dual Viewports}$$

- **Authoritative Values:** `StudioScene` attributes (camera pose and FOV, subject proxy dimensions and rotation, receiver plane/cove, light radiometric parameters).
- **Derived Values:** Camera basis ($\mathbf{fwd}, \mathbf{right}, \mathbf{up}$), view/projection matrices, ray origins/directions, shadow occlusion maps, screen gizmo handle pixel coordinates.

---

## 2. CURRENT CAMERA & PROJECTION MODEL

### 2.1 Camera Representations
There are two distinct camera systems in Relight Studio:
1. **Photograph Camera (`scene.camera`, [`studio3a/camera.py`](file:///Users/sumirdayal/religth%20studio/studio3a/camera.py)):**
   - Vectorized pinhole camera defining the projection through which the photograph was captured and through which virtual lighting and ray tracing are rendered.
   - Parameters: `pos` $[X, Y, Z]$, `target` $[X, Y, Z]$, `up` $[X, Y, Z]$, `fov_deg`, `width`, `height`, `focal_length_mm`.
   - Generates camera rays:
     $$\mathbf{d} = \text{ndc}_x \hat{\mathbf{r}} + \text{ndc}_y \hat{\mathbf{u}}_{\text{cam}} + \hat{\mathbf{f}}$$
2. **3D Stage Viewport Camera (`controller._get_stage_projector`, [`relight_studio/controller.py`](file:///Users/sumirdayal/religth%20studio/relight_studio/controller.py#L380-L420)):**
   - Perspective orbit camera allowing the artist to inspect the virtual 3D lighting rig from an external viewpoint.
   - Parameters: `stage_orbit_yaw_deg`, `stage_orbit_pitch_deg`, `stage_orbit_dist`, `stage_pan_offset`.

### 2.2 Camera Gaps & Deficiencies
- **Disconnection in Inspector:** The inspector currently only exposes a single slider for `fov_deg`. There is no way to edit camera height, distance, pitch, yaw, roll, or target point.
- **Missing Focal Length Coupling:** `focal_length_mm` ($50\,\text{mm}$) is defined in `CameraData` but was not bidirectionally synchronized with `fov_deg` ($45^\circ$).
- **No Direct Photographic Overlay:** The Photograph Viewport (Region A) displays only the rendered image or split wipe. It provides zero visual projection of the virtual camera's alignment against the photo.

---

## 3. EXISTING PROXY GEOMETRY CAPABILITIES

### 3.1 Supported Geometry Classes ([`studio3a/geometry.py`](file:///Users/sumirdayal/religth%20studio/studio3a/geometry.py))
- **Oriented Bounding Box (`OBB`):** Slab-based ray-box intersection with 3-axis rotation matrix $R = R_y R_x R_z$ and half-extents $[e_x, e_y, e_z]$.
- **Superquadric Ellipsoid (`SUPERQUADRIC`):** Analytic inside-outside function $F(x, y, z) = ((x/a)^{2/e_2} + (y/b)^{2/e_2})^{e_2/e_1} + (z/c)^{2/e_1} - 1 = 0$ solved via bracketed root-finding.
- **Sphere (`SPHERE`):** Analytic quadric intersection with center $[X, Y, Z]$ and radius $r$.
- **Mesh (`MESH`):** Triangular hull with BVH-accelerated Möller-Trumbore intersection.

### 3.2 Proxy Alignment Limitations
- **Gizmo Missing on Subject:** In RS-PRODUCT-1.1, the 3D stage transform gizmo was only attached to active lights (`active_light`). When the artist clicked `subject`, no translation, rotation, or scale gizmo appeared in the 3D stage.
- **Missing Roll Axis:** The rotation handles only allowed Pitch and Yaw. The third degree of rotational freedom (Roll around $Z$) was omitted.
- **No Ground Snap / Elevation Helper:** Artists had to manually guess the $Y$ elevation to make the proxy touch the ground plane without intersecting or hovering.

---

## 4. EXISTING RECEIVER MODEL

- **Types:** Infinite planar ground (`PLANE`) and studio fillet cyclorama (`CYCLORAMA`).
- **Fillet Mathematics:** Cylinder cove tangent to ground plane at $y = \text{ground\_y}$ and wall at $z = \text{wall\_z}$ with radius $r = \text{cove\_radius}$.
- **Receiver Limitations:** No visual contact line or shadow boundary guide is drawn on the photographic plate. The artist cannot easily tell whether the virtual floor matches the real table/floor plane of the photograph.

---

## 5. EXISTING ALIGNMENT & INTERACTION LIMITATIONS

1. **Blind Alignment:** To align the 3D scene to a photo, the artist currently has to adjust sliders and look at the 3D stage from the side, with no visual overlay on the actual photograph plate.
2. **Missing Diagnostic Metrics:** No quantitative silhouette overlap (IoU) or bounding-box error metrics are computed between the projected proxy and the foreground mask (`fg_mask`).
3. **No Camera Presets:** Missing photographer standard focal length presets (24mm Wide, 35mm Street, 50mm Normal, 85mm Portrait, 105mm Macro).
4. **Near-Parallel Gizmo Singularities:** When an axis aligns closely with the camera line of sight, projection length $L \to 0$, creating potential division-by-zero instability.

---

## 6. TECHNICAL RISKS & MITIGATION STRATEGY

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Projection Discrepancy** | Photograph overlay does not match rendered Metal ray tracing. | Invariant: Both overlay drawing and ray generation MUST use the exact same `Camera3D.project_point()` and `view_matrix` formulation. |
| **Undo Stack Pollution** | Continuous camera or proxy dragging pushes hundreds of micro-states. | Reuse `begin_interaction()` and `end_interaction()` lifecycle to consolidate exactly one undo snapshot per gesture. |
| **Axis Singularity** | Dragging gizmo when axis points into camera causes infinite metric displacement. | Enforce minimum screen projection length check ($L > 4\,\text{px}$); if axis is near-parallel to view ray, gracefully fall back to screen-aligned mouse delta. |
| **Missing Asset Crash** | Renamed or relocated photograph files cause unhandled exceptions. | Display explicit missing-asset UI modal banner with asset recovery path dialog instead of silent failure. |

---

## 7. PROPOSED IMPLEMENTATION PLAN

```
Phase 1: Photographic Camera Matching
  ├── Synchronized Focal Length (mm) <-> FOV (deg)
  ├── Camera Position [X, Y, Z], Target [X, Y, Z], Pitch/Yaw/Roll Controls
  ├── Camera Presets: 24mm, 35mm, 50mm, 85mm, 105mm
  └── Direct Image-Space Alignment Overlays on Photograph Viewport (Wireframe, Silhouette, Opacity Blend, Guides)

Phase 2: Subject Proxy Alignment & Complete 3D Geometry Editing
  ├── 3D Transform Gizmo enabled on Subject Proxy (Translation X/Y/Z)
  ├── Full 3-Axis Rotation Gizmo (Pitch, Yaw, ROLL)
  ├── Dimensional Scaling (Width, Height, Depth, Uniform Scale)
  └── Snap-to-Ground / Drop-to-Floor Action

Phase 3: Receiver and Ground-Contact Alignment
  ├── Ground Elevation, Cove Radius, Wall Distance Controls
  ├── Ground Plane Grid & Contact Line Visualization
  └── Shadow Receiving & Contact Shadow Alignment

Phase 4: Alignment Diagnostics
  ├── Projected Silhouette IoU against Foreground Segmentation Mask (fg_mask)
  ├── Bounding Box Fit Metrics
  └── Contact Gap / Ground Penetration Measurement

Phase 5: Photographic Lighting Response Validation
  ├── Spatial response metrics: local luminance, shadow centroid, direction, highlight shift
  └── Multi-scenario verification suite

Phase 6: Persistence, Schema 1.2.0 & Resilience
  ├── Full alignment and overlay state serialized into .relight bundle
  └── Explicit missing asset handling dialog and recovery

Phase 7: Test Suite, Benchmarking & Visual QA
  ├── 100% automated test pass
  └── 10+ High-DPI screenshots verifying all alignment modes
```

**Baseline Audit Verdict:** **APPROVED TO PROCEED TO PHASE 1.**
