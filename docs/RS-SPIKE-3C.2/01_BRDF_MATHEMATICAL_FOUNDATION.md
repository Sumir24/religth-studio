# RS-SPIKE-3C.2 — BRDF Mathematical Foundation
## Cook-Torrance Microfacet BRDF Formulation & Numerical Safeguards

**Document ID:** RS-SPIKE-3C.2-01  
**Milestone:** RS-SPIKE-3C.2  
**Author:** Principal Physically Based Rendering Engineer & Applied Mathematician  
**Source Implementation:** `studio3a/brdf.py`  
**Test Suite:** `tests/RS-SPIKE-3C.2/test_brdf_foundation.py`  
**Status:** VALIDATED (Reciprocity Verified, Safeguards Tested, 100% Pass)

---

## 1. Executive Summary

This report establishes the physical and mathematical foundation of the specular reflection system introduced in **RS-SPIKE-3C.2**. 

To transition from pure Lambertian diffuse relighting to a material-aware rendering pipeline, we formulate and implement the standard Cook-Torrance microfacet reflectance model. Every component—the GGX Normal Distribution Function (NDF), the Schlick Fresnel approximation, and the Heitz height-correlated Smith geometric visibility term—is mathematically derived, verified for Helmholtz reciprocity, and protected with explicit numerical safeguards.

---

## 2. Theoretical Formulation

The total bidirectional reflectance distribution function (BRDF) decomposes into diffuse and specular components:
$$f_r(\mathbf{l}, \mathbf{v}) = f_{\text{diffuse}}(\mathbf{l}, \mathbf{v}) + f_{\text{specular}}(\mathbf{l}, \mathbf{v})$$

### 2.1 The Cook-Torrance Specular Model
The microfacet specular model describes reflection from a statistical distribution of microscopic, optically smooth specular facets:
$$f_{\text{specular}}(\mathbf{l}, \mathbf{v}) = \frac{D(\mathbf{h}, \alpha) \cdot F(\mathbf{v}, \mathbf{h}, F_0) \cdot G(\mathbf{l}, \mathbf{v}, \mathbf{h}, \alpha)}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})}$$

Where:
- $\mathbf{n} \in \mathbb{R}^3$: Unit macroscopic surface normal.
- $\mathbf{l} \in \mathbb{R}^3$: Unit vector from surface point to light source.
- $\mathbf{v} \in \mathbb{R}^3$: Unit vector from surface point to camera/viewer.
- $\mathbf{h} = \frac{\mathbf{l} + \mathbf{v}}{\|\mathbf{l} + \mathbf{v}\|}$: Unit half-vector (microfacet normal for specular reflection).
- $D(\mathbf{h}, \alpha)$: Normal distribution function giving the differential area of microfacets oriented along $\mathbf{h}$.
- $F(\mathbf{v}, \mathbf{h}, F_0)$: Fresnel reflectance giving the fraction of light reflected per microfacet.
- $G(\mathbf{l}, \mathbf{v}, \mathbf{h}, \alpha)$: Geometric attenuation factor accounting for microfacet masking and shadowing.

---

### 2.2 Normal Distribution Function: GGX / Trowbridge-Reitz

We adopt the Trowbridge-Reitz / GGX distribution due to its realistic heavy-tailed highlight falloff:
$$D(\mathbf{h}, \alpha) = \frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}$$

**Roughness Reparameterization:**
Following Burley (2012), linear perceptual artist roughness $r \in [0, 1]$ maps quadratically to the physical microfacet slope $\alpha$:
$$\alpha = r^2$$
This ensures linear perceptual responsiveness when dragging roughness sliders in the studio workspace.

**Normal-Incidence Peak:**
When $\mathbf{h} = \mathbf{n}$ (microfacet aligned with macroscopic normal, $(\mathbf{n} \cdot \mathbf{h}) = 1$):
$$D(\mathbf{n}, \alpha) = \frac{\alpha^2}{\pi (\alpha^2)^2} = \frac{1}{\pi \alpha^2}$$
As $\alpha \to 0$ (perfect specular mirror), $D$ approaches a Dirac delta distribution $\delta(\mathbf{n} - \mathbf{h}) / \pi$.

---

### 2.3 Fresnel Reflectance: Schlick's Approximation

The fraction of radiant flux reflected at microfacet interfaces is governed by the Fresnel equations. For real-time and interactive rendering, Schlick's approximation provides sub-percent error relative to full electromagnetic boundary conditions:
$$F(\mathbf{v}, \mathbf{h}, F_0) = F_0 + (1 - F_0) (1 - (\mathbf{v} \cdot \mathbf{h}))^5$$

**Physical Boundary Conditions:**
1. **Normal Incidence ($(\mathbf{v} \cdot \mathbf{h}) = 1$):**
   $$F = F_0 + (1 - F_0)(0)^5 = F_0$$
   - Dielectrics (fabric, plastic, glass, ceramics): $F_0 \approx 0.04$ (reflects 4% at perpendicular angle).
   - Conductors (metals): $F_0 = \text{base albedo} \in [0.5, 1.0]$.
2. **Grazing Angles ($(\mathbf{v} \cdot \mathbf{h}) \to 0$):**
   $$F \to F_0 + (1 - F_0)(1)^5 = 1.0$$
   All non-absorptive materials achieve 100% specular reflectance at grazing angles.

---

### 2.4 Geometric Masking-Shadowing: Heitz Height-Correlated Smith

A major failure point of naive microfacet implementations is the division by $4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})$. At grazing angles, $(\mathbf{n} \cdot \mathbf{l}) \to 0$ or $(\mathbf{n} \cdot \mathbf{v}) \to 0$, causing numerical overflow and unnatural bright rim fringes.

We adopt the **Heitz (2014) height-correlated Smith visibility function**, which directly defines the combined visibility factor:
$$V(\mathbf{l}, \mathbf{v}, \alpha) = \frac{G(\mathbf{l}, \mathbf{v}, \mathbf{h}, \alpha)}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})} = \frac{0.5}{(\mathbf{n} \cdot \mathbf{v})\sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{l})^2} + (\mathbf{n} \cdot \mathbf{l})\sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{v})^2}}$$

This yields the simplified and numerically stable specular evaluation:
$$f_{\text{specular}}(\mathbf{l}, \mathbf{v}) = D(\mathbf{h}, \alpha) \cdot F(\mathbf{v}, \mathbf{h}, F_0) \cdot V(\mathbf{l}, \mathbf{v}, \alpha)$$

**Mathematical Advantages:**
1. **Exact Denominator Cancellation:** Eliminates the $4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})$ term completely.
2. **Physically Grounded Grazing Limit:** As $(\mathbf{n} \cdot \mathbf{l}) \to 0$, $V \to \frac{0.5}{(\mathbf{n} \cdot \mathbf{v}) \alpha}$, which finite and smooth.
3. **Height Correlation:** Accounts for the geometric fact that a microfacet visible to the light source is statistically more likely to be elevated and therefore visible to the observer.

---

## 3. Helmholtz Reciprocity

Helmholtz reciprocity requires that swapping the light direction $\mathbf{l}$ and the view direction $\mathbf{v}$ yields identical reflectance:
$$f_r(\mathbf{l}, \mathbf{v}) = f_r(\mathbf{v}, \mathbf{l})$$

**Proof:**
1. **Half-Vector Symmetry:**
   $$\mathbf{h}(\mathbf{l}, \mathbf{v}) = \frac{\mathbf{l} + \mathbf{v}}{\|\mathbf{l} + \mathbf{v}\|} = \frac{\mathbf{v} + \mathbf{l}}{\|\mathbf{v} + \mathbf{l}\|} = \mathbf{h}(\mathbf{v}, \mathbf{l})$$
   Therefore, $D(\mathbf{h}(\mathbf{l}, \mathbf{v})) = D(\mathbf{h}(\mathbf{v}, \mathbf{l}))$.
2. **Fresnel Symmetry:**
   $$\mathbf{v} \cdot \mathbf{h} = \mathbf{v} \cdot \frac{\mathbf{l} + \mathbf{v}}{\|\mathbf{l} + \mathbf{v}\|} = \frac{\mathbf{v} \cdot \mathbf{l} + 1}{\|\mathbf{l} + \mathbf{v}\|} = \mathbf{l} \cdot \frac{\mathbf{v} + \mathbf{l}}{\|\mathbf{l} + \mathbf{v}\|} = \mathbf{l} \cdot \mathbf{h}$$
   Therefore, $F(\mathbf{v}, \mathbf{h}) = F(\mathbf{l}, \mathbf{h})$.
3. **Visibility Symmetry:**
   $$V(\mathbf{l}, \mathbf{v}, \alpha) = \frac{0.5}{(\mathbf{n} \cdot \mathbf{v})\Lambda(\mathbf{l}) + (\mathbf{n} \cdot \mathbf{l})\Lambda(\mathbf{v})} = V(\mathbf{v}, \mathbf{l}, \alpha)$$
   The denominator is strictly commutative under $\mathbf{l} \leftrightarrow \mathbf{v}$.

Hence, $f_{\text{specular}}(\mathbf{l}, \mathbf{v}) \equiv f_{\text{specular}}(\mathbf{v}, \mathbf{l})$, satisfying reciprocity exactly. Automated unit test `test_helmholtz_reciprocity` verifies this across roughness values with relative tolerance $< 10^{-5}$.

---

## 4. Numerical Safeguards Specification

To eliminate NaN, Inf, and division-by-zero defects across both CPU and Metal GPU runtimes, every mathematical operation is bounded by documented safeguards:

| Constant / Guard | Value | Purpose & Physical Justification |
|---|:---:|---|
| `MIN_ROUGHNESS` | $0.04$ | Linear roughness floor. Corresponds to $\alpha_{\text{min}} = 0.04^2 = 0.0016$. Prevents Dirac delta singularity in $D$ where $1/(\pi \alpha^2) \to \infty$. |
| `MIN_ALPHA` | $0.0016$ | Direct floor for the squared roughness parameter $\alpha^2$. Prevents denominator underflow. |
| `EPSILON_DOT` | $10^{-5}$ | Minimum denominator floor in visibility and NDF denominators. Prevents division by zero at exact perpendicular grazing angles ($90^\circ$). |
| `EPSILON_LEN` | $10^{-7}$ | Vector normalization denominator floor. Prevents division by zero when normalizing $\mathbf{l} + \mathbf{v}$ when $\mathbf{l} \approx -\mathbf{v}$. |
| `clamp_dot(x)` | $[0.0, 1.0]$ | Clamps all directional dot products $(\mathbf{n} \cdot \mathbf{l}, \mathbf{n} \cdot \mathbf{v}, \mathbf{n} \cdot \mathbf{h}, \mathbf{v} \cdot \mathbf{h})$ to physically valid non-negative cosines. |
| `Horizon Cutoff` | $(\mathbf{n} \cdot \mathbf{l} \le 0) \lor (\mathbf{n} \cdot \mathbf{v} \le 0)$ | If light or camera lies below the surface horizon, $f_r$ is set to exactly $0.0$ to prevent negative radiance or light bleeding from underneath. |

---

## 5. Energy-Conserving Diffuse & Specular Partitioning

In physically based materials, energy conservation dictates that reflected diffuse energy plus reflected specular energy cannot exceed the incident energy:
$$k_d + k_s \le 1.0$$

Where $k_s = F(\mathbf{v}, \mathbf{h})$. Since light that is reflected specularly at the surface interface never penetrates into the bulk medium, diffuse reflection is scaled by the transmitted fraction $(1 - F)$:
$$f_{\text{diffuse}} = (1 - F) \cdot (1 - \text{metallic}) \cdot \frac{\text{base\_color}}{\pi}$$

**Conductor vs Dielectric Behavior:**
- **Dielectrics ($\text{metallic} = 0.0$):**
  $F_0 = 0.04$. At normal incidence, 4% of energy is reflected specularly; 96% is refracted and re-emitted as diffuse body color.
- **Conductors ($\text{metallic} = 1.0$):**
  Free conduction electrons reflect incident photons directly at the surface interface; light cannot penetrate the metal lattice. Thus $(1 - \text{metallic}) = 0$, yielding **zero diffuse reflection** ($f_{\text{diffuse}} = 0$). Specular reflectance is tinted by the metal's characteristic base color: $F_0 = \text{base\_color}$.

---

## 6. Verification Status

The mathematical foundation implemented in `studio3a/brdf.py` has been verified via unit tests in `tests/RS-SPIKE-3C.2/test_brdf_foundation.py`:
- `test_ggx_distribution_properties`: Peak and monotonic falloff validated.
- `test_fresnel_schlick_properties`: Normal incidence and grazing angle validated.
- `test_helmholtz_reciprocity`: Reciprocity confirmed across roughness sweeps.
- `test_backfacing_and_grazing_cutoff`: Zero bleeding below horizon confirmed.
- `test_roughness_clamping_and_non_negativity`: 0 NaNs / 0 Infs confirmed.
- `test_energy_conserving_diffuse_specular_split`: Dielectric vs metallic split confirmed.

Phase 1 is complete. Authorized to proceed to **Phase 2: Material Model & Scene Architecture**.
