# RELIGHT STUDIO — RS-SPIKE-3A
## Artist Interaction, Dual-Viewport UI & Workflow Verification

**Document:** `docs/RS-SPIKE-3A/06_ARTIST_WORKFLOW_REPORT.md`  
**Status:** Approved Engineering Baseline  
**Milestone:** RS-SPIKE-3A  
**Date:** November 2026  

---

### 1. Interaction Model Design

Relight Studio is built specifically for commercial photographers, art directors, and 3D visualizers. It adheres strictly to the principle of **Virtual Gaffer Pair-Programming**:
- The artist directs the lighting setup using familiar photographic terminology (Key light, Fill light, Softbox dimensions, Kelvin color temperature, Power in Watts vs Radiance).
- The system translates these high-level artistic controls into physically based 3D radiometric transport, re-evaluating illumination and non-destructively reconstructing the photographic plate.

The interactive workspace is organized into three synchronized regions:

```
+----------------------------------------------------------------------------------------------------+
|                                    RELIGHT STUDIO WORKSPACE                                        |
+-------------------------------------------------+--------------------------------------------------+
| VIEWPORT 1: PHOTOGRAPH VIEWPORT                 | VIEWPORT 2: VIRTUAL 3D STUDIO STAGE VIEWPORT    |
| - High-resolution photograph plate              | - 3/4 perspective 3D studio visualization        |
| - Interactive Before / After Wipe Slider        | - Virtual camera frustum pyramid                 |
| - 3D Wireframe Proxy overlay toggle             | - Subject proxy geometry                         |
| - Radiometric luminance error heatmaps          | - Receiver floor grid & cyclorama cove arc       |
|                                                 | - 3D Rectangular area light quad + normal vector |
+-------------------------------------------------+--------------------------------------------------+
| REGION 3: CONTEXT INSPECTOR (CONTROL PANEL)                                                        |
| - Area Light: Pos (X,Y,Z), Rotation (Pitch,Yaw,Roll), Dimensions (W,H), Intensity, Temp (Kelvin) |
| - Geometry: Proxy Type (OBB, Superquadric, Mesh), Receiver Type (Plane, Cyclorama)                 |
| - Quality & History: Preview (4 MC) vs Final (32 MC), Undo, Redo, Save JSON, Load JSON             |
+----------------------------------------------------------------------------------------------------+
```

---

### 2. Dual-Viewport Implementation

#### 2.1 Viewport 1: Photographic Plate Viewport
- **Modes:**
  - `Relit`: Full-resolution reconstructed linear-radiance photograph.
  - `Original`: Pristine, untouched original photograph.
  - `Before/After Wipe`: Interactive horizontal split-screen wipe (left = original, right = relit) enabling instant perceptual comparison of specular transitions, contact shadows, and color temperatures.
  - `Proxy Overlay`: Orthogonal projection of the 3D subject proxy wireframe overlaid onto the photo plate, allowing the artist to precisely align the proxy with the photographed product.
  - `Luminance Error Heatmap`: False-color perceptual difference map displaying $\Delta Y = |Y_{\text{relit}} - Y_{\text{orig}}|$ to verify detail preservation.

#### 2.2 Viewport 2: Virtual 3D Stage Viewport
- Renders an isometric / 3/4 perspective projection of the entire virtual studio:
  - Coordinate reference grid showing physical meter markers.
  - Cyclorama cove profile showing curvature transition from floor to wall.
  - Camera frustum showing lens optical axis, apex, and near/far plane corners.
  - Subject proxy wireframe positioned at its 3D coordinates.
  - Area light representation showing rectangular emitter frame, surface center, and yellow outward normal arrow indicating emission orientation.

---

### 3. Artist Workflow Verification

We conducted an end-to-end verification session simulating a commercial studio setup:

1. **Step 1: Photograph Ingestion:**
   The user imports a product photograph (`nike_sample.jpg`). The plate is decoded into linear sRGB float32 space and cached immutably.
2. **Step 2: Camera & Proxy Alignment:**
   The user selects the `MESH` proxy for the footwear product and sets the virtual camera distance and FOV. The 3D wireframe overlay confirms alignment with the shoe contour.
3. **Step 3: Receiver Selection:**
   The user chooses between an infinite ground plane or a curved cyclorama backdrop.
4. **Step 4: Light Manipulation:**
   The artist adjusts the Key softbox:
   - Position: $[-0.9, 1.2, 0.8]\text{ m}$
   - Dimensions: $0.6\text{ m} \times 0.6\text{ m}$
   - Intensity: $2.5$
   - Temperature: $5600\text{K}$ (daylight neutral)
5. **Step 5: Interactive Preview:**
   Preview mode (4 Monte Carlo samples) updates in $\approx 140\text{ ms}$, providing responsive visual feedback as the light is repositioned.
6. **Step 6: Undo / Redo Audit:**
   The artist performs 5 consecutive edits, triggers 3 undos, and 2 redos. The state manager reconstructs the exact intermediate states with zero parameter drift.
7. **Step 7: Final Render & Deterministic Replay:**
   The artist triggers Final quality (32 samples). The scene is saved to `scene_session.json`. The scene is reloaded from disk and re-rendered.
   **Verification:** Absolute pixel difference between original render and reloaded render is **$0.000000$ (Bitwise Identical)**.
