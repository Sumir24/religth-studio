# RS-SPIKE-3B Task Plan: Geometric Lighting Fidelity & Scene Interaction

## Phase 0: Independent Baseline Audit
- [x] 0.1 Audit Camera Implementation:
  - Basis construction, Gram-Schmidt / orthonormalization, camera-to-world transform.
  - Test pitch angles (0°, moderate, 71.3°, near-vertical ~89.9°), camera roll (15°, 45°), non-square image dimensions (portrait 576x1024, widescreen 1920x1080).
  - Verify numerical orthogonality ($R^T R = I, \det(R) = 1.0$) across all angles.
- [x] 0.2 Audit Geometry Intersections:
  - OBB, Superquadric root solving, Triangle mesh, AABB fast-reject, Ground plane, Cyclorama cove.
  - CPU vs Metal coordinate spaces, normal orientations, grazing-angle rays, self-shadow guards.
- [x] 0.3 Audit Benchmark Authenticity:
  - GPU kernel time vs host dispatch wall time.
  - Reproduce 6-scene CPU-Metal parity.
  - Reproduce 1080p C3 Oklab kernel dispatch.
  - Reproduce 280-triangle footwear mesh execution.
  - Reproduce interactive frame times on real photograph.
- [x] 0.4 Audit Metric Correctness:
  - Continuous Soft IoU (fuzzy Jaccard), Continuous SDE (CoM), Contour displacement, Irradiance MAE, Hit agreement, Protected region zero-mutation.
- [x] 0.5 Audit Application Interaction:
  - Measure light dragging, rotation, dimensions, intensity, proxy change, receiver change, undo/redo in `studio3a/workspace.py`.
- [x] 0.6 Deliverable: Author `docs/RS-SPIKE-3B/00_BASELINE_INDEPENDENT_AUDIT.md`.

## Phase 1: Geometry Diagnosis (Workstream A)
- [x] 1.1 Superquadric root-finding investigation:
  - Root bracket search step count, bisection / secant / Newton-Raphson refinement.
  - Why cosmetic bottle (M2_03) achieved 0.8037 IoU and organic sculpture (M2_06) achieved 0.7458 IoU.
  - Exponent sensitivity ($e_1, e_2 < 0.5$ vs $> 1.0$), grazing rays, normal gradient precision.
- [x] 1.2 Mesh intersection & AABB culling investigation:
  - Triangle counts, degenerate/thin triangles, grazing rays, silhouette accuracy.
  - Measure actual bottlenecks; evaluate whether BVH / MPSRayTracing is needed or if improved AABB/OBB is sufficient.
- [x] 1.3 Shadow-ray & receiver transitions:
  - Cyclorama cove continuity, floor-to-wall shadow transition, contact grounding decoupling.
- [x] 1.4 Deliverable: Author `docs/RS-SPIKE-3B/01_GEOMETRY_FIDELITY_ANALYSIS.md`.

## Phase 2: Geometry Correction (Workstream A Implementation)
- [x] 2.1 Implement high-accuracy superquadric root solver in CPU and Metal shaders:
  - Normalized radial metric $G(p) = \rho(p) - 1.0 = (F(p) + 1)^{e_1/2} - 1.0$.
  - 32-step interval march + 4-iteration bisection + safe secant refinement.
  - Accurate analytical gradient normals avoiding numerical overflow on fractional powers.
- [x] 2.2 Enhance mesh intersection and shadow ray handling:
  - Watertight Möller-Trumbore intersection, conservative bounds, acne-free offset.
- [x] 2.3 Improve cyclorama receiver shadow transport:
  - Smooth cove curvature shadow transport without clipping at floor-wall seam ($\pm 10^{-4}$ tolerance padding).
  - Aligned superellipse contact grounding formula on Metal GPU.
- [x] 2.4 Deliverable: Author `docs/RS-SPIKE-3B/03_SHADOW_ACCURACY_REPORT.md`.

## Phase 3: Area-Light & Illumination Fidelity (Workstream B)
- [x] 3.1 Stratified Monte Carlo sampling:
  - Low-discrepancy 2D stratified grid, preview vs final sample counts, noise vs determinism.
- [x] 3.2 Radiometric energy consistency:
  - Inverse-square law ($1/d^2$), radiant power vs radiance, dimensions change exposure consistency.
  - Kelvin-to-RGB blackbody conversion consistency.
- [x] 3.3 Penumbra scaling validation:
  - Shadow softness vs emitter size, distance to occluder, distance to receiver.
  - Independent penumbra width measurement ($0.902$ scaling constant).
- [x] 3.4 Deliverable: Author `docs/RS-SPIKE-3B/02_AREA_LIGHT_VALIDATION.md` and `area_light_validation_results.json`.

## Phase 4: Workspace Interaction & Performance (Workstream C)
- [x] 4.1 Authoritative scene manipulation:
  - Sync state across inspector, photograph viewport, and 3D stage viewport.
- [x] 4.2 Light manipulation predictability:
  - Pos, rotation (pitch/yaw/roll), width, height, intensity, Kelvin, enabled toggle.
- [x] 4.3 Preview vs Final render separation:
  - Preview (fast, stratified 4 samples), Final (high-quality 32/64 samples).
- [x] 4.4 Transactional Undo/Redo:
  - Discrete state snapshots with exact replay determinism.
- [x] 4.5 Latency Profiling (P50, P95, P99):
  - At 1024x576 ($0.87$ ms GPU / $8.06$ ms Host) and 1920x1080 ($3.00$ ms GPU / $7.24$ ms final GPU).
  - Passes 60 FPS interactive budget gate.
- [x] 4.6 Deliverable: Author `docs/RS-SPIKE-3B/04_INTERACTION_PERFORMANCE_REPORT.md` and `interaction_performance_results.json`.

## Phase 5: Photographic Validation (Workstream D)
- [x] 5.1 Assemble/verify photographic validation dataset:
  - Categories: 1. Footwear (Nike Sneaker), 2. Sculpture (Classical Statue), 3. Hard-surface (Architectural Relief).
- [x] 5.2 Immutability & detail preservation:
  - Exact bitwise zero-mutation on protected regions ($0.0000000000$).
  - E.1 guided filter texture preservation and C3 Oklab gamut mapping ($0.0000\%$ out-of-gamut).
- [x] 5.3 Photographic plausibility & structured evaluation protocol:
  - Shadow direction, softness, contact grounding, contrast.
- [x] 5.4 Deliverable: Author `docs/RS-SPIKE-3B/05_PHOTOGRAPHIC_VALIDATION_REPORT.md` and `photographic_validation_results.json`.

## Phase 6: Regression, Parity & Final Documentation
- [x] 6.1 Full test suite and parity benchmark across canonical scenes:
  - 51 automated tests passing in $<5.0$s.
  - Planar IoU = $1.0000$ (Gate $\ge 0.93$), Complex IoU = $0.9116 - 1.0000$ (Gate $\ge 0.90$), SDE = $0.00 - 1.99$ px (Gate $\le 3.0$ px), Irr MAE $\le 2.5 \times 10^{-5}$ (Gate $\le 0.001$), Preview P95 = $1.02$ ms GPU / $8.06$ ms Host (Gate $\le 16.6$ ms).
- [x] 6.2 Deliverables:
  - `docs/RS-SPIKE-3B/06_REGRESSION_AND_PARITY_REPORT.md`
  - `docs/RS-SPIKE-3B/07_FINAL_VALIDATION_REPORT.md`
  - `docs/RS-SPIKE-3B/08_NEXT_MILESTONE_RECOMMENDATION.md`
  - `docs/RS-SPIKE-3B/benchmark_results.json`
  - `docs/RS-SPIKE-3B/benchmark_results.csv`
- [x] 6.3 Milestone complete with UNCONDITIONAL PASS.
