# RELIGHT STUDIO — SPIKE 2.1 METRIC SPECIFICATION
## Quantitative Diagnostics, Physical Definitions & Evaluation Standards
**Document Reference:** `RS-SPEC-SPIKE-2.1-METRICS.md`  
**Purpose:** Replace ad-hoc, hardcoded, or circular metrics with mathematically defensible, independently verifiable imaging metrics.  
**Author:** Principal Computational Photography Architect & Numerical Imaging Researcher  
**Status:** COMPLETE & MANDATORY FOR SPIKE 2.1 HARNESS  

---

## 1. Metric System Overview & Non-Negotiable Standards

Every diagnostic metric in Spike 2.1 must adhere to the following rules:
1. **Zero Hardcoded Outputs:** If a metric cannot be evaluated on a given test scene (e.g., ground-truth displacement on an uncalibrated real photograph), the harness must output `NOT_APPLICABLE` or `NOT_MEASURED`. Never report dummy values such as `0.0`.
2. **Independent Ground Truth:** Comparisons must be performed against an independent 3D ray-traced reference (`spike2_1_reference_renderer.py`), never against a formula derived from the candidate prototype.
3. **Strict Domain Definition:** Every metric must have an explicitly defined support region $\Omega_{\text{eval}}$ and non-zero denominator check to prevent artificial zero error from empty masks.

---

## 2. Exhaustive Metric Specifications

### D1. Contact Grounding Sharpness ($CGS$)
- **Physical Meaning:** Evaluates whether an object is firmly grounded to the receiver surface at zero-distance contact interfaces, preventing floating artifacts or light leaks under shoe soles and pedestals.
- **Mathematical Definition:**
  $$CGS = \min_{\mathbf{x} \in \Omega_{\text{contact}}} V_{\text{direct}}(\mathbf{x}) \cdot C_{\text{contact}}(\mathbf{x})$$
  where $\Omega_{\text{contact}}$ is the verified geometric contact interface between object base and receiver plane.
- **Support Region:** Dilated intersection band $\partial \Omega_{\text{caster}} \cap \Pi_{\text{receiver}}$ within $\pm 2\text{ px}$ of the contact base.
- **Units:** Dimensionless transmittance in $[0.0, 1.0]$.
- **Target Threshold:** $CGS \le 0.15$ for grounded resting objects ($h = 0$).
- **Empty Mask Handling:** Returns `NOT_APPLICABLE` if no contact points exist.

### D2. Shadow Detachment Gap ($SDG$)
- **Physical Meaning:** Measures the spatial distance in pixels between the lowest point of an object's silhouette and the onset of its shadow on the receiver.
- **Mathematical Definition:**
  $$SDG = \min_{\mathbf{p} \in \partial \Omega_{\text{base}}, \; \mathbf{q} \in \text{ShadowOnset}} \|\mathbf{p} - \mathbf{q}\|_2$$
  where $\text{ShadowOnset} = \{\mathbf{x} \in \Pi_{\text{receiver}} : V_{\text{direct}}(\mathbf{x}) < 0.85\}$.
- **Units:** Pixels ($\text{px}$).
- **Target Threshold:**
  - For Grounded Objects ($h = 0$): $SDG \le 1.0\text{ px}$.
  - For Elevated Objects ($h > 0$): $SDG$ must be monotonically increasing with elevation $h$.
- **Empty Mask Handling:** Returns maximum search horizon ($60\text{ px}$) if no shadow is cast.

### D3. Shadow Boundary Continuity ($SBC$) & Tearing
- **Physical Meaning:** Measures gradient continuity across the penumbral boundary of the shadow and across the contact interface, detecting raster tearing, contour staircasing, and unphysical halo gaps.
- **Mathematical Definition:**
  $$SBC = 1.0 - \frac{1}{|\partial \Omega_{\text{shadow}}|} \sum_{\mathbf{x} \in \partial \Omega_{\text{shadow}}} \frac{\|\nabla V_{\text{direct}}(\mathbf{x})\|}{8.0}$$
  where $\nabla V_{\text{direct}}$ is the normalized $3 \times 3$ Sobel gradient, and $\partial \Omega_{\text{shadow}}$ is the 3-pixel boundary ring around the shadow footprint ($0.15 < V_{\text{direct}} < 0.85$).
- **Units:** Dimensionless continuity score in $[0.0, 1.0]$.
- **Target Threshold:** $SBC \ge 0.90$.
- **Known Failure Mode:** High-frequency micro-treads (e.g. sole lugs) create physically sharp shadow edges that legitimately lower $SBC$ to $\approx 0.85 - 0.88$. Documented as an acceptable material-dependent variation.

### D4. Silhouette Leakage Rate ($SLR$)
- **Physical Meaning:** Quantifies false shadow bleeding onto illuminated background or cliff regions.
- **Mathematical Definition:**
  $$SLR = \frac{|\{\mathbf{x} \in \Omega_{\text{unshadowed\_cliff}} : V_{\text{direct}}(\mathbf{x}) < 0.85\}|}{|\Omega_{\text{unshadowed\_cliff}}|} \times 100\%$$
  where $\Omega_{\text{unshadowed\_cliff}}$ is the region of depth cliffs ($U_{\text{geometry}} = 0$) that lie outside the physical ground-truth shadow cone.
- **Units:** Percentage ($\%$) of cliff pixels falsely occluded.
- **Target Threshold:** $SLR \le 2.0\%$.
- **Empty Mask Handling:** If $|\Omega_{\text{unshadowed\_cliff}}| < 10\text{ px}$, returns `NOT_APPLICABLE` rather than false $0.0\%$.

### D5. Shadow Displacement & Shape Accuracy ($SDE$, $\text{IoU}$)
- **Physical Meaning:** Measures geometric alignment between the estimated cast shadow and the ground-truth 3D ray-traced reference.
- **Mathematical Definitions:**
  1. **Centroid Displacement Error ($SDE$):**
     $$SDE = \|\mathbf{c}_{\text{est}} - \mathbf{c}_{\text{gt}}\|_2 \quad (\text{px})$$
     where $\mathbf{c} = \frac{\sum \mathbf{x} (1 - V(\mathbf{x}))}{\sum (1 - V(\mathbf{x}))}$.
  2. **Intersection over Union ($\text{IoU}$):**
     $$\text{IoU} = \frac{|\mathcal{M}_{\text{est}} \cap \mathcal{M}_{\text{gt}}|}{|\mathcal{M}_{\text{est}} \cup \mathcal{M}_{\text{gt}}|}$$
     where $\mathcal{M} = \{\mathbf{x} : V_{\text{direct}}(\mathbf{x}) < 0.70\}$.
- **Units:** $SDE$ in pixels ($\text{px}$); $\text{IoU}$ in $[0.0, 1.0]$.
- **Target Threshold:** $SDE \le 3.0\text{ px}$, $\text{IoU} \ge 0.85$.
- **Real Photo Behavior:** Marked `NOT_APPLICABLE` on real photos lacking 3D ground truth.

### D6. False Occlusion Rate ($FOR$)
- **Physical Meaning:** Measures unphysical darkening on fully illuminated surfaces facing the light.
- **Mathematical Definition:**
  $$FOR = \frac{|\{\mathbf{x} \in \Omega_{\text{illuminated}} : V_{\text{direct}}(\mathbf{x}) < 0.90\}|}{|\Omega_{\text{illuminated}}|} \times 100\%$$
  where $\Omega_{\text{illuminated}} = \{\mathbf{x} : \mathbf{n}(\mathbf{x}) \cdot \mathbf{L} > 0.35 \text{ and } V_{\text{gt}}(\mathbf{x}) = 1.0\}$.
- **Units:** Percentage ($\%$).
- **Target Threshold:** $FOR \le 1.0\%$.

### D7. Multi-Scale Detail Conservation ($DCI_{\text{shadow}}$)
- **Physical Meaning:** Verifies that shadow transport does not destroy underlying micro-textures, fabric weaves, or surface typography.
- **Mathematical Definition:**
  $$DCI_{\text{shadow}} = \text{SSIM}\left( \nabla^2 Y_{\text{orig}}, \; \nabla^2 Y_{\text{relit}} \right)$$
  evaluated within the shadow region $\Omega_{\text{shadow}}$.
- **Units:** Structural similarity index in $[-1.0, 1.0]$.
- **Target Threshold:** $DCI_{\text{shadow}} \ge 0.980$.

### D8. Empirical Penumbra Softening Profile ($PSF$)
- **Physical Meaning:** Measures whether the transition width of the cast shadow penumbra widens monotonically as caster-to-receiver distance increases.
- **Mathematical Definition:**
  Extract 1D cross-sections of $V_{\text{direct}}$ perpendicular to the shadow edge at near-contact ($d_1$) and far-field ($d_2$):
  $$W_{\text{penumbra}}(d) = \|\mathbf{x}_{90\%} - \mathbf{x}_{10\%}\|_2$$
  $$PSF = \frac{W_{\text{penumbra}}(d_2) - W_{\text{penumbra}}(d_1)}{d_2 - d_1}$$
- **Units:** Rate of widening $\text{px} / \text{px}$.
- **Target Threshold:** $PSF > 0.0$ (strictly monotonic widening) and within $\pm 25\%$ of ground truth ray-traced penumbra rate.

---

## 3. Metric Summary & Acceptance Criteria Table

| ID | Metric Name | Synthetic Gate | Photographic Gate | Required Ground Truth |
|:---:|:---|:---:|:---:|:---|
| **M1** | Contact Grounding Sharpness ($CGS$) | $\le 0.15$ | $\le 0.15$ | Known receiver plane / base seam |
| **M2** | Shadow Detachment Gap ($SDG$) | $\le 1.0\text{ px}$ ($h=0$) | $\le 1.0\text{ px}$ ($h=0$) | Silhouette contact points |
| **M3** | Shadow Boundary Continuity ($SBC$) | $\ge 0.90$ | $\ge 0.85$ (micro-treads) | Direct shadow gradient |
| **M4** | Silhouette Leakage Rate ($SLR$) | $\le 2.0\%$ | $\le 2.0\%$ | Unshadowed cliff mask |
| **M5a**| Shadow Displacement Error ($SDE$) | $\le 3.0\text{ px}$ | `NOT_APPLICABLE` | 3D Ray-Traced Shadow Mask |
| **M5b**| Shadow Shape $\text{IoU}$ | $\ge 0.85$ | `NOT_APPLICABLE` | 3D Ray-Traced Shadow Mask |
| **M6** | Penumbra Softening Behavior ($PSF$) | $PSF > 0$ | $PSF > 0$ | 1D penumbra cross-sections |
| **M7** | False Occlusion Rate ($FOR$) | $\le 1.0\%$ | $\le 1.0\%$ | Known illuminated zone |
| **M8** | Detail Conservation ($DCI_{\text{shadow}}$) | $\ge 0.980$ | $\ge 0.980$ | Original photographic albedo |
| **M9** | 1080p Processing Latency | $\le 35\text{ ms}$ | $\le 35\text{ ms}$ | High-resolution timer |

---
*Metric specification compiled and certified for Spike 2.1 execution.*
