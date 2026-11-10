# RELIGHT STUDIO — RS-SPIKE-3C.2.1
## Independent Evidence Audit Report 01: BRDF Mathematical Verification & Numerical Safeguards

**Author:** Independent Principal Rendering Engineer, Physically Based Rendering Researcher & Adversarial Verification Lead  
**Milestone:** RS-SPIKE-3C.2.1 — Independent BRDF, Material Transport & Photographic Fidelity Audit  
**Audited Code:** `studio3a/brdf.py`, `metal2/shaders/renderer.metal`  
**Independent Reference:** `benchmarks/audit_3c21/independent_brdf_reference.py`  
**Test Harness:** `benchmarks/audit_3c21/audit_brdf_mathematics.py`  
**Target Gates:** G01 (GGX NDF), G02 (Fresnel & Smith Geometry), G03 (Helmholtz Reciprocity)

---

### 1. Executive Summary & Audit Verdict

This report provides an independent adversarial audit of the Cook–Torrance microfacet BRDF implemented in `studio3a/brdf.py` and native Metal 3 GPU shaders in `metal2/shaders/renderer.metal`.

All equations were evaluated against an independently formulated float64 mathematical reference (`IndependentBRDFReference`) derived directly from academic literature (Trowbridge & Reitz 1975, Walter et al. 2007, Heitz 2014, Schlick 1994, Burley 2012).

#### Audit Scorecard for Gates G01–G03:
- **Gate G01 (GGX BRDF Mathematical Validation):** **CONDITIONAL PASS**
  - **Confirmed:** Trowbridge-Reitz GGX NDF correctly normalizes across the hemisphere; Burley parameterization $\alpha = \text{roughness}^2$ matches standard Disney/Filament conventions.
  - **CRITICAL DEFECT DETECTED:** A numerical conflict between `MIN_ROUGHNESS = 0.04` ($\alpha_{\text{min}}^2 = 2.56 \times 10^{-6}$) and `EPSILON_DOT = 1e-5` ($10^{-5}$) causes the peak GGX NDF to **collapse and invert non-monotonically** for roughnesses below $r \approx 0.0562$. As roughness decreases from $0.0562$ to $0.04$, the on-axis specular mirror peak collapses from $317.54$ down to $81.49$ (a $74.3\%$ drop). The RS-SPIKE-3C.2 test suite avoided detecting this bug by restricting its test array to $[0.05, 1.00]$.
- **Gate G02 (Fresnel & Geometry Term Validation):** **PASS**
  - Schlick Fresnel satisfies $F(0^\circ) = F_0$ and $F(90^\circ) = 1.000000$ to $< 10^{-7}$.
  - Heitz height-correlated Smith visibility function satisfies normal incidence identity $V(1, 1) = 0.250000$ to $< 10^{-7}$.
- **Gate G03 (Helmholtz Optical Reciprocity):** **PASS**
  - Across 1,000 randomized directional pairs, $\max |f_s(\mathbf{l}, \mathbf{v}) - f_s(\mathbf{v}, \mathbf{l})| = 7.37 \times 10^{-7} < 10^{-6}$.

---

### 2. Independent Mathematical Formulations & Reference Parity

#### 2.1 Canonical Specular Formulation
The Cook–Torrance microfacet model represents specular reflection as:
$$f_s(\mathbf{l}, \mathbf{v}) = D(\mathbf{h}, \alpha) \cdot F(\mathbf{v}, \mathbf{h}, F_0) \cdot V(\mathbf{l}, \mathbf{v}, \alpha)$$

Where:
1. **Half-Vector:**
   $$\mathbf{h} = \frac{\mathbf{l} + \mathbf{v}}{\|\mathbf{l} + \mathbf{v}\|}$$
2. **Trowbridge-Reitz GGX NDF:**
   $$D(\mathbf{h}, \alpha) = \frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}$$
3. **Schlick Fresnel:**
   $$F(\mathbf{v}, \mathbf{h}, F_0) = F_0 + (1 - F_0) (1 - \mathbf{v} \cdot \mathbf{h})^5$$
4. **Heitz Height-Correlated Smith Visibility:**
   $$V(\mathbf{l}, \mathbf{v}, \alpha) = \frac{G_2(\mathbf{l}, \mathbf{v}, \alpha)}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})} = \frac{0.5}{(\mathbf{n} \cdot \mathbf{v}) \Lambda_l + (\mathbf{n} \cdot \mathbf{l}) \Lambda_v}$$
   where $\Lambda_x = \sqrt{(\mathbf{n} \cdot \mathbf{x})^2 (1 - \alpha^2) + \alpha^2}$.

#### 2.2 Numerical Identity Checks

| Term & Invariant | Expected Analytical Value | Production Code (`studio3a/brdf.py`) | Discrepancy | Status |
| :--- | :--- | :--- | :--- | :---: |
| **Normal Fresnel $F(0^\circ)$** | $F_0 = 0.040000$ | $0.040000$ | $0.0 \times 10^{-7}$ | **PASS** |
| **Grazing Fresnel $F(90^\circ)$** | $1.000000$ | $1.000000$ | $0.0 \times 10^{-7}$ | **PASS** |
| **Normal Visibility $V(1, 1)$** | $0.250000$ | $0.250000$ | $0.0 \times 10^{-7}$ | **PASS** |
| **Horizon Cutoff ($N \cdot L \le 0$)** | $0.000000$ | $0.000000$ | $0.0 \times 10^{-7}$ | **PASS** |
| **Horizon Cutoff ($N \cdot V \le 0$)** | $0.000000$ | $0.000000$ | $0.0 \times 10^{-7}$ | **PASS** |
| **Degenerate Half-Vector ($V = -L$)** | $0.000000$ | $0.000000$ | $0.0 \times 10^{-7}$ | **PASS** |
| **Upper Hemisphere Monte Carlo ($r \ge 0.06$)** | $10,000$ ray pairs | $\text{MRE} = 2.47 \times 10^{-4}$ | $< 1.0 \times 10^{-3}$ | **PASS** |

---

### 3. Critical Adversarial Finding: GGX Denominator Clamping Inversion

#### 3.1 The Flaw: Safeguard Mismatch
In `studio3a/brdf.py` and `metal2/shaders/renderer.metal`, the author declared:
```python
MIN_ROUGHNESS: float = 0.04      # alpha_min = 0.04^2 = 0.0016 prevents singular delta spike
MIN_ALPHA: float = 0.0016        # Direct alpha floor
EPSILON_DOT: float = 1e-5        # Prevents division by zero in grazing angles
```
In `distribution_ggx`:
```python
def distribution_ggx(n_dot_h: np.ndarray, alpha: float) -> np.ndarray:
    a2 = max(alpha * alpha, MIN_ALPHA * MIN_ALPHA)
    nh = clamp_dot(n_dot_h)
    denom = (nh * nh * (a2 - 1.0) + 1.0)
    denom = np.maximum(denom, EPSILON_DOT)
    return a2 / (np.pi * denom * denom)
```
And in Metal shader `metal2/shaders/renderer.metal` (lines 73–79):
```metal
inline float distribution_ggx(float n_dot_h, float alpha) {
    float a2 = max(alpha * alpha, 0.0016f * 0.0016f);
    float nh = clamp(n_dot_h, 0.0f, 1.0f);
    float denom = nh * nh * (a2 - 1.0f) + 1.0f;
    denom = max(denom, 1e-5f);
    return a2 / (3.141592653589793f * denom * denom);
}
```

#### 3.2 Mathematical Proof of Non-Monotonic Collapse
At on-axis normal incidence ($\mathbf{n} \cdot \mathbf{h} = 1.0$):
$$\text{denom} = 1.0 \cdot (a^2 - 1.0) + 1.0 = a^2 = \alpha^2$$

For roughness $r = 0.04$, $\alpha = r^2 = 0.0016$, so:
$$\alpha^2 = (0.0016)^2 = 2.56 \times 10^{-6}$$

Because $2.56 \times 10^{-6} < 10^{-5}$ (`EPSILON_DOT`), the denominator is clamped:
$$\text{denom}_{\text{clamped}} = 10^{-5}$$

This alters the analytical peak formula from:
$$D_{\text{true}} = \frac{a^2}{\pi \cdot (a^2)^2} = \frac{1}{\pi a^2} = \frac{1}{\pi \times 2.56 \times 10^{-6}} \approx 124,339.8$$
to:
$$D_{\text{clamped}} = \frac{a^2}{\pi \cdot (\text{denom}_{\text{clamped}})^2} = \frac{\alpha^2}{\pi \times 10^{-10}} \approx \frac{2.56 \times 10^{-6}}{\pi \times 10^{-10}} = \frac{25,600}{\pi} \approx 8,148.73$$

The threshold roughness where $\alpha^2 = 10^{-5}$ is:
$$r_{\text{crit}} = (10^{-5})^{1/4} \approx 0.05623$$

For all $r < 0.05623$, $D_{\text{peak}} \propto \alpha^2$ **increases as roughness increases**, which directly contradicts the physical definition of a microfacet NDF!

#### 3.3 Empirical Measurements Across the Transition

| Roughness $r$ | Parameter $\alpha = r^2$ | True Peak $D$ | Measured Production Peak $D$ | Specular Peak $f_s$ ($F_0=0.04$) | Monotonicity |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **$0.0400$** | $0.001600$ | $124,339.80$ | **$8,148.73$** | **$81.49$** | **INVERTED** |
| **$0.0450$** | $0.002025$ | $77,624.96$ | **$13,052.79$** | **$130.53$** | Inverted |
| **$0.0500$** | $0.002500$ | $50,929.58$ | **$19,894.37$** | **$198.94$** | Inverted |
| **$0.0562$** | $0.003158$ | $31,908.23$ | **$31,753.78$** | **$317.54$** | **Global Maxima** |
| **$0.0600$** | $0.003600$ | $24,560.95$ | **$24,560.95$** | **$245.61$** | Decreasing |
| **$0.0800$** | $0.006400$ | $7,771.24$ | **$7,771.24$** | **$77.71$** | Decreasing |
| **$0.1000$** | $0.010000$ | $3,183.10$ | **$3,183.10$** | **$31.83$** | Decreasing |
| **$0.2500$** | $0.062500$ | $81.49$ | **$81.49$** | **$0.81$** | Decreasing |
| **$0.5000$** | $0.250000$ | $5.09$ | **$5.09$** | **$0.05$** | Decreasing |
| **$1.0000$** | $1.000000$ | $0.32$ | **$0.32$** | **$0.00$** | Decreasing |

#### 3.4 Forensic Discovery: Test Suite Avoidance
In `tests/RS-SPIKE-3C.2/test_brdf_validation.py` (lines 78–82):
```python
roughnesses = [0.05, 0.10, 0.25, 0.50, 0.75, 1.00]
```
The test suite explicitly started its test sweep at $r = 0.05$. At $r = 0.05$, $f_s = 198.94$, and at $r = 0.10$, $f_s = 31.83$. Thus, the test `assert peaks[i] > peaks[i+1]` passed.
However, had the test included the declared minimum roughness `MIN_ROUGHNESS = 0.04`, it would have failed:
$$\text{peak}(0.04) = 81.49 < \text{peak}(0.05) = 198.94$$

#### 3.5 Recommended Architectural Fix (for RS-SPIKE-3C.3)
To ensure physical monotonicity down to `MIN_ROUGHNESS = 0.04`:
1. The denominator safeguard in `distribution_ggx` must be clamped to `1e-7` or $a^2$:
   ```python
   denom = np.maximum(denom, a2)  # Since denom >= a2 for all valid nh in [0, 1]
   ```
2. Alternatively, raise `MIN_ROUGHNESS` to $0.06$ if $1e-5$ is required for single-precision fp32 stability on older GPUs.

---

### 4. Helmholtz Optical Reciprocity Verification

Helmholtz reciprocity requires:
$$f_s(\mathbf{l}, \mathbf{v}) = f_s(\mathbf{v}, \mathbf{l})$$

1,000 randomized ray pairs were evaluated over $\Omega^+$ with randomly chosen roughnesses in $[0.06, 1.0]$ and $F_0 \in [0.02, 0.95]$:
$$\max_{\mathbf{l}, \mathbf{v}} |f_s(\mathbf{l}, \mathbf{v}) - f_s(\mathbf{v}, \mathbf{l})| = 7.3695 \times 10^{-7} < 10^{-6}$$

Reciprocity holds to machine precision.

---

### 5. Summary & Phase 1 Audit Conclusion

1. The mathematical foundations of the Cook–Torrance model (Smith $G_2/Vis$, Schlick $F$, Burley $\alpha$) are sound and verified against independent literature implementations.
2. Gate G02 and G03 are **PASS**.
3. Gate G01 is declared **CONDITIONAL PASS** due to the $10^{-5}$ clamping defect that inverts NDF peak behavior between $r = 0.04$ and $r = 0.0562$.
