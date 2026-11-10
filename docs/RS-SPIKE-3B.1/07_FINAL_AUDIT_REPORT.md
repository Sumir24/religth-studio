# RELIGHT STUDIO — RS-SPIKE-3B.1 MASTER AUDIT REPORT
# 07: INDEPENDENT EVIDENCE AUDIT & PHOTOGRAPHIC FIDELITY VERIFICATION

**Audit Authority:** Principal Computational Photography Engineer, Independent Rendering Auditor, Applied Mathematics Researcher, and Metal GPU Performance Engineer  
**Date:** November 10, 2026  
**Audited Checkpoint:** `efed4ed` (`feat(RS-SPIKE-3B): Geometric Lighting Fidelity & Scene Interaction validation complete (UNCONDITIONAL PASS)`)  
**Audit Branch:** `audit/RS-SPIKE-3B.1`  
**Final Audit Verdict:** **CONDITIONAL PASS**  

---

## 1. EXECUTIVE SUMMARY & FORMAL AUDIT VERDICT

Milestone **RS-SPIKE-3B** achieved major engineering advances, delivering a functional interactive 3D studio lighting environment powered by a native Apple Silicon Metal compute pipeline, parametric superquadrics, curved cyclorama cove geometry, and non-destructive image compositing. In its final report (`docs/RS-SPIKE-3B/06_FINAL_REPORT.md`), it declared an **UNCONDITIONAL PASS**.

Following a thorough, evidence-first forensic audit across mathematics, shadow optics, GPU hardware profiling, and photographic fidelity, this audit formally **downgrades the milestone verdict from UNCONDITIONAL PASS to CONDITIONAL PASS**.

### Primary Audit Findings:
1. **The "1.0000 Parity" Misclassification:**
   The reported `Soft IoU = 1.0000` and `SDE = 0.00 px` represented **backend implementation parity (Metal GPU vs CPU reference)**, where both backends executed identical numerical logic. It did **not** represent physical accuracy against an independent ground-truth shadow. When measured against an independent $N=256$ Monte Carlo double-precision reference, the true shadow accuracy achieves a solid, realistic **$\text{Soft IoU} = 0.9099$** and sub-2-pixel contour displacement ($1.42\text{ px}$), but it is not 1.0000.
2. **Missing E.1 Guided-Filter Regularizer in Metal & P1 Sneaker Failure:**
   The native Metal compute shader (`metal2/shaders/renderer.metal`) omits the E.1 Guided-Filter Regularization developed in Spike 1, executing naive multiplicative relighting. Consequently, when relighting the complex footwear plate (`P1_nike_sneaker`), the subject foreground detail preservation index drops to **$\mathbf{0.8282}$ (FAIL)** against the $\ge 0.88$ acceptance threshold. This failure was masked in RS-SPIKE-3B by averaging across the large flat background.
3. **Superquadric Metric Classification:**
   The normalized metric $G(p) = (F(p) + 1)^{e_1/2} - 1$ is mathematically proved to be a **radially homogeneous degree-1 algebraic distance metric**, **not an exact Euclidean Signed Distance Function (SDF)**. It provides excellent root-bracketing stability and bounds floating-point growth linearly, achieving $98.4\% - 100.0\%$ ray-hit agreement and $0.001 - 0.037\text{ mm}$ spatial accuracy against a double-precision Brent root solver.
4. **The "34x Latency Variance" Explained:**
   The apparent $34\times$ latency spread ($0.41\text{ ms}$ to $22.08\text{ ms}$) was an artifact of comparing different image resolutions ($256 \times 384$ vs $576 \times 1024$) and sample counts ($N=9$ vs $N=64$). Under standardized Full HD 1080p conditions, raw GPU execution is remarkably stable ($4.67\text{ ms}$ to $7.00\text{ ms}$, running at $143 - 214\text{ FPS}$). However, **$78\% - 94\%$ of end-to-end frame latency is consumed by host CPU overhead** ($116\text{ MB/frame}$ shared memory allocation and CPU canvas copies).
5. **Verified Capabilities:**
   Bitwise zero-mutation on protected regions (`max diff = 0.0000000000`), deterministic JSON scene state replay (`max diff = 0.0000000000`), and all 51 automated regression tests pass with 100% integrity.

---

## 2. COMPREHENSIVE AUDIT SCORECARD

| Evaluation Area | RS-SPIKE-3B Claim | Independent Audit Finding | Formal Audit Verdict |
| :--- | :--- | :--- | :---: |
| **Superquadric Mathematics** | Exact SDF with linear growth | Radially homogeneous algebraic metric ($G(\alpha p) = \alpha G(p)$), not an orthogonal Euclidean SDF. Bounds float32 values ($G \approx 1.87$ at $2\times$ radius). | **QUALIFIED PASS** |
| **Superquadric Solver Parity** | 100% numerically stable | 98.4%–100% hit agreement vs double-precision Brent solver; distance MAE $0.001 - 0.037\text{ mm}$; fixed float32 gradient squaring overflow. | **PASS** |
| **Shadow Transport Fidelity** | Soft IoU 1.0000, SDE 0.00 px | Artifact of comparing identical CPU vs Metal code. True accuracy vs independent $N=256$ Monte Carlo: Soft IoU $0.9099$, Contour Disp $1.42\text{ px}$. | **CONDITIONAL PASS** |
| **Sphere Proxy Modeling** | Analytical spherical subject | No native sphere primitive in data model. Approximating sphere via OBB causes $134.7\%$ shadow area error. Spheres must use Superquadric $e=1.0$. | **FAIL (OBB) / PASS (SQ)** |
| **Performance Reconciliation** | 0.41–22.08 ms ($34\times$ variance) | Uncontrolled benchmark artifact (resolution/sample mismatch). Controlled 1080p GPU time is $4.67 - 7.00\text{ ms}$ ($143 - 214\text{ FPS}$). | **PASS** |
| **Host vs GPU Architecture** | Not analyzed | $78\% - 94\%$ of end-to-end frame time spent on host CPU allocations ($116\text{ MB/frame}$) and synchronous pipeline drains. | **ARCHITECTURAL FINDING** |
| **Photographic Fidelity** | DCI $0.8941 - 0.9995$ (`PASS`) | Whole-image metric diluted by flat background. Footwear plate foreground DCI is **$0.8282$ (FAILED)** due to omission of E.1 in Metal shader. | **CONDITIONAL PASS** |
| **Zero-Mutation Immutability** | Max Diff: 0.0000000000 | Verified genuine bitwise equality on real photographic pixels via direct shader branch bypass. | **PASS** |
| **Deterministic Replay** | Replay Diff: 0.0000000000 | Verified exact bitwise reproduction across all 5 geometry/receiver scene configurations. | **PASS** |
| **Regression Test Suite** | 51 passing tests | 51/51 tests pass in $4.88\text{ s}$ with zero skips, zero mocks, zero xfails. Identified empty `test_v5_engine.py`. | **PASS** |

---

## 3. DETAILED TECHNICAL FINDINGS

### 3.1. Superquadric Metric Characterization
- **Metric Identity:**
  $$G(p) = \rho(p) - 1 = \left( \left(\left|\frac{x}{r_x}\right|^{2/e_2} + \left|\frac{y}{r_y}\right|^{2/e_2}\right)^{e_2/e_1} + \left|\frac{z}{r_z}\right|^{2/e_1} \right)^{e_1/2} - 1$$
- **Proof of Homogeneity:** Along any radial ray $p(t) = t \hat{d}$, $G(t \hat{d}) = t \, \rho(\hat{d}) - 1$. This guarantees that $G(p)$ grows strictly linearly ($O(t)$), completely eliminating the float32 exponential overflow inherent to raw inside-outside function $F(p)$.
- **Non-SDF Proof:** For non-spherical shapes, $|\nabla G(p)| \neq 1.0$ away from the surface. In corners and high-curvature zones ($e_1, e_2 \le 0.3$), $|\nabla G(p)|$ scales inversely with local curvature. Thus, $G(p)$ cannot be used as a distance-bounding sphere-tracer; it must be solved via interval bracketing and bisection.
- **Float32 Normal Vector Repair:** For $e_1 \le 0.1$, the analytical gradient exponent $(2/e_1 - 1) \ge 19.0$ produced values exceeding $10^{19}$, causing `np.linalg.norm` to square to $> 10^{38}$ (overflowing float32). This was repaired by pre-scaling gradient components by $\max(|g_x|, |g_y|, |g_z|)$ prior to normalization.

### 3.2. True Shadow Accuracy vs Implementation Parity
- **The Parity Illusion:** Both CPU and Metal implementations shared identical 64-sample stratified grid layouts, identical cell centers, and identical float32 ray-box intersection algorithms. Comparing them yielded $\text{Soft IoU} = 1.0000$.
- **Ground Truth Evaluation:** Decoupled from the engine, an independent reference generator was built using $N=256$ Monte Carlo stratified jittered samples in double precision (`float64`).
- **Results:**
  - OBB on Plane: $\text{Soft IoU} = 0.8470$, Contour Disp $= 2.52\text{ px}$.
  - Rounded Box Superquadric: $\text{Soft IoU} = 0.9613$, Contour Disp $= 0.52\text{ px}$.
  - Bottle on Cyclorama: $\text{Soft IoU} = 0.9210$, Contour Disp $= 1.27\text{ px}$.
  - Grazing Light (15°): $\text{Soft IoU} = 0.9068$, Contour Disp $= 1.60\text{ px}$.
  - Large Softbox ($1.0\text{ m}$): $\text{Soft IoU} = 0.9075$, Contour Disp $= 1.25\text{ px}$.
- **Sphere Proxy Anomaly:** The data model lacks an analytical sphere proxy. Attempting to represent a sphere via an OBB causes a catastrophic $134.7\%$ shadow area error ($4,490\text{ px}$ vs $1,913\text{ px}$). Spherical objects must be modeled with Superquadrics ($e_1=1.0, e_2=1.0$).

### 3.3. Performance Reconciliation & Host Bottlenecks
- **GPU Kernel Throughput:** On Apple M5, raw GPU execution is exceptionally fast:
  - 576p Preview: $0.56 - 0.90\text{ ms}$ ($> 1,100\text{ FPS}$).
  - 1080p Final (64 samples): $4.67 - 7.00\text{ ms}$ ($143 - 214\text{ FPS}$).
- **Host Bottlenecks:** End-to-end host latency at 1080p reaches $27 - 34\text{ ms}$ ($29 - 37\text{ FPS}$). Profiling reveals that $81.2\%$ of frame time is spent on:
  - Per-frame allocation of 6 shared UMA buffers ($116.2\text{ MB/call}$): $9.2\text{ ms}$.
  - Redundant C++ `memcpy` of output buffers ($58.2\text{ MB}$): $4.5\text{ ms}$.
  - CPU-bound OpenCV canvas copy in `_generate_proxy_overlay`: $7.0\text{ ms}$ (spiking to $46\text{ ms}$ under unoptimized paths).
  - Synchronous pipeline stall (`waitUntilCompleted`): $3.8\text{ ms}$.

### 3.4. Photographic Fidelity & Missing E.1 Filter
- **Whole-Image DCI vs Foreground DCI:**
  - Plate P1 (Nike Sneaker): Whole-image $\text{DCI} = 0.8941$, but **Foreground $\text{DCI} = 0.8282$ (FAILED)**.
  - Plate P2 (Statue): Whole-image $\text{DCI} = 0.9971$, Foreground $\text{DCI} = 0.9968$ (`PASS`).
  - Plate P3 (Relief): Whole-image $\text{DCI} = 0.9876$, Foreground $\text{DCI} = 0.9963$ (`PASS`).
- **Missing E.1 Filter:** In `metal2/shaders/renderer.metal`, relighting is executed as naive multiplication: $\mathbf{I}_{\text{relit}} = \mathbf{I}_{\text{orig}} \cdot (\mathbf{E} \cdot V + 0.15)$. The E.1 Guided-Filter Regularization was never ported to Metal shaders. Noisy monocular depth normals directly modulate fine textures, inducing noticeable "texture crunch" on the footwear knit.

---

## 4. WHAT CAN BE TRUSTED VS WHAT MUST BE QUALIFIED

### Trusted Without Reservation:
1. **Mathematical Stability of Superquadric Primitives:** Zero NaNs, zero infinities, bounded linear growth, and sub-$40\,\mu\text{m}$ spatial precision.
2. **Apple Silicon Metal Kernel Performance:** Raw GPU shading at Full HD 1080p runs at $> 140\text{ FPS}$ with 64 physical shadow samples.
3. **Protected Region Zero-Mutation:** Genuine bitwise immutability (`0.0000000000` delta) on real photographic pixels.
4. **Deterministic Scene State Replay:** Perfect JSON serialization roundtrip (`0.0000000000` delta).
5. **Cyc Cove Geometry:** Seamless fillet curvature with exact receiver self-shadowing.

### Qualified Capabilities:
1. **Shadow Accuracy:** Must be quoted as $\approx 91\%$ Soft IoU and $\approx 1.4\text{ px}$ contour displacement against Monte Carlo ground truth, NOT 1.0000.
2. **Sphere Proxy Usage:** Only supported via Superquadric ($e_1=1.0, e_2=1.0$). OBB proxies must never be assigned to spherical subjects.
3. **Photographic Detail Preservation:** Only verified for smooth organic surfaces (P2) and flat reliefs (P3). Complex textured geometry (P1) requires E.1 guided-filter restoration before production release.
4. **Application Frame Rate:** Currently $30\text{ FPS}$ at 1080p due to Python/C++ memory allocation overhead, despite $> 140\text{ FPS}$ GPU capability.
