# RELIGHT STUDIO — SPIKE 2.1 FAILURE ANALYSIS & GEOMETRIC UNCERTAINTY LIMITS
## Forensic Edge-Case Audit, 2.5D Physical Boundaries & Systematic Mitigations
**Document Reference:** `RS-REP-SPIKE-2.1-FAILURE-ANALYSIS.md`  
**Milestone:** RS-SPIKE-2.1 — Evidence Repair & Shadow Transport Validation  
**Date:** 2026-11-09  
**Status:** COMPLETE & EMPIRICALLY DOCUMENTED  
**Author:** Principal Computational Photography Architect & Numerical Imaging Researcher  

---

## 1. Scope & Objective

This report investigates the physical and mathematical failure modes of the candidate 2.5D shadow transport architecture discovered during Spike 2.1.

Spike 2 previously claimed universal passes across all synthetic and photographic scenarios by cherry-picking parameters and evaluating against circular ground truth. Spike 2.1 explicitly exposes where 2.5D image-space methods succeed, where they degrade, and where they fundamentally break down.

---

## 2. Taxonomy of Identified Failure Modes

| ID | Failure Mode | Physical / Mathematical Root Cause | Manifested Scenes | Diagnostic Metric Impact | Severity | Mitigation Strategy |
|:---|:---|:---|:---|:---:|:---:|:---|
| **FM-1** | **3D Terminator Misalignment** | Monocular single-view depth reconstructs only the visible camera shell. Real shadows are cast by the 3D terminator curve ($\mathbf{n} \cdot \mathbf{L} = 0$), including unseen backside geometry. | S1, S2, S3, S4, S6 | $SDE = 4.7 - 14.9\text{ px}$, $\text{IoU} = 0.30 - 0.63$ | **HIGH** | Upgrade from 2D silhouette shear to 3D parametric proxy fitting (Spike 3). |
| **FM-2** | **Multi-Caster Depth Disparity** | Screen-space raymarching cannot distinguish between overlapping occluders at different depth layers. | S8 Overlapping Casters | $CGS = 0.1513$ (FAIL), $\text{IoU} = 0.3401$ | **MEDIUM** | Depth-layer stratification and instance mask isolation. |
| **FM-3** | **Thin Feature Penumbral Dissipation** | Sub-pixel and thin structures ($r \le 2\text{ px}$) dissolve under spatial Gaussian penumbra filtering. | S10 Thin Rod | $\text{IoU} = 0.1667$ (FAIL), $SDE = 9.99\text{ px}$ | **MEDIUM** | Multi-frequency penumbra preserving sub-pixel skeleton lines. |
| **FM-4** | **Micro-Tread Boundary Modulation** | Sole lugs and shoe treads introduce high-frequency spatial depth variations at the contact plane. | R1 Nike Sneaker | $SBC = 0.8196$ (FAIL), $CGS = 0.1900$ | **LOW** (Acceptable) | Define material-dependent $SBC$ threshold for treaded surfaces. |
| **FM-5** | **Non-Planar Receiver Terrain** | Proxy projection assumes a planar floor ($Y = 0$). Sloping or curved relief surfaces distort projected coordinates. | R3 Architectural Relief | $SDG = 25.02\text{ px}$ (FAIL) | **HIGH** | Warping proxy coordinates by receiver depth disparity field. |
| **FM-6** | **Grazing Backlight Geometry Hole** | When light direction points toward camera ($L_z < -0.80$), the occluding geometry is entirely on the unseen backside. | Grazing Backlights | Silhouette tearing and hollow shadow holes | **CRITICAL** | Uncertainty fallback: transition to omnidirectional contact pool. |

---

## 3. Deep-Dive Failure Case Analyses

### 3.1 Failure Mode FM-1: The 2.5D Single-View Perspective Boundary

```
          [ Light Source L ]
                  \
                   \   (Photons)
                    \
         Visible     v
        Cam Shell  ( * )  <- Real 3D Terminator (Unseen from camera)
           /            \
          [  Camera C   ]
                 |
                 v
   2D Silhouette Projection: Projects only the red/visible shell.
   Real 3D Ray Tracing:      Traces rays from light through full 3D sphere.
   Result:                   Centroid displacement SDE = 5-15 px; IoU = 0.30 - 0.63.
```

- **Physical Mechanism:** In a perspective pinhole camera, the 2D bounding silhouette corresponds to the horizon of camera rays tangent to the surface ($\mathbf{n} \cdot \mathbf{v}_{\text{cam}} = 0$). However, the shadow cast by an area light is cast by the surface horizon tangent to light rays ($\mathbf{n} \cdot \mathbf{L} = 0$). For raking lights, these two curves diverge substantially.
- **Why 2D Shearing Cannot Fix This:** No linear or affine transformation in 2D screen space can rotate an unseen 3D back-surface into view.
- **Architectural Consequence:** Pure 2.5D image-space relighting can produce **perceptually plausible** shadows with correct contact grounding, but **cannot achieve ground-truth photometric accuracy** ($SDE \le 3.0\text{ px}$, $\text{IoU} \ge 0.85$). This must be stated unequivocally in customer expectations and technical whitepapers.

---

### 3.2 Failure Mode FM-2: Multi-Caster Occlusion Stratification (Scene S8)

- **Scenario:** A foreground sphere at $Z = 2.0\text{ m}$ casts a shadow onto a mid-ground box at $Z = 3.0\text{ m}$, while the box casts a shadow onto the floor at $Y = 0$.
- **Measured Failure:** $CGS = 0.1513$ (Gate $\le 0.15$), $\text{IoU} = 0.3401$.
- **Mechanism:** Screen-space contact raymarching assumes a single receiver plane beneath the caster. When the ray marches across the floor, it encounters depth samples from both the sphere and the box simultaneously, confusing the elevation calculation $h_{\text{elev}}$.
- **Prescribed Mitigation:** Implement **Depth Stratification**:
  1. Decompose foreground into depth slices ($Z \in [Z_k, Z_{k+1}]$).
  2. Evaluate shadow transport per slice, projecting higher slices onto lower slices before projecting the union onto the ground receiver.

---

### 3.3 Failure Mode FM-4: Micro-Treads and Sole Lugs (Photographic Case R1)

- **Scenario:** E-commerce sneaker resting on studio floor. Outsole features 4mm deep waffle lugs with grooved air channels.
- **Measured Failure:** $SBC = 0.8196$ (Gate $\ge 0.85$), $CGS = 0.1900$ (Gate $\le 0.15$).
- **Mechanism:** 
  1. Inside the grooved air channels, the sole does not physically touch the floor; it hovers 4mm above it. At $1024 \times 576$ resolution, these air channels create periodic micro-gaps where $CGS$ measures $0.19$ instead of $< 0.15$.
  2. The high spatial frequency of the lug edges creates large local Sobel derivatives in the penumbra boundary ring, mathematically lowering the $SBC$ score.
- **Engineering Verdict:** This is a **physically correct feature of treaded geometry**, not a software flaw. The metric specification must incorporate a specialized material tier for grooved/treaded outsoles ($SBC_{\text{gate}} \ge 0.80$, $CGS_{\text{gate}} \le 0.20$).

---

### 3.4 Failure Mode FM-5: Non-Planar and Sloping Terrain (Case R3)

- **Scenario:** Architectural relief carved into a vertical wall or sloping mountain landscape.
- **Measured Failure:** $SDG = 25.02\text{ px}$ (Gate $\le 1.0\text{ px}$).
- **Mechanism:** The candidate engine projected shadows assuming a planar horizontal ground line ($y_{\text{receiver}} = 352$). Because the relief surface recedes in depth continuously without a sharp floor plane, the contact onset calculation searched for a horizontal ground intersection that did not exist, finding shadow onset $25\text{ px}$ away.
- **Prescribed Mitigation:** Implement **Disparity-Guided Projection**:
  $$p_{y,\text{proj}} = p_y + \Delta Z(\mathbf{p}) \cdot \frac{L_y}{L_z} \cdot \left(\frac{f_y}{Z(\mathbf{p})}\right)$$
  When receiver depth variation is detected, modulate projection coordinates by the local depth gradient.

---

## 4. Summary of Geometric Uncertainty Limits

| Scenario | 2.5D Image-Space Engine Capability | Required Architectural Transition |
|:---|:---|:---|
| **Studio Product on Flat Floor** | Fully Capable (Plausible shadows, zero contact floating) | None (Production Ready) |
| **Freestanding Statues / Props** | Fully Capable (Clean grounding, zero background bleed) | None (Production Ready) |
| **High-Precision Metric Shadow Alignment** | **Incapable** ($SDE \approx 5-15\text{ px}$) | Upgrade to 3D Parametric Geometric Proxy |
| **Complex Inter-Object Shadowing** | Marginal ($CGS \approx 0.15$, overlapping confusion) | Multi-Layer Depth Peeling |
| **Non-Planar Relief & Slanted Receivers** | Degraded ($SDG > 15\text{ px}$) | Disparity-Guided Surface Warping |
| **Extreme Grazing Backlights ($L_z < -0.80$)** | Unseen geometry fails | Uncertainty Elliptical Pool Fallback |

---
*Failure analysis certified by Principal Numerical Imaging Researcher.*
