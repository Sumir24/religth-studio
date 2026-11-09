# RELIGHT STUDIO — MILESTONE PROPOSAL
## RS-SPIKE-3A: Parametric 3D Proxy & Geometry-Aware Shadow Transport

- **Document ID:** RS-PROP-SPIKE-3A-GEOMETRY-v1.0
- **Status:** APPROVED PROPOSAL FOR IMMEDIATE EXECUTION
- **Author:** Principal Physically Based Rendering Engineer & Numerical Methods Specialist
- **Date:** 2026-11-09
- **Preceding Milestone:** RS-SPIKE-2.2 (Disproved General 2.5D Image-Space Cast Shadows)

---

### 1. Executive Summary & Problem Statement

In RS-SPIKE-2.2, empirical evaluation against 3D ground-truth ray tracing established that pure 2.5D image-space shadow projection fails general production acceptance ($SDE = 13.4\text{ px}$, $\text{IoU} = 0.521$, $SLR = 12.66\%$ on cycloramas, $48.33\text{ px}$ error on hovering subjects).
The fundamental physical limitation is that a monocular 2.5D depth map contains no geometry for the occluder's back volume, and a 2D shear projection cannot project shadows across non-planar receivers (curved cycloramas, walls, or multi-tiered stages).

**Milestone Objective:**
Build and validate a **Parametric 3D Proxy & Geometry-Aware Shadow Engine** that couples 2.5D monocular depth with analytical 3D volumetric proxies (Oriented Bounding Boxes, Superquadric Ellipsoids, and Capsule Hierarchies) and curved parametric receiver models to achieve sub-millimeter shadow accuracy ($SDE \le 2.0\text{ px}$, $\text{IoU} \ge 0.90$, $SLR \le 1.0\%$) without requiring expensive multi-view photogrammetry or neural reconstruction.

---

### 2. Core Research Questions

1. **RQ-3A.1 (Proxy Expressiveness):** Can low-parameter analytical 3D proxies (OBB with 10 DOF, Superquadrics with 11 DOF) accurately reproduce the ground-truth 3D shadow silhouette of complex consumer goods (footwear, bottles, apparel) across arbitrary lighting angles?
2. **RQ-3A.2 (Non-Planar Receiver Transport):** How accurately can analytical cone tracing onto a parametric curved cyclorama cove model ($Y = f(Z)$) eliminate the $12.66\%$ silhouette leakage observed in S11?
3. **RQ-3A.3 (Detail Blending & Boundary Hybridization):** How can high-frequency silhouette details from the 2.5D photographic mask (e.g. shoelace tips, sneaker tread lugs) be blended seamlessly with the smooth shadow cast by the 3D parametric proxy without causing boundary tearing or double-shadow artifacts?
4. **RQ-3A.4 (Performance & Throughput):** Can proxy fitting and analytical cone tracing execute within $< 4.0\text{ ms}$ on Apple Silicon Metal at 1080p?

---

### 3. Mathematical Foundations

```
                            PARAMETRIC PROXY SHADOW GEOMETRY
                            
                    Light Source (x_L, y_L, z_L), Radius R_source
                                  *
                                 / \
                                /   \
                               /     \  Umbra / Penumbra Cone
                              /       \
                             /  +---+  \
                            /   | 3D|   \  Parametric Proxy P_3D
                           /    |   |    \ (OBB / Superquadric)
                          /     +---+     \
                         /                 \
     -------------------/-------------------\----------------- Parametric Receiver
                       /                     \
                      +======= Umbra ========+  Cast Shadow Area
                      <--- Penumbra Ring --->
```

#### 3.1 Analytical 3D Proxy Representations
1. **Oriented Bounding Box (OBB):**
   Defined by center $\mathbf{c} \in \mathbb{R}^3$, half-extents $\mathbf{e} = [e_x, e_y, e_z]$, and orientation matrix $\mathbf{R} \in SO(3)$.
   Ray intersection computed via the Kay-Kajiya slab method in local proxy coordinates $\mathbf{x}' = \mathbf{R}^T (\mathbf{x} - \mathbf{c})$:
   $$t_{\text{near}} = \max_i \left( \min(t_{i, 1}, t_{i, 2}) \right), \quad t_{\text{far}} = \min_i \left( \max(t_{i, 1}, t_{i, 2}) \right)$$
2. **Superquadric Ellipsoid:**
   Implicit surface defined in canonical space by:
   $$\mathcal{F}(x, y, z) = \left( \left| \frac{x}{r_x} \right|^{\frac{2}{\epsilon_2}} + \left| \frac{y}{r_y} \right|^{\frac{2}{\epsilon_2}} \right)^{\frac{\epsilon_2}{\epsilon_1}} + \left| \frac{z}{r_z} \right|^{\frac{2}{\epsilon_1}} = 1$$
   Where $\epsilon_1$ controls vertical squareness and $\epsilon_2$ controls horizontal squareness.
   For standard ellipsoids ($\epsilon_1 = \epsilon_2 = 1.0$), intersection along ray $\mathbf{p}(t) = \mathbf{o} + t \mathbf{d}$ is solved in closed form:
   $$A t^2 + 2 B t + C = 0 \implies \Delta = B^2 - A C$$

#### 3.2 Parametric Receiver Modeling (Curved Cyclorama Cove)
The studio backdrop is modeled as a continuous, differentiable surface:
$$Y_{\text{receiver}}(Z) = \begin{cases} Y_{\text{floor}} & Z \le Z_{\text{cove\_start}} \\ Y_{\text{floor}} + R_c - \sqrt{R_c^2 - (Z - Z_{\text{cove\_start}})^2} & Z_{\text{cove\_start}} < Z < Z_{\text{cove\_start}} + R_c \\ Y_{\text{floor}} + R_c + (Z - Z_{\text{cove\_end}}) \tan \theta_{\text{wall}} & Z \ge Z_{\text{cove\_start}} + R_c \end{cases}$$
Intersecting a light ray with this profile reduces to solving a 1D quadratic root on the circular fillet section, enabling exact analytical shadow placement on curved photography sweeps.

#### 3.3 Hybrid Silhouette Detail Displacement
To preserve fine photographic silhouettes that exceed the proxy's geometry, the candidate shadow visibility is formulated as:
$$V_{\text{hybrid}}(x, y) = V_{\text{proxy}}^{3D}(x, y) \cdot \left[ 1.0 - \delta_{\text{detail}}(x, y) \right]$$
Where $\delta_{\text{detail}}$ is the signed distance field of the 2.5D photographic boundary re-projected along the light vector in the near-contact region ($d_{\text{contact}} < 30\text{ px}$).

---

### 4. Experimental Methodology & Test Manifest

The prototype will be built strictly within `spike3a/` and evaluated against ground-truth 3D Monte Carlo ray tracing across 15 test configurations:

| Category | Test Scene | Geometry & Configuration | Ground Truth Verification Target |
| :--- | :--- | :--- | :--- |
| **Planar Ground** | **S1_grounded_sphere** | Spherical primitive resting on flat floor | Validate baseline equivalence ($SDE \le 1.0\text{ px}$) |
| **Hovering Sweep** | **S2_hovering_sphere** | Elevation sweep: $h = 0.05, 0.20, 0.50$ | Verify shadow detachment gap ($SDE \le 2.0\text{ px}$ at $h=0.50$) |
| **Prismatic Box** | **S3_step_box_90deg** | Sharp 90-degree step box with grazing key light | Verify OBB slab intersection ($SDE \le 1.5\text{ px}$) |
| **Complex Hull** | **S4_shoe_hull** | Organic footwear hull with arched midsole | Verify superquadric proxy fit ($\text{IoU} \ge 0.90$) |
| **Curved Backdrop** | **S11_curved_cyclorama** | Sphere + Box on curved cyclorama cove | Eliminate cyclorama leakage ($SLR \le 1.0\%$, $SDE \le 2.0\text{ px}$) |
| **Multi-Camera** | **S12_multi_cam_pitch** | Pitch sweep: $15^\circ$ (eye), $45^\circ$ (studio), $85^\circ$ (top) | Validate perspective invariance across all angles |
| **Photographic** | **R1_sneaker** | Real footwear on studio floor | Contact grounding + cast shadow without tread bleed |
| **Photographic** | **R2_classical_statue** | Real sculpture on pedestal | Validate multi-part proxy fit on organic structure |

---

### 5. Quantitative Acceptance Gates

| Diagnostic Metric | Spike 2.2 Baseline (Failed) | Spike 3A Target Gate | Critical Significance |
| :--- | :---: | :---: | :--- |
| **Shadow Distance Error ($SDE$)** | $13.4\text{ px}$ | **$\le 2.0\text{ px}$** | Centroid error against true 3D ray tracing |
| **Intersection over Union ($\text{IoU}$)** | $0.521$ | **$\ge 0.90$** | Silhouette overlap against 3D ground truth |
| **Silhouette Leakage Rate ($SLR$)** | $12.66\%$ (Cyclo) | **$\le 1.0\%$** | Eliminates shadow spill on lit background walls |
| **Shadow Detachment Gap ($SDG$)** | $48.33\text{ px}$ ($h=0.5$) | **Monotonic $\le 1.5\text{ px}$ error** | Accurate shadow detachment for hovering subjects |
| **Contact Grounding ($CGS$)** | $0.0616$ (Photo: $0.19$) | **$\le 0.10$** | Sharp, grounded interface at supporting plane |
| **Latency Budget (1080p Metal)** | N/A | **$\le 4.0\text{ ms}$** | GPU proxy fitting and cone tracing throughput |

---

### 6. Dependencies, Risks & Mitigation Strategies

1. **Risk 1: Proxy Fitting Ambiguity from Monocular Depth**
   - *Risk:* A monocular depth map has missing back faces; fitting an unconstrained ellipsoid might produce incorrect depth thickness.
   - *Mitigation:* Constrain proxy fitting using bilateral symmetry priors and ground-plane bounding planes.
2. **Risk 2: Boundary Seams between 2.5D Details and 3D Proxy**
   - *Risk:* Hard transitions between proxy cone tracing and screen-space contact grounding.
   - *Mitigation:* Smooth Hermite blending driven by distance-to-contact $w_{\text{contact}} = \text{SmoothStep}(0, 25\text{ px}, d)$.
3. **Dependencies:**
   - Requires independent 3D reference ray tracer from Spike 2.2 (`spike2_2_reference_renderer.py`).
   - Strictly decoupled from Spike 3B (Specular PBR) and Metal-2.

---

### 7. Expected Deliverables

- `spike3a/spike3a_proxy_engine.py`: Analytical 3D proxy ray tracer and cyclorama receiver solver.
- `spike3a/spike3a_evaluation.py`: Quantitative verification harness against ground-truth 3D ray tracing.
- `docs/spike3a/RS-REP-SPIKE-3A-RESULTS.md`: Empirical results report and metric verification table.
- `docs/spike3a/RS-DECISION-SPIKE-3A.md`: Formal milestone ratification.
