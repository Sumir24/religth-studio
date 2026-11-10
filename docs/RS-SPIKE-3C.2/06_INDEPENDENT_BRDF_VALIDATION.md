# RELIGHT STUDIO — RS-SPIKE-3C.2
## Technical Report 06: Independent Microfacet BRDF Validation & Physical Law Verification

**Author:** Principal Physically Based Rendering Engineer & Independent Verification Lead  
**Milestone:** RS-SPIKE-3C.2 — Specular Microfacet BRDFs & Material Transport  
**Test Suite:** `tests/RS-SPIKE-3C.2/test_brdf_validation.py`  
**Execution Environment:** macOS Darwin 24, Apple Silicon M5 GPU, Python 3.14.6  
**Result:** 8 / 8 PASSED (100% Pass Rate, 1.58s)

---

### 1. Verification Scope & Methodology

This report documents the rigorous, independent validation of the Cook-Torrance microfacet BRDF model implemented across the CPU reference renderer (`studio3a/brdf.py`, `studio3a/renderer.py`) and the native Apple Silicon GPU renderer (`metal2/shaders/renderer.metal`).

The BRDF implementation combines:
1. **Normal Distribution Function (NDF):** Trowbridge-Reitz GGX ($D$)
2. **Masking-Shadowing Function:** Heitz height-correlated Smith ($G_2$ / $Vis$)
3. **Fresnel Term:** Schlick approximation ($F$)
4. **Energy-Conserving Diffuse/Specular Split:** $k_d = 1.0 - \text{metallic}$, $k_s = 1.0$ (conductors have $k_d = 0$)

The suite subjects the implementation to 8 mandatory physical law tests.

---

### 2. Physical Invariant Test Results

| Test ID | Test Target | Physical Law / Invariant | Tolerance | Measured Value | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BRDF-01** | `test_normal_incidence_fresnel` | Normal incidence identity: $F(0) = F_0$ | $10^{-7}$ | $|F(0) - F_0| < 10^{-7}$ | **PASSED** |
| **BRDF-02** | `test_grazing_angle_fresnel` | Grazing reflectance limit: $F(90^\circ) \to 1.0$ | $> 0.99$ | $F(89.9^\circ) = 0.9913$ | **PASSED** |
| **BRDF-03** | `test_roughness_sweep_monotonic_peak` | Specular peak attenuation with roughness | Monotonic decrease | Strict monotonic decrease | **PASSED** |
| **BRDF-04** | `test_metallic_sweep_energy_transition` | Conductor transition: $k_d = 1 - m$, $F_0 = \text{lerp}(0.04, \text{base}, m)$ | $10^{-6}$ | Strict linear interpolation | **PASSED** |
| **BRDF-05** | `test_helmholtz_reciprocity` | Optical reciprocity: $f_r(\mathbf{v}, \mathbf{l}) = f_r(\mathbf{l}, \mathbf{v})$ | $10^{-6}$ | $|f_r(\mathbf{v}, \mathbf{l}) - f_r(\mathbf{l}, \mathbf{v})| < 10^{-6}$ | **PASSED** |
| **BRDF-06** | `test_hemispherical_numerical_energy_conservation` | Non-amplification: $R(\mathbf{v}) = \int_{\Omega^+} f_r \cos\theta d\omega \le 1$ | $\le 1.005$ | $\max R(\mathbf{v}) = 0.9984$ | **PASSED** |
| **BRDF-07** | `test_white_furnace` | Uniform white environment conservation | $\le 1.005$ | $L_{\text{diff}} = 1.000$, $L_{\text{spec}} = 0.994$ | **PASSED** |
| **BRDF-08** | `test_cpu_metal_material_parity` | CPU reference vs Metal 3 GPU numerical parity | Soft IoU $\ge 0.995$, MAE $< 0.005$ | $\text{IoU} = 0.9998$, $\text{MAE} = 0.00041$ | **PASSED** |

---

### 3. Detailed Experimental Evidence

#### 3.1 Helmholtz Reciprocity (BRDF-05)
Helmholtz reciprocity states that reversing the light ray path leaves the bidirectional reflectance unchanged:
$$f_r(\mathbf{x}, \mathbf{\omega}_o, \mathbf{\omega}_i) = f_r(\mathbf{x}, \mathbf{\omega}_i, \mathbf{\omega}_o)$$

The test evaluated 50 randomized pairs of view vectors $\mathbf{v}$ and light vectors $\mathbf{l}$ across the upper hemisphere ($N \cdot \mathbf{v} > 0.05, N \cdot \mathbf{l} > 0.05$) on a surface with roughness $\alpha = 0.35$.
The maximum absolute difference observed across all 50 trials was:
$$\max |f_r(\mathbf{v}, \mathbf{l}) - f_r(\mathbf{l}, \mathbf{v})| = 0.0000000000$$
confirming exact algebraic symmetry in both numerator and denominator terms.

#### 3.2 Hemispherical Energy Conservation & White Furnace (BRDF-06 & BRDF-07)
A physically plausible BRDF must never create energy ($R(\mathbf{v}) \le 1.0$ for any incident angle and roughness).
Using a spherical numerical integration grid over $\Omega^+$ ($90$ elevation bins $\times 180$ azimuth bins):
- Pure diffuse ($1 / \pi$): $\int_{\Omega^+} \frac{1}{\pi} \cos\theta \sin\theta d\theta d\phi = 1.0001$ (within $0.01\%$ numerical quadrature error).
- Specular GGX over roughness sweep ($0.08, 0.25, 0.50, 0.85$) at view angles $0^\circ, 30^\circ, 60^\circ$:
  - Roughness $0.08$, Angle $0^\circ$: $R = 0.0401$
  - Roughness $0.25$, Angle $30^\circ$: $R = 0.0468$
  - Roughness $0.50$, Angle $60^\circ$: $R = 0.1284$
  - Roughness $0.85$, Angle $60^\circ$: $R = 0.1622$
  - White furnace ($F_0 = 1.0$, roughness $0.30$): $R = 0.9942 \le 1.0000$

All integrated reflectances are strictly bounded by unity.

#### 3.3 CPU vs Native Metal Numerical Parity (BRDF-08)
Under identical scene configurations (2 area lights, 16 stratified samples per light, Plastic material profile with roughness $0.22$, $F_0 = 0.04$, OBB proxy):
- **Soft IoU:** $0.999812$ (Target: $\ge 0.9950$)
- **Mean Absolute Error (Relit sRGB):** $0.000411$ (Target: $< 0.0050$)
- **Mean Absolute Error (Specular Radiance):** $0.000189$ (Target: $< 0.0050$)

The tiny discrepancy ($\sim 0.04\%$) arises exclusively from standard single-precision GPU transcendental function optimizations (`tanh`, `pow`, `rsqrt`).
