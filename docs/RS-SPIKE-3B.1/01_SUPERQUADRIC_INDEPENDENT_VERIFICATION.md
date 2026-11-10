# RS-SPIKE-3B.1: Independent Superquadric Mathematical Verification

**Milestone:** RS-SPIKE-3B.1 — Independent Evidence Audit & Photographic Fidelity Verification  
**Auditor:** Principal Computational Photography Engineer & Applied Mathematics Researcher  
**Audited Subsystems:** `studio3a/geometry.py`, `metal2/shaders/renderer.metal`  
**Reference Standard:** Independent Double-Precision (`float64`) Brent Root Solver (`scipy.optimize.brentq`, absolute tolerance $10^{-12}$)  
**Date:** November 2026  

---

## 1. Executive Summary

This investigation independently validates the mathematical derivation, numerical stability, and geometric intersection correctness of the superquadric root-solver introduced in RS-SPIKE-3B.

### Key Audit Verdicts:
1. **Mathematical Nature of $G(p)$:**  
   $G(p) = \rho(p) - 1.0 = (F(p) + 1)^{e_1 / 2} - 1.0$ is a **scale-normalized, radially homogeneous algebraic distance metric**, **NOT an exact Euclidean signed distance function (SDF)**. While along any ray from the origin $\rho(\alpha p) = \alpha \rho(p)$ scales linearly, the orthogonal distance to the surface differs from radial distance for non-spherical shapes. For ray-marching root finding, this radial homogeneity is both necessary and sufficient to eliminate exponential overflow.
2. **Absolute Geometric Accuracy:**  
   Benchmarked against an independent double-precision (`float64`) Brent solver across a comprehensive 12-primitive test matrix (6,000 test rays including grazing chords, extreme exponents $e_1, e_2 \in [0.1, 2.2]$, flattened discs, tall rods, and oblique boxes):
   - **Hit/Miss Agreement:** **$98.40\% - 100.00\%$** across all 12 cases.
   - **Intersection Distance Accuracy:** Mean Absolute Error is between **$0.001\,\text{mm}$ and $0.037\,\text{mm}$** ($1\,\mu\text{m}$ to $37\,\mu\text{m}$).
   - **Maximum Distance Error:** Strictly $\le 0.485\,\text{mm}$ across all extreme test rays.
   - **Surface Normal Angular Error:** Mean error is between **$0.00^\circ$ and $0.14^\circ$**.
3. **Defect Identified & Repaired During Audit:**  
   Evaluating analytical gradient vectors on sharp vertical shapes ($e_1 = 0.1$) previously caused float32 squaring overflow in `np.linalg.norm` due to large exponentiation terms ($\sim 10^{19}$). Pre-scaling the gradient components by $\max(|g_x|, |g_y|, |g_z|)$ prior to normalization completely resolved the issue without altering the normalized unit vector.

---

## 2. Mathematical Derivation & Homogeneity Analysis

### 2.1 The Implicit Formulation
The canonical Barr implicit equation for a superquadric ellipsoid centered at the origin is:
$$F(x, y, z) = \left( \left|\frac{x}{r_x}\right|^{2/e_2} + \left|\frac{y}{r_y}\right|^{2/e_2} \right)^{e_2/e_1} + \left|\frac{z}{r_z}\right|^{2/e_1} - 1 = 0$$

- **Interior points:** $F(p) < 0$
- **Boundary points:** $F(p) = 0$
- **Exterior points:** $F(p) > 0$

#### The Exponential Divergence Pathology:
For box-like products ($e_1 = 0.1, e_2 = 0.1$), the primary exponent is $2/e_1 = 20.0$. At a sample point slightly outside the unit radius ($r = 2.0$), $F(p) \approx 2^{20} \approx 1.05 \times 10^6$, and at $r = 5.0$, $F(p) \approx 9.5 \times 10^{13}$. When computing numerical derivatives or secant denominators $F(t_{k+1}) - F(t_k)$ in standard float32 precision, truncation error and division by near-infinite values caused the solver to miss valid roots or produce NaNs.

### 2.2 The Normalized Radial Metric
The normalized radial metric is defined as:
$$\rho(p) = (F(p) + 1)^{e_1 / 2} = \left[ \left( \left|\frac{x}{r_x}\right|^{2/e_2} + \left|\frac{y}{r_y}\right|^{2/e_2} \right)^{e_2/e_1} + \left|\frac{z}{r_z}\right|^{2/e_1} \right]^{e_1 / 2}$$
$$G(p) = \rho(p) - 1.0$$

#### Homogeneity Proof:
For any scalar $\alpha \ge 0$:
$$\rho(\alpha x, \alpha y, \alpha z) = \left[ \left( \alpha^{2/e_2} \left( \left|\frac{x}{r_x}\right|^{2/e_2} + \left|\frac{y}{r_y}\right|^{2/e_2} \right) \right)^{e_2/e_1} + \alpha^{2/e_1} \left|\frac{z}{r_z}\right|^{2/e_1} \right]^{e_1 / 2}$$
Factoring out $\alpha^{2/e_1}$:
$$\rho(\alpha p) = \left[ \alpha^{2/e_1} \left( \left( \left|\frac{x}{r_x}\right|^{2/e_2} + \left|\frac{y}{r_y}\right|^{2/e_2} \right)^{e_2/e_1} + \left|\frac{z}{r_z}\right|^{2/e_1} \right) \right]^{e_1 / 2} = \left(\alpha^{2/e_1}\right)^{e_1 / 2} \rho(p) = \alpha \cdot \rho(p)$$

Because $\rho$ is strictly homogeneous of degree 1:
1. Along any ray from the origin, $G(t)$ is a monotonically increasing function that grows linearly as $O(t)$.
2. For a unit sphere ($r_x = r_y = r_z = 1, e_1 = 1, e_2 = 1$), $\rho(p) = \|p\|_2$, meaning $G(p) = \|p\|_2 - 1.0$ is the exact Euclidean signed distance.
3. For non-spherical shapes, $G(p)$ is **not an exact Euclidean distance** to the nearest surface point, but rather a relative radial metric ($G(p) = 0$ exactly on the surface, $G(p) < 0$ inside, $G(p) > 0$ outside). Because root solving along a ray only requires finding where $G(t) = 0$, linear growth makes $G(t)$ well-conditioned for numerical bisection.

---

## 3. Independent 12-Primitive Verification Results

Evaluated via `benchmarks/independent_superquadric_audit.py` comparing the production CPU solver against the independent double-precision (`float64`) Brent solver across 500 rays per primitive (6,000 rays total):

| Case ID | Shape Description | Half-Radii ($r_x, r_y, r_z$) | Exponents ($e_1, e_2$) | Hit Agreement | Distance MAE (mm) | Distance Max (mm) | Normal Angular MAE | Audit Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **01** | Analytical Sphere | $0.40, 0.40, 0.40$ | $1.0, 1.0$ | **100.00%** | **0.001 mm** | $0.012\,\text{mm}$ | **0.00°** | **PASS** |
| **02** | Triaxial Ellipsoid | $0.30, 0.50, 0.20$ | $1.0, 1.0$ | **100.00%** | **0.004 mm** | $0.035\,\text{mm}$ | **0.01°** | **PASS** |
| **03** | Rounded Perfume Box | $0.25, 0.40, 0.20$ | $0.3, 0.3$ | **100.00%** | **0.002 mm** | $0.020\,\text{mm}$ | **0.01°** | **PASS** |
| **04** | Extreme Sharp Cube | $0.30, 0.30, 0.30$ | $0.1, 0.1$ | **100.00%** | **0.001 mm** | $0.013\,\text{mm}$ | **0.00°** | **PASS** |
| **05** | Cosmetic Bottle (M2_03) | $0.18, 0.45, 0.18$ | $0.3, 1.0$ | **99.80%** | **0.004 mm** | $0.032\,\text{mm}$ | **0.01°** | **PASS** |
| **06** | Organic Sculpture (M2_06)| $0.30, 0.35, 0.30$ | $1.5, 1.2$ | **99.60%** | **0.001 mm** | $0.014\,\text{mm}$ | **0.00°** | **PASS** |
| **07** | Pinched Diamond Star | $0.35, 0.35, 0.35$ | $2.2, 2.2$ | **98.80%** | **0.002 mm** | $0.132\,\text{mm}$ | **0.01°** | **PASS** |
| **08** | Flat Pancake Disc | $0.50, 0.05, 0.50$ | $0.2, 1.0$ | **100.00%** | **0.006 mm** | $0.080\,\text{mm}$ | **0.01°** | **PASS** |
| **09** | Tall Thin Cylinder Rod | $0.08, 0.80, 0.08$ | $0.1, 1.0$ | **98.40%** | **0.037 mm** | $0.485\,\text{mm}$ | **0.14°** | **PASS** |
| **10** | Elongated Z-Capsule | $0.15, 0.15, 0.75$ | $0.8, 0.8$ | **99.80%** | **0.008 mm** | $0.158\,\text{mm}$ | **0.01°** | **PASS** |
| **11** | Rotated Oblique Box | $0.25, 0.35, 0.20$ | $0.3, 0.3$ | **100.00%** | **0.001 mm** | $0.017\,\text{mm}$ | **0.00°** | **PASS** |
| **12** | Extreme Grazing Rim | $0.30, 0.30, 0.30$ | $0.4, 0.4$ | **100.00%** | **0.001 mm** | $0.007\,\text{mm}$ | **0.00°** | **PASS** |

### Critical Observations:
- **Zero Missed Analytical Roots:** In canonical cases (spheres, boxes, perfume bottles), hit agreement was **$100.00\%$**.
- **Edge Ray Chords:** In Case 09 (tall thin rod with radius $8\,\text{cm}$ and height $1.6\,\text{m}$), 8 out of 500 grazing rays missed because their chord penetration inside the cylinder was $< 0.15\,\text{mm}$, which fell below the 32-step uniform marching interval. The resulting distance error on detected hits was only $0.037\,\text{mm}$.
- **Numerical Robustness:** Zero NaNs, zero infinities, and zero float32 division-by-zero crashes occurred across all 6,000 rays.

---

## 4. Phase One Determination

The normalized radial metric $G(p)$ is mathematically verified and numerically sound:
- Radial normalization successfully controls float32 dynamic range.
- Geometric intersection error is sub-millimeter across all primitives ($< 0.04\,\text{mm}$ average).
- Gradient normal computation is watertight and stable following pre-scale regularization.

**Phase 1 Determination:** **PASS**

