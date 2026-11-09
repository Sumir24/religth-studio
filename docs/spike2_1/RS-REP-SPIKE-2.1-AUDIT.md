# RELIGHT STUDIO — SPIKE 2.1 FORENSIC AUDIT REPORT
**Document Reference:** `RS-REP-SPIKE-2.1-AUDIT.md`  
**Prior Art Audited:** `spike_shadow_transport.py`, `spike2_output/SPIKE_2_EVALUATION_REPORT.md`, `spike2_output/benchmark_results.json`, `docs/superpowers/specs/2026-11-09-spike-2-shadow-transport-design.md`  
**Auditor:** Principal Computational Photography Architect & Rendering Engineer  
**Date:** 2026-11-09  
**Status:** COMPLETE — CRITICAL DEFECTS CONFIRMED

---

## 1. Executive Summary of Audit Findings

A forensic review of the Spike 2 implementation (`spike_shadow_transport.py`) and its associated evaluation report (`spike2_output/SPIKE_2_EVALUATION_REPORT.md`) reveals five major categories of critical engineering defects:

1. **Fabricated & Hardcoded Benchmark Metrics:** The S2 elevation sweep hardcoded five out of six reported metrics (`SBC=0.985`, `SLR=0.0%`, `SDE=0.25px`, `FOR=0.0%`, `DCI=0.9997`). Real photographic test cases hardcoded `SDG=0.0`, `SDE=0.0`, `FOR=0.0`. Penumbra Softening Behavior ($PSF$) was never measured from output images, but was claimed to pass based on a parameter declaration.
2. **Circular Ground-Truth Generation:** Synthetic Scene S1's "ground-truth" cast shadow was generated using the **exact same 2D silhouette extrusion and Gaussian blur formula** as the candidate proxy renderer itself. The reported $SDE = 0.00 - 0.28\text{ px}$ was a measurement of the candidate against an identical copy of its own algorithm, not an independent physically based ray-traced reference.
3. **Severe Acceptance Gate Misrepresentation:** The summary table in the Spike 2 report classified failed gates as **PASS** by cherry-picking synthetic sub-cases while ignoring measured photographic failures:
   - **Gate S3 (SBC):** Target $\ge 0.90$. Real sneaker scored $0.881$, architectural relief scored $0.780$. Reported as **PASS**.
   - **Gate S4 (SLR):** Target $\le 2.0\%$. Classical statue scored $3.67\%$. Reported as **PASS**.
   - **Gate S8 (DCI):** Target $\ge 0.980$. Classical statue scored $0.9760$. Reported as **PASS**.
   - **Gate S9 (Latency):** Target $\le 35\text{ ms}$ (1080p). Measured $p95 = 131.20\text{ ms}$ (1080p) and $634.96\text{ ms}$ (4K). Reported as **PASS**.
4. **Physical Conflation in Light Transport Architecture:**
   - Ambient Occlusion ($T_{\text{ao}}$) was multiplied directly into the directional key-light attenuation field, violating the rendering equation by applying indirect diffuse occlusion to direct radiance.
   - Surface orientation ($\mathbf{n} \cdot \mathbf{L}$) was mislabeled as "directional self-shadowing" ($T_{\text{self}}$) without performing any self-occlusion ray checks.
   - Contact raymarching and analytical cast shadow footprints were multiplied indiscriminately, causing double-attenuation in near-contact zones.
5. **Uncalibrated Image-Space Depth & Missing Camera Projection:** Depth maps were manipulated as arbitrary normalized values in $[0, 1]$ without focal length, field of view, or metric scale. Raymarching steps relied on arbitrary heuristic multipliers (`tan_elev * 0.005`).

---

## 2. Metric Provenance Audit (Section A1)

Below is the exhaustive provenance audit of every metric reported in `spike2_output/benchmark_results.json`:

| Metric ID | Metric Name | Current Implementation in `spike_shadow_transport.py` | Independently Measured? | Confirmed Defect | Required Repair for Spike 2.1 |
|:---|:---|:---|:---:|:---|:---|
| **M1** | Contact Grounding Sharpness ($CGS$) | Evaluates `np.min` across contact horizontal window or entire row. | **PARTIAL** | On real photos, broad row-wide minimums could capture unoccluded dark albedo pixels rather than true contact seam occlusion. | Restrict $CGS$ strictly to verified geometric contact coordinates along object base. Measure both local minimum and contact distribution. |
| **M2** | Shadow Detachment Gap ($SDG$) | Searches downward for first pixel with $T < 0.85$. | **PARTIAL (Synthetic S1/S2)**<br>**NO (Real Photos)** | On real photos (R1, R2, R3), `SDG_px: 0.0` was **hardcoded** in the dictionary without running search! In S2, search was only along a single column ($cx$). | Execute true 2D distance transform between silhouette boundary and shadow onset across all test cases. Report `NOT_APPLICABLE` when contact base is off-frame or ungrounded. |
| **M3** | Shadow Boundary Continuity ($SBC$) | Computes normalized Sobel gradient across boundary of $(T < 0.85)$. | **YES (S1, S3, Real)**<br>**NO (S2 Sweep)** | In Scene S2 elevation sweep, `SBC: 0.985` was **hardcoded** across all 4 elevations ($h=0, 5, 20, 50$). On real images, failed values ($0.780, 0.881$) were concealed in report summary. | Compute actual boundary gradients across all scenes without hardcoding. Accurately report when sharp micro-treads or contact edges lower $SBC$. |
| **M4** | Silhouette Leakage Rate ($SLR$) | Measures percentage of unshadowed cliff pixels with $T < 0.85$. | **YES (S1, S3, Real)**<br>**NO (S2 Sweep)** | In Scene S2, `SLR_pct: 0.0` was **hardcoded**. In Case R2, measured $SLR = 3.67\%$ was suppressed in report summary to claim gate passed. | Evaluate false shadow leakage against true unshadowed ground truth masks. Report failures transparently. |
| **M5** | Shadow Displacement Error ($SDE$) | Computes Euclidean distance between centroid of $(1-T) \cdot \text{ground}$ and GT. | **NO (Circular)** | Ground truth $T_{\text{gt}}$ in S1 was generated using the **exact same code** as candidate ($SDE \approx 0.00\text{ px}$). On real images, `SDE: 0.0` was **hardcoded** as zero error despite having no ground truth. | Implement an independent 3D ray-traced reference renderer with no shared projection code. Report `NOT_APPLICABLE` for real photographs without 3D ground truth. |
| **M6** | Penumbra Softening Behavior ($PSF$) | Declared in report table as "Monotonic rise ($\beta=0.08$)". | **NO (Fabricated)** | **Never computed from output images.** A parameter slope was cited as an empirical result. No actual penumbra profile or width was measured. | Fit sigmoid/error functions across shadow penumbra transects at multiple caster-receiver distances. Measure empirical edge width $\Delta x_{10\% \to 90\%}$ and verify physical monotonic increase. |
| **M7** | False Occlusion Rate ($FOR$) | Measures percentage of unshadowed background pixels with $T < 0.90$. | **YES (S1)**<br>**NO (S2, S3, Real)** | Hardcoded as `0.0%` for S2 sweep, S3 step box, and all real photographic cases. | Define explicit illuminated test regions across all scenes. Compute true unoccluded false darkening rates. |
| **M8** | Frame Latency & Memory | Measured with `time.perf_counter()` and `tracemalloc`. | **YES (Measured)** | Latency ($p95 = 131.2\text{ ms}$ at 1080p, $634.96\text{ ms}$ at 4K) failed the interactive target ($\le 35\text{ ms}$), but report incorrectly labeled it **PASS**. Memory tracked only Python allocations, omitting native C/OpenCV buffers. | Measure complete end-to-end pipeline latency. Track OS Resident Set Size (RSS) alongside Python allocations. Benchmark GPU/Metal feasibility. |
| **M9** | Detail Preservation ($DCI_{\text{shadow}}$) | Computes Laplacian structural correlation (SSIM) between original and relit image. | **YES (S1, S3, Real)**<br>**NO (S2 Sweep)** | In S2 sweep, `DCI_shadow: 0.9997` was **hardcoded**. Case R2 scored $0.9760$ ($< 0.980$), but report summary claimed gate passed. DCI was also over-interpreted as proof of complete physical preservation. | Compute DCI dynamically for all test cases. Supplement with separate edge preservation, high-frequency energy ratio, and local chromatic error metrics. |

---

## 3. Light Transport & Component Implementation Audit (Section A2)

### 3.1 Conflation of Ambient Occlusion ($T_{\text{ao}}$) with Direct Radiance
In `spike_shadow_transport.py`:
```python
T_fg = T_ao * T_contact * (0.15 + 0.85 * T_self)
T_bg = T_ao * T_contact * T_cast
R_target = R_ambient + (R_key - R_ambient) * T_comp
```
- **Physical Defect:** Standard rendering theory dictates:
  $$L_o(\mathbf{x}, \omega_o) = \int_{\Omega} f_r(\mathbf{x}, \omega_i, \omega_o) L_i(\mathbf{x}, \omega_i) (\mathbf{n} \cdot \omega_i) d\omega_i$$
  Splitting into direct and indirect ambient illumination:
  $$L_o \approx L_{\text{direct}} \cdot V_{\text{direct}}(\mathbf{x}) \cdot (\mathbf{n} \cdot \mathbf{L}) + L_{\text{ambient}} \cdot A_{\text{ambient}}(\mathbf{x})$$
  In `spike_shadow_transport.py`, $T_{\text{ao}}$ multiplies $R_{\text{key}} \cdot T_{\text{comp}}$. Thus, when a strong direct spotlight shines directly into a cavity, the cavity remains artificially black because $T_{\text{ao}}$ attenuates the key light directly!
- **Required Repair:** Ambient occlusion must modulate only the indirect/ambient fill term $R_{\text{ambient}}$, never the direct key light radiance $R_{\text{key}}$.

### 3.2 Misattribution of Directional Response ($T_{\text{self}}$)
- In `compute_component_T_self`:
  ```python
  cos_theta = np.sum(normals * L, axis=-1)
  taper = smoothstep(-horizon_taper, horizon_taper, cos_theta)
  T_self = taper * np.maximum(0.0, cos_theta)
  ```
- **Physical Defect:** This is simply a softened **Lambertian cosine law** $D_{\text{diffuse}} = \max(0, \mathbf{n} \cdot \mathbf{L})$. It contains zero raymarching or occlusion testing. Calling it "directional self-shadowing" is physically false.
- **Required Repair:** Rename this term to Diffuse Orientation Response ($D_{\text{diffuse}}$). True self-occlusion ($V_{\text{self}}$) requires testing whether another surface element blocks the direct light ray along $-\mathbf{L}$.

### 3.3 Contact Shadow ($T_{\text{contact}}$) and Cast Shadow ($T_{\text{cast}}$) Double-Counting
- In `composite_shadow_transport`:
  $T_{\text{bg}} = T_{\text{ao}} \cdot T_{\text{contact}} \cdot T_{\text{cast}}$.
- **Physical Defect:** Both $T_{\text{contact}}$ and $T_{\text{cast}}$ attempt to compute direct light visibility on the receiver. Multiplying them causes the near-contact receiver zone to be squared in attenuation, producing an unnaturally dark band right beside the caster.
- **Required Repair:** Direct visibility on the receiver must be computed via a unified visibility union:
  $$V_{\text{receiver}}(\mathbf{x}) = \min(V_{\text{contact}}(\mathbf{x}), V_{\text{cast}}(\mathbf{x}))$$
  or a distance-weighted blend from near-field contact raymarching to far-field proxy projection.

---

## 4. Geometry and Depth Audit (Section A3)

1. **Uncalibrated Depth Conventions:**
   - Single-view monocular depth maps from DPT/MiDaS output relative inverse disparity, not linear metric depth $Z$.
   - `spike_shadow_transport.py` applied linear 3D analytical formulas:
     $$x_{\text{proj}} = x + t \cdot L_x, \quad y_{\text{proj}} = y_{\text{ground}} + t \cdot L_z \cdot 0.20$$
     where $0.20$ was an arbitrary empirical fudge factor.
   - Without camera focal length $f_x, f_y$ and principal point $(c_x, c_y)$, screen-space projections are severely distorted when light elevation changes.
2. **Silhouette and Contact Seam Detection Heuristics:**
   - Case R1 sneaker hardcoded `ground_y = 648`, but the sneaker sole has variable elevation across its length.
   - Case R2 statue used `ground_y = 988`, but the pedestal base spans multiple perspective depths.
3. **Missing Backside Geometry:**
   - For lights with $L_z < -0.80$ (steep backlighting), the single-view depth map contains zero evidence of rear object shape. Extruding the front silhouette along $+\mathbf{L}$ assumes the object is an infinite cylinder in depth.

---

## 5. Benchmark Integrity Audit (Section A4)

1. **Circular Ground Truth in Scene S1:**
   - Lines 251-265 of `spike_shadow_transport.py` generated `T_gt` using:
     ```python
     y_coords, x_coords = np.where(sphere_mask)
     d_to_ground = np.maximum(0.0, y_ground - y_coords)
     proj_x = np.clip(np.round(x_coords + d_to_ground * scale_x), 0, W - 1).astype(int)
     proj_y = np.clip(np.round(y_ground + d_to_ground * scale_y), 0, H - 1).astype(int)
     footprint_gt = np.zeros((H, W), dtype=np.float32)
     footprint_gt[proj_y, proj_x] = 1.0
     footprint_gt = cv2.morphologyEx(footprint_gt, cv2.MORPH_CLOSE, kernel)
     shadow_soft_gt = cv2.GaussianBlur(footprint_gt, (k_size, k_size), sigma_penumbra)
     ```
   - Lines 461-480 (`compute_component_T_cast`) implemented the exact identical block of code.
   - Comparing the candidate against an identical implementation yielded $SDE \approx 0.00\text{ px}$. This created an illusion of mathematical precision while testing nothing.
2. **Mask Boundary Conflation:**
   - In Scene S1, `sbc = measure_shadow_boundary_continuity(T_comp, (T_comp < 0.85) & ground_mask)` measured the gradient of a Gaussian-blurred mask on a flat plane. A blurred plane is by definition smooth ($\approx 0.97$), so this metric did not evaluate edge tearing across the object boundary.

---

## 6. Performance Audit (Section A5)

1. **Measured Latency vs. Claimed Status:**
   - 1080p single-thread CPU execution was measured at **$p95 = 131.20\text{ ms}$** (approx. 7.6 fps).
   - 4K single-thread CPU execution was measured at **$p95 = 634.96\text{ ms}$** (approx. 1.5 fps).
   - The interactive requirement specified $\le 35\text{ ms}$ (30 fps).
   - Claiming **PASS** for Gate S9 was mathematically indefensible.
2. **Memory Tracing Scope:**
   - `tracemalloc` only traces memory allocated inside the Python interpreter heap ($79.29\text{ MB}$ for 1080p, $316.78\text{ MB}$ for 4K).
   - Memory allocated by OpenCV C++ kernels (`cv2.GaussianBlur`, `cv2.Sobel`, `cv2.morphologyEx`) and OS virtual memory paging was excluded. True process RSS exceeded $220\text{ MB}$ for 1080p and $750\text{ MB}$ for 4K.

---

## 7. Action Plan for Spike 2.1

Based on this audit, Spike 2.1 must execute the following corrective engineering phases:

1. **Phase B:** Author `RS-SPEC-SPIKE-2.1-CORRECTED-ARCHITECTURE.md` establishing seven decoupled physical terms:
   - Direct Visibility: $V_{\text{direct}}$
   - Ambient Visibility: $A_{\text{ambient}}$
   - Contact Occlusion: $C_{\text{contact}}$
   - Diffuse Orientation: $D_{\text{diffuse}}$
   - Self-Occlusion: $V_{\text{self}}$
   - Cast Shadow Visibility: $V_{\text{cast}}$
   - Geometric Confidence: $U_{\text{geometry}}$
2. **Phase C:** Build `spike2_1_reference_renderer.py` featuring an **independent 3D ray-tracer** with analytical ray-primitive intersection, spherical area-light monte-carlo cone sampling, and calibrated perspective camera projection.
3. **Phase D:** Rebuild the metric harness in `spike2_1_evaluation.py` and specify in `RS-SPEC-SPIKE-2.1-METRICS.md` with zero hardcoding and explicit `NOT_MEASURED` / `NOT_APPLICABLE` states.
4. **Phase E:** Implement full 10-configuration component ablation in `spike2_1_ablation.py`.
5. **Phase F:** Profile full-pipeline CPU latency and investigate GPU/Metal shader translation feasibility in `RS-REP-SPIKE-2.1-PERFORMANCE.md`.
6. **Phase G & H:** Execute benchmark, produce visual contact sheets, failure-mode analysis, and an evidence-backed architectural decision.

---
*Report certified by Principal Computational Photography Architect & Rendering Engineer.*
