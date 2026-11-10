# RELIGHT STUDIO — RS-PRODUCT-1.1 INTERACTION VALIDATION
## 3D Interaction Mathematics, Gizmo Tracking & Viewport Navigation

**Document:** `RS_PRODUCT_1_1_INTERACTION_VALIDATION.md`  
**Milestone:** RS-PRODUCT-1.1  
**Status:** **VERIFIED & PASSING**

---

## 1. 3D PROJECTION & DRAG MAPPING MATHEMATICS

To achieve predictable, tactile interaction, the 3D stage camera perspective projection and mouse drag vectors must be mathematically aligned without arbitrary scaling heuristics.

### 1.1 Camera Basis and Perspective Projection
The stage camera orbits around target $\mathbf{p}_{\text{target}} = [x_{\text{pan}}, 0.35, z_{\text{pan}}]^\top$ at spherical angles $\theta$ (yaw) and $\phi$ (pitch) with distance $r$:

$$\mathbf{p}_{\text{cam}} = \mathbf{p}_{\text{target}} + \begin{bmatrix} r \cos \phi \sin \theta \\ r \sin \phi \\ r \cos \phi \cos \theta \end{bmatrix}$$

The camera orthonormal frame $(\hat{\mathbf{r}}, \hat{\mathbf{u}}, \hat{\mathbf{f}})$ is constructed:
$$\hat{\mathbf{f}} = \frac{\mathbf{p}_{\text{target}} - \mathbf{p}_{\text{cam}}}{\|\mathbf{p}_{\text{target}} - \mathbf{p}_{\text{cam}}\|}, \quad \hat{\mathbf{r}} = \frac{\hat{\mathbf{f}} \times \hat{\mathbf{y}}}{\|\hat{\mathbf{f}} \times \hat{\mathbf{y}}\|}, \quad \hat{\mathbf{u}} = \hat{\mathbf{r}} \times \hat{\mathbf{f}}$$

Given focal length $f = \frac{H / 2}{\tan(\text{FOV} / 2)}$, any world point $\mathbf{P} \in \mathbb{R}^3$ projects to screen coordinates $(s_x, s_y)$:
$$\mathbf{P}_{\text{rel}} = \mathbf{P} - \mathbf{p}_{\text{cam}}, \quad z_{\text{cam}} = \mathbf{P}_{\text{rel}} \cdot \hat{\mathbf{f}}$$
$$s_x = \frac{W}{2} + \frac{\mathbf{P}_{\text{rel}} \cdot \hat{\mathbf{r}}}{z_{\text{cam}}} f, \quad s_y = \frac{H}{2} - \frac{\mathbf{P}_{\text{rel}} \cdot \hat{\mathbf{u}}}{z_{\text{cam}}} f$$

### 1.2 World Displacement from Screen Drag
Let the light origin in world space be $\mathbf{p}_0$ with screen projection $\mathbf{s}_0 = (s_{x0}, s_{y0})$. For any unit axis vector $\hat{\mathbf{v}} \in \{\hat{\mathbf{x}}, \hat{\mathbf{y}}, \hat{\mathbf{z}}\}$, the 1-meter point $\mathbf{p}_1 = \mathbf{p}_0 + \hat{\mathbf{v}}$ projects to screen coordinate $\mathbf{s}_1 = (s_{x1}, s_{y1})$.

The screen vector representing 1 meter along the axis is:
$$\mathbf{v}_{\text{axis}} = \mathbf{s}_1 - \mathbf{s}_0, \quad L = \|\mathbf{v}_{\text{axis}}\| \quad (\text{pixels per meter})$$

When the user moves the mouse by screen displacement $\Delta \mathbf{m} = (\Delta x, \Delta y)$, the projected distance along the axis in meters is:
$$\Delta d_{\text{meters}} = \frac{\Delta \mathbf{m} \cdot \mathbf{v}_{\text{axis}}}{L^2} = \frac{\Delta \mathbf{m} \cdot \hat{\mathbf{u}}_{\text{axis}}}{L}$$

where $\hat{\mathbf{u}}_{\text{axis}} = \mathbf{v}_{\text{axis}} / L$.

This guarantees:
1. **1:1 Visual Alignment:** Mouse movement parallel to the projected gizmo axis translates the object so that the gizmo handle tracks directly beneath the mouse cursor.
2. **Perspective Scaling:** When the light is farther from the camera ($L$ is smaller), larger screen movements are required for equivalent metric displacement; when near the camera ($L$ is larger), smaller screen movements produce fine metric precision.
3. **Orthogonal Invariance:** Mouse motion perpendicular to $\mathbf{v}_{\text{axis}}$ produces zero displacement ($\Delta \mathbf{m} \cdot \hat{\mathbf{u}}_{\text{axis}} = 0$), preventing accidental jitter along unselected degrees of freedom.

---

## 2. CLIENT-SIDE HIT TESTING & INTERACTION STATE MACHINE

### 2.1 Hit-Testing Algorithms
When mouse events occur on `stageCanvas`, coordinates are transformed into image space $(i_x, i_y)$. Distances to gizmo handles and axis segments are evaluated:

```
                  +----------------------------------+
                  |         stageCanvas Event        |
                  +----------------------------------+
                                   |
                  +----------------------------------+
                  |  Point-to-Segment Distance Check |
                  +----------------------------------+
                   /               |                \
    d(P, Pitch/Yaw) < 16px    d(P, Axis X/Y/Z) < 12px   d(P, Light Center) < 22px
          |                        |                        |
     Rotation Gizmo          Translation Gizmo         Select Light Object
     (PITCH / YAW)             (X / Y / Z)             (Focus Inspector)
```

For translation axes, distance from point $P$ to segment $AB$ is calculated:
$$t = \text{clamp}\left(\frac{(P - A) \cdot (B - A)}{\|B - A\|^2}, 0, 1\right), \quad \text{dist} = \|P - (A + t(B - A))\|$$

### 2.2 Interaction State Machine
```
   [ Idle State ]
         |
         | mousedown on Gizmo Handle
         v
   [ Begin Interaction ] -----> POST /api/interaction/begin
         |                      (Switches to Preview Render Mode, N=4)
         | mousemove (continuous)
         v
   [ Dragging Active Axis ] --> POST /api/stage/drag
         |                      (Real-time light update, skips undo stack)
         | mouseup
         v
   [ End Interaction ] -------> POST /api/interaction/end
                                (Consolidates 1 undo state, triggers Final Render, N=25-32)
```

---

## 3. INTERACTION EVIDENCE LOG

The following table records the reproducible sequence captured during automated execution of [`scripts/capture_product_1_1_screenshots.py`](file:///Users/sumirdayal/religth%20studio/scripts/capture_product_1_1_screenshots.py):

| Step | User Gesture | Active Target | Resulting Scene Coordinates | Photographic Luminance | Evidence Status |
|---|---|---|---|---|---|
| 1 | Baseline Selection | `light_01` | Position: `[1.200, 1.800, 1.500]` | $0.2022$ | **VERIFIED** |
| 2 | Drag X (+80px screen) | `light_01` | Position: `[1.348, 1.800, 1.500]` | $0.2014$ | **VERIFIED** |
| 3 | Drag Y (-70px screen) | `light_01` | Position: `[1.348, 1.909, 1.500]` | $0.2010$ | **VERIFIED** |
| 4 | Drag Z (+60px screen) | `light_01` | Position: `[1.348, 1.909, 1.368]` | $0.2011$ | **VERIFIED** |
| 5 | Rotate Pitch & Yaw | `light_01` | Rotation: `[-50.0°, 5.0°, 0.0°]` | $0.2007$ | **VERIFIED** |
| 6 | Resize Dimensions | `light_01` | Width: $1.0\,\text{m}$, Height: $1.0\,\text{m}$ | $0.2110$ | **VERIFIED** |

### Findings from Interaction Evidence:
1. **Physical Lighting Correlation:** Increasing area light dimensions from $0.6 \times 0.6\,\text{m}$ to $1.0 \times 1.0\,\text{m}$ expands the emitting area by factor $(1.0 \times 1.0) / (0.6 \times 0.6) = 2.77\times$, increasing photographic mean luminance from $0.2007$ to $0.2110$ under fixed radiance convention.
2. **Camera Isolation Guarantee:** Orbiting the camera from $(\text{yaw}=35^\circ, \text{pitch}=25^\circ)$ to $(\text{yaw}=55^\circ, \text{pitch}=35^\circ)$ verified that light positions, intensities, and subject proxy dimensions remained bitwise invariant.
3. **Consolidated Undo Stack:** Moving the light across 80 screen pixels generated 12 discrete drag updates, but upon mouse release, exactly one consolidated state was pushed to the undo stack, allowing immediate single-keystroke undo.
