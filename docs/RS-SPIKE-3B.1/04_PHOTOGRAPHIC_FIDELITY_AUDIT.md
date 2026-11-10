# RELIGHT STUDIO — RS-SPIKE-3B.1 AUDIT DELIVERABLE
# 04: PHOTOGRAPHIC FIDELITY AUDIT

**Author:** Principal Computational Photography Engineer & Independent Imaging Auditor  
**Date:** November 10, 2026  
**Audited Checkpoint:** `efed4ed` (RS-SPIKE-3B)  
**Evaluation Script:** `benchmarks/validate_photographic_fidelity.py`  
**Test Plates:** `P1_nike_sneaker` ($576 \times 1024$), `P2_classical_statue` ($576 \times 1024$), `P3_architectural_relief` ($768 \times 512$)  

---

## 1. EXECUTIVE SUMMARY & FORENSIC DISCOVERIES

In RS-SPIKE-3B (`docs/RS-SPIKE-3B/06_FINAL_REPORT.md`), the photographic relighting pipeline claimed:
- **Zero-Mutation Difference:** `0.0000000000` (10 decimal places, `PASS`)
- **Detail Conservation Index (DCI):** Reported passing across all plates ($0.8941 - 0.9995$)
- **Photographic Plausibility:** Unconditional Pass

Independent forensic audit has uncovered **two fundamental architectural findings**:

1. **The DCI Background Dilution Flaw & P1 Sneaker Failure:**
   The Detail Conservation Index (DCI) metric as implemented in `eval_DCI` evaluated the whole image rather than isolating the subject foreground.
   When disaggregated into foreground subject vs background:
   - **Plate P1 (Nike Sneaker) Foreground DCI:** **$\mathbf{0.8282}$ (FAILED)** against the $\ge 0.88$ acceptance gate!
   - **Plate P1 Background DCI:** **$0.9702$**
   - **Plate P1 Whole-Image Average:** **$0.8941$**
   The large, uniform background diluted the metric, masking severe micro-contrast degradation on the footwear subject.
2. **Missing E.1 Guided-Filter Regularization in Metal Shaders:**
   Inspection of `metal2/shaders/renderer.metal` reveals that the native Metal shader **omits the E.1 Guided-Filter Shading Ratio Regularization** developed in Spike 1. Instead, it performs **naive multiplicative relighting**:
   $$\mathbf{I}_{\text{relit}} = \mathbf{I}_{\text{orig}} \cdot \left(\mathbf{E}_{\text{irr}} \cdot V + 0.15\right)$$
   In `metal2/renderer.py`, `shading_ratio` is hardcoded as `np.ones_like(out_vis)`. Because high-frequency normal and depth noise directly modulate image pixels without guided-filter edge-preserving smoothing, fine textures on complex geometry (such as the sneaker's mesh) suffer substantial distortion.
3. **Verification of Zero-Mutation:**
   The reported `0.0000000000` difference was verified as **genuine bitwise equality**. In `renderer.metal`, protected pixels branch directly to copy `image_orig_srgb[idx]` into `out_relit_srgb[idx]` with zero floating-point operations. The test correctly covered real photographic pixels across $40\%$ of each image plate.

---

## 2. MATHEMATICAL CRITIQUE OF THE DCI METRIC

The Detail Conservation Index is defined in `benchmarks/validate_photographic_fidelity.py` as:
$$\text{DCI} = \frac{1}{|\Omega|} \sum_{p \in \Omega} \frac{2 \sigma_{xy}(p) + C_3}{2 \sigma_x(p) \sigma_y(p) + C_3}$$
where $x = \Delta Y_{\text{orig}}$, $y = \Delta Y_{\text{relit}}$, $\Delta$ is a $3 \times 3$ discrete Laplacian operator, and $\sigma_{xy}, \sigma_x, \sigma_y$ are local windowed Gaussian statistics ($\text{win}=11, \sigma=1.5$).

### 2.1. Frequency Band Isolation
The $3 \times 3$ Laplacian kernel acts as a second-order high-pass filter:
$$\Delta = \begin{bmatrix} 0 & 1 & 0 \\ 1 & -4 & 1 \\ 0 & 1 & 0 \end{bmatrix}$$
- Its response peaks near the Nyquist frequency ($f \approx 0.25 - 0.50\text{ cycles/pixel}$), isolating micro-textures, fine fabric weaves, and sharp edges.
- Macroscopic lighting gradients $\mathbf{L}(x)$ have near-zero second derivatives ($\Delta \mathbf{L} \approx 0$). Consequently, smooth virtual studio illumination does not penalize the score.

### 2.2. Failure Modes & Inherent Blindnesses of DCI

#### Failure Mode 1: Scale Invariance & Contrast Compression Blindness
Because the SSIM structural term divides covariance by standard deviations ($\frac{\sigma_{xy}}{\sigma_x \sigma_y}$), it is scale-invariant. If a relighting pass compresses local micro-contrast by $50\%$ ($y = 0.5 x$), the correlation remains mathematically **$1.0000$**:
$$\frac{2 (0.5 \sigma_x^2) + C_3}{2 \sigma_x (0.5 \sigma_x) + C_3} = \frac{\sigma_x^2 + C_3}{\sigma_x^2 + C_3} = 1.0000$$
DCI cannot detect severe global or local contrast attenuation.

#### Failure Mode 2: Chromatic & Gamut Blindness
DCI collapses color to 1D luminance:
$$Y = 0.2126 R + 0.7152 G + 0.0722 B$$
If an unconstrained virtual light induces severe chromatic shifts, channel clipping, or hue distortion (e.g. skin tones turning unnaturally green or magenta), DCI continues to report $> 0.99$ as long as the luminance edge gradients remain structurally aligned.

#### Failure Mode 3: Flat-Region Metric Dilution
In flat or smooth background regions where $\Delta Y \approx 0$, local variances approach zero ($\sigma_x \approx 0, \sigma_y \approx 0$). In this regime:
$$\text{DCI}(p) \approx \frac{C_3}{C_3} = 1.0000$$
Any image plate where the subject occupies less than $50\%$ of the frame will have its DCI score artificially inflated by the background.

---

## 3. ZERO-MUTATION IMMUTABILITY VERIFICATION

The reported max difference of `0.0000000000` (10 decimal places) on protected regions was independently audited.

### Source Implementation Verification
In `metal2/shaders/renderer.metal` (lines 568–571):
```cpp
// 5. Non-Destructive Linear Reconstruction & Protected Mask Pass-through
if (has_protected_mask != 0 && protected_mask[idx] != 0) {
    out_relit_srgb[idx] = image_orig_srgb[idx]; // Bitwise zero-mutation guarantee
    return;
}
```

### Analysis:
1. **Bitwise Integrity:** In Apple Silicon unified memory, `out_relit_srgb[idx] = image_orig_srgb[idx]` emits a direct 128-bit memory copy without floating-point arithmetic or conversion. The bits are bitwise identical.
2. **Mask Coverage:** The test mask protected `W * 0.40` (the entire left 40% of the image). In all three photographic cases (P1, P2, P3), this region contains non-trivial photographic data:
   - In P1, it spans the sneaker toe-box, outsole tread, and ground plane.
   - In P2, it spans the statue torso, drapery folds, and cyc background.
   - In P3, it spans architectural stone carvings and mortar joints.
3. **Verdict:** The zero-mutation guarantee is **GENUINE and FULLY VERIFIED**.

---

## 4. PLATE-BY-PLATE PHOTOGRAPHIC FIDELITY AUDIT

| Plate ID | Subject & Geometry | Overall DCI | Foreground DCI | Background DCI | Gate Status ($\ge 0.88$) | Visual Artifacts & Notes |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **P1** | Nike Sneaker (Low-Poly Mesh, 280 tri) | 0.8941 | **0.8282** | 0.9702 | **FAIL (FG)** | Noticeable texture crunch and edge haloing along shoe collar. |
| **P2** | Classical Statue (Superquadric Cove) | 0.9971 | **0.9968** | 0.9989 | **PASS** | Exceptional smooth surface relighting on stone carving. |
| **P3** | Architectural Relief (OBB Planar) | 0.9876 | **0.9963** | 0.9818 | **PASS** | High-frequency masonry micro-contrast well preserved. |

### 4.1. Case P1: Footwear Subject (Nike Sneaker) — Detailed Failure Analysis
- **Observed Behavior:**
  - Foreground DCI dropped to **$0.8282$**, failing the milestone threshold.
  - While the overall score was reported as $0.8941$, this was an illusion created by the smooth $0.9702$ background.
- **Root Cause:**
  - The Nike sneaker has high geometric complexity with discontinuous estimated depth normals.
  - Because `metal2/shaders/renderer.metal` executes naive multiplicative relighting rather than E.1 guided-filter smoothing, rapid spatial variations in the depth-derived surface normals modulate the original RGB pixels directly.
  - This induces high-frequency shading artifacts ("texture crunch") and edge halos where normals abruptly transition from the shoe outsole to the floor.

### 4.2. Case P2: Classical Marble Statue (Organic Surface)
- **Observed Behavior:**
  - Foreground DCI achieved **$0.9968$**; overall DCI achieved **$0.9971$**.
  - Warm key light ($3200\text{ K}$) at $-35^\circ$ creates natural grazing illumination across the statue's muscular anatomy and drapery.
- **Analysis:**
  - Because the statue's geometry is continuous and smooth, depth-derived normals vary gradually.
  - The superquadric shadow projection onto the cyclorama cove produces a soft, believable cast shadow with smooth contact grounding.

### 4.3. Case P3: Architectural Stone Relief (Hard Surface)
- **Observed Behavior:**
  - Foreground DCI achieved **$0.9963$**; overall DCI achieved **$0.9876$**.
  - Cool key light ($6500\text{ K}$) creates sharp relief shadows emphasizing carved masonry.
- **Analysis:**
  - The stone surface has dense intrinsic high-frequency texture. Because the underlying proxy is an OBB aligned with the relief plane, the illumination gradient across the facade is smooth, allowing intrinsic textures to shine through cleanly.

---

## 5. AUDIT RECOMMENDATIONS FOR PHOTOGRAPHIC PIPELINE

1. **Mandatory Disaggregated DCI Reporting:**
   The evaluation harness must be permanently updated to report **Foreground DCI** (`eval_DCI(orig, relit, fg_mask)`) independently from whole-image DCI. Whole-image DCI must never be used as a primary acceptance gate.
2. **Re-implement E.1 Guided-Filter Regularization on Metal:**
   The omission of the E.1 Guided-Filter Shading Ratio pass in Metal is the direct cause of the P1 sneaker failure ($0.8282$). A native Metal guided filter compute kernel must be implemented in the next milestone to smooth the shading ratio before image modulation.
3. **Verdict on Photographic Fidelity:**
   **CONDITIONAL PASS.** Passes convincingly on smooth organic surfaces (P2) and textured planar reliefs (P3), but fails acceptance standards on complex geometric subjects (P1) due to the absence of the E.1 regularizer in Metal shaders.
