# RELIGHT STUDIO — SPIKE 2.2 METRIC SPECIFICATION
## Repaired Diagnostic Metrics, Ground-Truth Contracts & Empty-Mask Policies
**Document Reference:** `RS-SPEC-SPIKE-2.2-METRICS.md`  
**Supercedes:** `docs/spike2_1/RS-SPEC-SPIKE-2.1-METRICS.md`  
**Milestone:** RS-SPIKE-2.2 — Shadow Transport Corrective Validation  
**Date:** 2026-11-09  
**Status:** COMPLETE & MANDATORY FOR SPIKE 2.2 HARNESS  
**Author:** Principal Numerical Methods Researcher & Systems Auditor  

---

## 1. Operating Rules & The Metric Integrity Contract

Every diagnostic metric in Spike 2.2 must adhere to the following non-negotiable principles:

1. **Independent Evaluation Masks:** Evaluation masks (cliffs, contact seams, illuminated regions) must be derived from **independent ground-truth geometry** or independent pre-processing, **never** from candidate output flags or internal state.
2. **Strict Empty-Mask Semantics:** When a metric's support domain $\Omega_{\text{eval}}$ contains zero valid pixels (or falls below the minimum statistical support threshold $N_{\text{min}}$), the harness must return `NOT_APPLICABLE`. It must **never** return `0.0`, `1.0`, or any numeric surrogate.
3. **Missing-Feature Detection:** When a candidate algorithm fails to predict a feature (e.g. producing no shadow when ground truth contains a shadow), distance metrics ($SDE$) and continuity metrics ($SBC$) must return `NOT_APPLICABLE`, while the new **Shadow Recall ($REC_{\text{shadow}}$)** diagnostic records $0.0\%$ (FAIL). Complete failure must never be rewarded with a zero-error score.
4. **Transparent Threshold Integrity:** Original acceptance thresholds are frozen. A gate can be declared PASS, FAIL, CONDITIONAL, NOT_APPLICABLE, or NOT_MEASURED. Thresholds cannot be altered retroactively to force a pass.

---

## 2. Exhaustive Metric Specifications

---

### M1. Contact Grounding Sharpness ($CGS$)
- **Physical Meaning:** Evaluates whether an object is firmly grounded to the receiver surface at true zero-distance contact points, eliminating floating artifacts and light leaks beneath shoe outsoles and pedestals.
- **Mathematical Definition:**
  $$CGS = \min_{\mathbf{x} \in \Omega_{\text{contact}}} \left( V_{\text{direct}}(\mathbf{x}) \cdot C_{\text{contact}}(\mathbf{x}) \right)$$
- **Input Buffers:** $V_{\text{direct}} \in [0, 1]$, $C_{\text{contact}} \in [0, 1]$, Geometric contact mask $\Omega_{\text{contact}}$.
- **Support Region ($\Omega_{\text{contact}}$):** Verified geometric contact interface where caster geometry touches the receiver plane:
  $$\Omega_{\text{contact}} = \{\mathbf{x} \in \Pi_{\text{receiver}} : \text{dist}(\mathbf{x}, \partial \Omega_{\text{caster}}) \le 2\text{ px} \text{ and } |Z(\mathbf{x}) - Z_{\text{receiver}}| \le \epsilon_Z\}$$
  Must **not** use arbitrary rectangular bounding boxes that sample recessed lug air cavities.
- **Measurement Units:** Dimensionless transmittance in $[0.0, 1.0]$.
- **Empty-Mask Policy:** If $|\Omega_{\text{contact}}| < 5\text{ px}$ (e.g. elevated hovering objects $h > 0$), returns `NOT_APPLICABLE`.
- **Target Threshold:** $CGS \le 0.15$ for grounded resting objects ($h = 0$).
- **Known Failure Mode:** Grooved sole treads have air channels where rubber does not touch the floor. $CGS$ must only sample true contact lugs.

---

### M2. Shadow Detachment Gap ($SDG$)
- **Physical Meaning:** Measures the spatial Euclidean distance in pixels between the base of an object and the onset of its shadow on the receiver plane.
- **Mathematical Definition:**
  $$SDG = \min_{\mathbf{p} \in \partial \Omega_{\text{base}}, \; \mathbf{q} \in \text{ShadowOnset}} \|\mathbf{p} - \mathbf{q}\|_2$$
  where $\text{ShadowOnset} = \{\mathbf{x} \in \Pi_{\text{receiver}} : V_{\text{direct}}(\mathbf{x}) < 0.85\}$.
- **Input Buffers:** $V_{\text{direct}}$, Caster base silhouette boundary $\partial \Omega_{\text{base}}$, Receiver mask $\Pi_{\text{receiver}}$.
- **Support Region:** Caster base points and receiver shadow onset pixels.
- **Measurement Units:** Euclidean distance in pixels ($\text{px}$).
- **Empty-Mask Policy:** If no shadow is detected ($|\text{ShadowOnset}| = 0$), returns maximum search horizon ($60.0\text{ px}$). If caster is hovering ($h > 0$), returns distance to shadow onset (must increase monotonically with $h$).
- **Target Threshold:**
  - For Grounded Objects ($h = 0$): $SDG \le 1.0\text{ px}$.
  - For Hovering Objects ($h > 0$): $SDG > 1.0\text{ px}$ and strictly monotonic with elevation $h$.

---

### M3. Shadow Boundary Continuity ($SBC$)
- **Physical Meaning:** Measures spatial gradient continuity across the penumbral boundary of the shadow, penalizing staircasing, raster tearing, and unphysical contour gaps.
- **Mathematical Definition:**
  $$SBC = 1.0 - \frac{1}{|\partial \Omega_{\text{penumbra}}|} \sum_{\mathbf{x} \in \partial \Omega_{\text{penumbra}}} \frac{\|\nabla V_{\text{direct}}(\mathbf{x})\|}{8.0}$$
  where $\nabla V_{\text{direct}}$ is the normalized $3 \times 3$ Sobel gradient, and $\partial \Omega_{\text{penumbra}} = \{\mathbf{x} \in \Pi_{\text{receiver}} : 0.15 < V_{\text{direct}}(\mathbf{x}) < 0.85\}$.
- **Input Buffers:** $V_{\text{direct}}$, Receiver mask $\Pi_{\text{receiver}}$.
- **Support Region:** Penumbra transition band $\partial \Omega_{\text{penumbra}}$ on the receiver plane.
- **Measurement Units:** Dimensionless continuity score in $[0.0, 1.0]$.
- **Empty-Mask Policy:** **CRITICAL REPAIR:** If $|\partial \Omega_{\text{penumbra}}| < 10\text{ px}$ (meaning no shadow exists), returns `NOT_APPLICABLE`. It must **never** return $1.0000$.
- **Target Threshold:** $SBC \ge 0.90$ (Synthetic), $SBC \ge 0.85$ (Photographic).

---

### M4. Silhouette Leakage Rate ($SLR$)
- **Physical Meaning:** Quantifies false shadow bleeding onto illuminated background or depth cliff regions.
- **Mathematical Definition:**
  $$SLR = \frac{|\{\mathbf{x} \in \Omega_{\text{unshadowed\_cliff}} : V_{\text{direct}}(\mathbf{x}) < 0.85\}|}{|\Omega_{\text{unshadowed\_cliff}}|} \times 100\%$$
- **Input Buffers:** $V_{\text{direct}}$, Independent ground-truth depth cliff mask $C_{\text{cliff\_gt}}$, Ground-truth shadow mask $V_{\text{gt}}$.
- **Support Region ($\Omega_{\text{unshadowed\_cliff}}$):**
  $$\Omega_{\text{unshadowed\_cliff}} = \{\mathbf{x} : C_{\text{cliff\_gt}}(\mathbf{x}) = 1 \text{ and } V_{\text{gt}}(\mathbf{x}) > 0.85\}$$
  **CRITICAL REPAIR:** $C_{\text{cliff\_gt}}$ must be derived from the **ground-truth depth map**, never from the candidate's internal $U_{\text{geom}}$.
- **Measurement Units:** Percentage of unshadowed cliff pixels falsely occluded ($\%$).
- **Empty-Mask Policy:** If $|\Omega_{\text{unshadowed\_cliff}}| < 10\text{ px}$, returns `NOT_APPLICABLE`.
- **Target Threshold:** $SLR \le 2.0\%$.

---

### M5a. Shadow Centroid Displacement Error ($SDE$)
- **Physical Meaning:** Measures spatial alignment between the estimated cast shadow and the 3D ray-traced ground truth.
- **Mathematical Definition:**
  $$SDE = \|\mathbf{c}_{\text{est}} - \mathbf{c}_{\text{gt}}\|_2 \quad (\text{px})$$
  $$\mathbf{c} = \frac{\sum_{\mathbf{x} \in \Pi} \mathbf{x} \cdot (1.0 - V(\mathbf{x}))}{\sum_{\mathbf{x} \in \Pi} (1.0 - V(\mathbf{x}))}$$
- **Input Buffers:** $V_{\text{direct}}$, $V_{\text{direct\_gt}}$, Receiver mask $\Pi$.
- **Support Region:** Receiver plane $\Pi$.
- **Measurement Units:** Euclidean distance in pixels ($\text{px}$).
- **Empty-Mask Policy:** **CRITICAL REPAIR:** If $\sum_{\Pi} (1.0 - V_{\text{est}}) < 10.0$ (no shadow estimated), returns `NOT_APPLICABLE`. It must **never** return $0.00\text{ px}$. For real photographs lacking 3D ground truth, strictly returns `NOT_APPLICABLE`.
- **Target Threshold:** $SDE \le 3.0\text{ px}$.

---

### M5b. Shadow Shape Intersection over Union ($\text{IoU}$)
- **Physical Meaning:** Measures morphological overlap between estimated cast shadow and 3D ray-traced ground truth.
- **Mathematical Definition:**
  $$\text{IoU} = \frac{|\mathcal{M}_{\text{est}} \cap \mathcal{M}_{\text{gt}}|}{|\mathcal{M}_{\text{est}} \cup \mathcal{M}_{\text{gt}}|}$$
  where $\mathcal{M} = \{\mathbf{x} \in \Pi : V(\mathbf{x}) < 0.70\}$.
- **Input Buffers:** $V_{\text{direct}}$, $V_{\text{direct\_gt}}$, Receiver mask $\Pi$.
- **Support Region:** Receiver plane $\Pi$.
- **Measurement Units:** Dimensionless ratio in $[0.0, 1.0]$.
- **Empty-Mask Policy:** If $|\mathcal{M}_{\text{gt}}| = 0$ and $|\mathcal{M}_{\text{est}}| = 0$, returns `1.0`. If $|\mathcal{M}_{\text{gt}}| > 0$ and $|\mathcal{M}_{\text{est}}| = 0$, returns `0.0`. On real photographs without 3D ground truth, returns `NOT_APPLICABLE`.
- **Target Threshold:** $\text{IoU} \ge 0.85$.

---

### M5c. Shadow Recall ($REC_{\text{shadow}}$) — NEW REPAIR METRIC
- **Physical Meaning:** Explicitly measures what fraction of the physical ground-truth shadow was successfully detected by the candidate, penalizing missing shadows in ablations.
- **Mathematical Definition:**
  $$REC_{\text{shadow}} = \frac{|\mathcal{M}_{\text{est}} \cap \mathcal{M}_{\text{gt}}|}{|\mathcal{M}_{\text{gt}}|} \times 100\%$$
- **Measurement Units:** Percentage ($\%$).
- **Target Threshold:** $REC_{\text{shadow}} \ge 90.0\%$ for valid shadow transport configurations. Returns $0.0\%$ when shadow is disabled.

---

### M6. False Occlusion Rate ($FOR$)
- **Physical Meaning:** Measures unphysical darkening on fully illuminated foreground surfaces facing the light source.
- **Mathematical Definition:**
  $$FOR = \frac{|\{\mathbf{x} \in \Omega_{\text{illuminated}} : V_{\text{direct}}(\mathbf{x}) < 0.90\}|}{|\Omega_{\text{illuminated}}|} \times 100\%$$
  where $\Omega_{\text{illuminated}} = \{\mathbf{x} \in \Omega_{\text{fg}} : \mathbf{n}(\mathbf{x}) \cdot \mathbf{L} > 0.35 \text{ and } V_{\text{gt}}(\mathbf{x}) > 0.95\}$.
- **Input Buffers:** $V_{\text{direct}}$, Normals $\mathbf{n}$, Light direction $\mathbf{L}$, $V_{\text{gt}}$, Foreground mask $\Omega_{\text{fg}}$.
- **Support Region:** Illuminated foreground surfaces.
- **Measurement Units:** Percentage ($\%$).
- **Empty-Mask Policy:** If $|\Omega_{\text{illuminated}}| < 10\text{ px}$, returns `NOT_APPLICABLE`.
- **Target Threshold:** $FOR \le 1.0\%$.

---

### M7. Multi-Scale Detail Conservation Index ($DCI$)
- **Physical Meaning:** Verifies that relighting preserves high-frequency micro-textures, engravings, and fabric weaves inside shadows.
- **Mathematical Definition:**
  $$DCI = \text{SSIM}\left( \nabla^2 Y_{\text{orig}}, \; \nabla^2 Y_{\text{relit}} \right)$$
  evaluated using an $11 \times 11$ Gaussian window ($\sigma = 1.5$) on Laplacian second-derivative fields.
- **Input Buffers:** Original linear RGB $I_{\text{orig}}$, Relit linear RGB $I_{\text{relit}}$.
- **Support Region:** Entire image domain $\Omega$.
- **Measurement Units:** Structural similarity index in $[-1.0, 1.0]$.
- **Target Threshold:** $DCI \ge 0.980$.

---

### M8. Empirical Penumbra Softening Profile ($PSF$)
- **Physical Meaning:** Verifies that the transition width of the cast shadow penumbra widens monotonically as distance from the caster increases.
- **Mathematical Definition:**
  $$PSF = \frac{W_{\text{penumbra}}(d_2) - W_{\text{penumbra}}(d_1)}{d_2 - d_1}$$
  where $W(d)$ is the 10%–90% transition width along cross-sections at near distance $d_1$ and far distance $d_2$.
- **Measurement Units:** Rate of widening in pixels per pixel ($\text{px} / \text{px}$).
- **Empty-Mask Policy:** If no shadow exists or cross-section has no transition, returns `NOT_APPLICABLE`.
- **Target Threshold:** $PSF > 0.0\text{ px/px}$ (strictly monotonic).

---

### M9. Processing Latency & Memory
- **Physical Meaning:** End-to-end wall-clock time and peak resident memory for interactive relighting.
- **Execution Standards:**
  - Must record warm-up run (1 run discarded).
  - Must record repeated runs ($N \ge 10$).
  - Must report both **p50 (median)** and **p95 (tail latency)**.
  - Must report peak GPU allocation (VRAM) and peak CPU RSS memory.
- **Measurement Units:** Latency in milliseconds ($\text{ms}$); Memory in Megabytes ($\text{MB}$).
- **Target Threshold:** Latency $\le 35.0\text{ ms}$ at 1080p ($1920 \times 1080$).

---

## 3. Summary Metric Classification Matrix

| Metric ID | Metric Name | Synthetic Gate | Photographic Gate | Required Ground Truth | Missing-Feature Policy |
|:---:|:---|:---:|:---:|:---|:---|
| **M1** | Contact Grounding Sharpness ($CGS$) | $\le 0.15$ | $\le 0.15$ | Geometric contact interface | `NOT_APPLICABLE` if $h > 0$ |
| **M2** | Shadow Detachment Gap ($SDG$) | $\le 1.0\text{ px}$ ($h=0$) | $\le 1.0\text{ px}$ ($h=0$) | Silhouette base points | Max search horizon ($60\text{ px}$) |
| **M3** | Shadow Boundary Continuity ($SBC$) | $\ge 0.90$ | $\ge 0.85$ | Direct shadow gradient | `NOT_APPLICABLE` if no shadow |
| **M4** | Silhouette Leakage Rate ($SLR$) | $\le 2.0\%$ | $\le 2.0\%$ | Ground-truth depth cliff mask | `NOT_APPLICABLE` if $|\Omega| < 10$ |
| **M5a**| Shadow Centroid Error ($SDE$) | $\le 3.0\text{ px}$ | `NOT_APPLICABLE` | 3D Ray-Traced Shadow Mask | `NOT_APPLICABLE` if no shadow |
| **M5b**| Shadow Shape $\text{IoU}$ | $\ge 0.85$ | `NOT_APPLICABLE` | 3D Ray-Traced Shadow Mask | $0.00$ if shadow missing |
| **M5c**| Shadow Recall ($REC_{\text{shadow}}$) | $\ge 90.0\%$ | `NOT_APPLICABLE` | 3D Ray-Traced Shadow Mask | $0.0\%$ if shadow missing |
| **M6** | False Occlusion Rate ($FOR$) | $\le 1.0\%$ | $\le 1.0\%$ | Ray-traced illuminated mask | `NOT_APPLICABLE` if $|\Omega| < 10$ |
| **M7** | Detail Conservation ($DCI$) | $\ge 0.980$ | $\ge 0.980$ | Original photographic image | Computed across all pixels |
| **M8** | Penumbra Softening Rate ($PSF$) | $> 0.0$ | $> 0.0$ | 1D penumbra cross-sections | `NOT_APPLICABLE` if no shadow |
| **M9** | 1080p Latency (p50 / p95) | $\le 35\text{ ms}$ | $\le 35\text{ ms}$ | High-resolution hardware clock | `NOT_MEASURED` if no GPU |
| **M10**| Peak Memory (VRAM / RSS) | $\le 512\text{ MB}$ | $\le 512\text{ MB}$ | System memory profiler | Measured in MB |

---
*Specification approved and certified for Spike 2.2 evaluation.*

