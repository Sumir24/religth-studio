# RELIGHT STUDIO — RS-PRODUCT-1.2
## Subject Proxy Alignment & 3D Geometry Editing Specification

**Author:** Principal 3D Graphics Engineer & Interaction Designer  
**Milestone:** RS-PRODUCT-1.2  
**Status:** VALIDATED & ACCEPTED  

---

## 1. Executive Overview

Prior to RS-PRODUCT-1.2, virtual 3D proxies lacked full 3-axis rotation (the $Z$-axis Roll rotation was absent), lacked uniform and non-uniform dimensional scaling controls, suffered from near-parallel projection singularities during camera drags, and had no closed-form mechanism for resting proxies precisely on the ground floor.

RS-PRODUCT-1.2 introduces comprehensive 3D proxy manipulation:
1. **Full 3-Axis Translation:** $X$, $Y$, $Z$ position manipulation via 3D gizmo arrows and numerical inputs.
2. **Complete 3-Axis Rotation:** Pitch (around $X$), Yaw (around $Y$), and **Roll (around $Z$)** with interactive screen-space projected rotation rings.
3. **Multi-Axis Scaling:** Width ($X$), Height ($Y$), Depth ($Z$), and Uniform scaling.
4. **Near-Parallel Singularity Protection:** Automatic fallback for edge-on view angles preventing numerical blowup.
5. **Closed-Form Snap-to-Ground:** Exact analytical ground contact computation for OBBs, Superquadrics, and Spheres.

---

## 2. Mathematical Formulation

### 2.1 Oriented Bounding Box (OBB) Geometry
Let the subject proxy have center position $\mathbf{p} = [p_x, p_y, p_z]^T$, dimensions $\mathbf{d} = [w, h, d]^T$, and scale $\mathbf{s} = [s_x, s_y, s_z]^T$. The half-extents along the local principal axes are:

$$\mathbf{e} = \frac{1}{2} (\mathbf{d} \odot \mathbf{s}) = \begin{bmatrix} 0.5 w s_x \\ 0.5 h s_y \\ 0.5 d s_z \end{bmatrix}$$

The 3D orientation is defined by Euler angles $(\psi, \theta, \phi)$ corresponding to Pitch ($X$), Yaw ($Y$), and Roll ($Z$). The composite rotation matrix $\mathbf{R} = \mathbf{R}_z(\phi) \mathbf{R}_y(\theta) \mathbf{R}_x(\psi)$ maps local coordinates to world coordinates.

The 8 corner vertices in world space are given by:

$$\mathbf{v}_{i,j,k} = \mathbf{p} + \mathbf{R} \begin{bmatrix} (-1)^i e_x \\ (-1)^j e_y \\ (-1)^k e_z \end{bmatrix}, \quad i,j,k \in \{0, 1\}$$

### 2.2 Lowest Elevation & Closed-Form Ground Contact
To calculate the exact elevation of the lowest point of the proxy without costly discrete sampling:

#### For an Oriented Bounding Box (OBB):
Because an affine projection of a convex box onto the vertical axis $\mathbf{u}_y = [0, 1, 0]^T$ achieves its extremum at a vertex:

$$y_{\min} = p_y - \left( |R_{1,0}| e_x + |R_{1,1}| e_y + |R_{1,2}| e_z \right)$$

where $R_{1,c}$ denotes the second row of the rotation matrix $\mathbf{R}$.

#### For an Ellipsoid / Superquadric / Sphere:
The support function of an ellipsoid with semi-axes $(e_x, e_y, e_z)$ along direction vector $\mathbf{n} = [0, -1, 0]^T$ in world space yields the closed-form minimum elevation:

$$y_{\min} = p_y - \sqrt{ (R_{1,0} e_x)^2 + (R_{1,1} e_y)^2 + (R_{1,2} e_z)^2 }$$

### 2.3 Closed-Form Ground Snapping
Given receiver floor elevation $y_{\text{ground}}$, the ground gap is:

$$\Delta y_{\text{gap}} = y_{\min} - y_{\text{ground}}$$

The closed-form snap adjustment mutates only the $Y$ translation coordinate:

$$p_{y,\text{new}} = p_y - \Delta y_{\text{gap}} = p_y - (y_{\min} - y_{\text{ground}})$$

Post-condition guarantee:

$$y_{\min,\text{new}} \equiv y_{\text{ground}} \implies |\Delta y_{\text{gap}}| < 10^{-6}\,\text{m}$$

Contact state classification:
- **CONTACT:** $|\Delta y_{\text{gap}}| \le 0.005\,\text{m}$ (within $5\,\text{mm}$ threshold)
- **HOVERING:** $\Delta y_{\text{gap}} > 0.005\,\text{m}$
- **PENETRATING:** $\Delta y_{\text{gap}} < -0.005\,\text{m}$

---

## 3. 3D Stage Gizmo & Drag Projection

### 3.1 Handle Architecture
When `selected_object_id == "subject"`, the 3D stage generates interactive handles:
1. **Translation Arrows:** $X$ (red), $Y$ (green), $Z$ (blue).
2. **Rotation Rings:** Pitch (red ring), Yaw (green ring), **Roll (cyan ring)**.
3. **Scale Handles:** Uniform corner cube, Width/Height/Depth directional tabs.
4. **Ground Footprint Marker:** Projected yellow contact ring directly beneath the proxy.

### 3.2 Near-Parallel Singularity Protection
When an axis $\mathbf{a}_{\text{world}}$ is projected into screen coordinates, the projected direction vector is:

$$\mathbf{v}_{\text{screen}} = \text{project}(\mathbf{p} + \mathbf{a}) - \text{project}(\mathbf{p})$$

If the camera line-of-sight is nearly parallel to the axis ($\|\mathbf{v}_{\text{screen}}\| < 4.0\,\text{pixels}$), a direct projection division results in extreme numerical instability and erratic object jumping.

Relight Studio detects this singularity condition:
```python
axis_screen_len = np.linalg.norm(v_screen)
if axis_screen_len < 4.0:
    # Safe fallback: project along perpendicular viewport plane
    factor = 0.01 * (delta_screen_x - delta_screen_y)
    pos[axis_idx] += factor
```
This guarantees stable, continuous manipulation regardless of orbit camera angle.

---

## 4. Visual Evidence & Screenshots

- **Full XYZ Gizmo with Roll Ring:** `docs/RS-PRODUCT-1.2/screenshots/10_subject_proxy_3d_gizmo_pitch_yaw_roll.png`
- **Snap to Ground Contact:** `docs/RS-PRODUCT-1.2/screenshots/11_subject_snap_to_ground_contact.png`
- **Wireframe Over Photograph:** `docs/RS-PRODUCT-1.2/screenshots/06_photograph_wireframe_overlay.png`
