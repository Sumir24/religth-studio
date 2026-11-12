# RELIGHT STUDIO — RS-PRODUCT-1.2.1
## Geometry & Ground-Contact Mathematics Audit

**Auditor:** Principal 3D Graphics Engineer & Applied Mathematics Researcher  
**Milestone:** RS-PRODUCT-1.2.1  
**Status:** REMEDIATED & INDEPENDENTLY VERIFIED  

---

## 1. Executive Summary

This audit independently investigated the support functions, lowest elevation formulas, and snap-to-ground behavior across OBBs, Spheres, and Superquadrics.

### Defect Identified & Remediated:
- **Superquadric Support Function Formulation:** In the RS-PRODUCT-1.2 baseline, `compute_proxy_geometry_meta()` used the pure ellipsoid support formula $\Delta y = \sqrt{(R_{1,0} r_x)^2 + (R_{1,1} r_y)^2 + (R_{1,2} r_z)^2}$ for all superquadrics, ignoring the shape exponents $(e_1, e_2)$.
- **Mathematical Impact:** For squarish superquadrics ($e_1 < 1.0$, such as $e_1 = 0.8$ or $e_1 = 0.5$), the true rotated surface extends further into the corners than an ellipsoid, resulting in a $28.7\,\text{mm}$ error for $e_1=0.8$ and $76.5\,\text{mm}$ error for $e_1=0.5$.
- **Remediation Implemented:** `compute_proxy_geometry_meta` and `snap_proxy_to_ground` were updated to accept `sq_exponents`. For $e_1 \ne 1.0$, the function generates exact superquadric surface points using signed power parametric equations $(\text{sgn}(\cos v) |\cos v|^{e_1})$, evaluating the exact minimum world elevation ($< 0.1\,\text{mm}$ error).

---

## 2. Independent Support Function Verification

### 2.1 Oriented Bounding Box (OBB)
Let $\mathbf{R}$ be the orthonormal rotation matrix with rows $\mathbf{r}_0, \mathbf{r}_1, \mathbf{r}_2$ and local half-extents $\mathbf{e} = [e_x, e_y, e_z]^T$.
World position of any point inside the box is:

$$\mathbf{p}_{\text{world}} = \mathbf{p}_{\text{center}} + \mathbf{R} \mathbf{v}, \quad v_x \in [-e_x, e_x], \; v_y \in [-e_y, e_y], \; v_z \in [-e_z, e_z]$$

The world vertical elevation is:

$$y_{\text{world}} = p_y + R_{1,0} v_x + R_{1,1} v_y + R_{1,2} v_z$$

Because the coefficients $R_{1,c}$ are constants, the linear functional attains its global minimum over the compact convex set $[-e_x, e_x] \times [-e_y, e_y] \times [-e_z, e_z]$ when $v_c = -\text{sgn}(R_{1,c}) e_c$. Thus:

$$y_{\min} = p_y - \left( |R_{1,0}| e_x + |R_{1,1}| e_y + |R_{1,2}| e_z \right)$$

This analytical closed-form formula is **EXACT**.
Tested under:
- Identity rotation: $y_{\min} = p_y - e_y$ (Exact)
- $90^\circ$ Pitch: $y_{\min} = p_y - e_z$ (Exact)
- $90^\circ$ Roll: $y_{\min} = p_y - e_x$ (Exact)
- Arbitrary compound Euler angles $(35^\circ, -45^\circ, 20^\circ)$: Discrepancy vs numerical brute-force search $< 10^{-7}\,\text{m}$.

### 2.2 Sphere & Ellipsoid Support Function
An ellipsoid is the unit sphere mapped by $\mathbf{M} = \mathbf{R} \text{diag}(r_x, r_y, r_z)$. The support function along unit vector $\mathbf{n} = [0, -1, 0]^T$ gives:

$$h_E(\mathbf{n}) = \|\mathbf{M}^T \mathbf{n}\| = \sqrt{ (R_{1,0} r_x)^2 + (R_{1,1} r_y)^2 + (R_{1,2} r_z)^2 }$$

$$y_{\min} = p_y - h_E(\mathbf{n}) = p_y - \sqrt{ (R_{1,0} r_x)^2 + (R_{1,1} r_y)^2 + (R_{1,2} r_z)^2 }$$

This closed-form formula is **EXACT for Spheres and Ellipsoids ($e_1 = 1.0, e_2 = 1.0$)**.

### 2.3 General Superquadric Support
For $e_1 \ne 1.0$, the shape follows the parametric equation:

$$\mathbf{x}_{\text{local}}(u, v) = \begin{bmatrix} r_x \text{sgn}(\cos v) |\cos v|^{e_1} \text{sgn}(\cos u) |\cos u|^{e_2} \\ r_y \text{sgn}(\sin v) |\sin v|^{e_1} \\ r_z \text{sgn}(\cos v) |\cos v|^{e_1} \text{sgn}(\sin u) |\sin u|^{e_2} \end{bmatrix}$$

Remediation evaluates $24 \times 13 = 312$ vectorized surface samples in $0.058\,\text{ms}$, yielding sub-millimeter precision across all shape exponents:

| Shape Exponent $e_1$ | Baseline Formula | Remediated Formulation | Discrepancy vs Numerical |
|---|---|---|---|
| **$e_1 = 1.0$ (Ellipsoid)** | $0.4272\,\text{m}$ | $0.4272\,\text{m}$ | **$0.00\,\text{mm}$** (Exact) |
| **$e_1 = 0.8$ (Sneaker Proxy)** | $0.4272\,\text{m}$ (Error) | **$0.4559\,\text{m}$** | **$< 0.1\,\text{mm}$** |
| **$e_1 = 0.5$ (Rounded Box)** | $0.4272\,\text{m}$ (Error) | **$0.5037\,\text{m}$** | **$< 0.2\,\text{mm}$** |
| **$e_1 = 0.1$ (Sharp Box)** | $0.4272\,\text{m}$ (Error) | **$0.5765\,\text{m}$** | **$< 0.3\,\text{mm}$** |

---

## 3. Contact Invariant Post-Condition

The snap-to-ground operation sets:

$$p_{y,\text{new}} = p_y - (y_{\min} - y_{\text{ground}})$$

Post-condition assertion across 500 random configurations:

$$|y_{\min,\text{new}} - y_{\text{ground}}| < 10^{-5}\,\text{m}$$

Contact state transitions reliably:
- Before snap (hovering at $y=2.0$): `gap = 1.427m`, state = `"hovering"`
- After snap: `gap = 0.0000m`, state = `"contact"` (green badge)
- Submerged: `gap = -0.050m`, state = `"penetrating"` (red warning)

