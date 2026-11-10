# RS-PRODUCT-1.0 Task Plan: Artist-Controlled Virtual Lighting Studio

**Role:** Principal macOS Application Architect, Staff Rendering Engineer, Senior Interaction Designer, Metal Engineer, Product Designer, Technical Project Lead  
**Product:** Relight Studio  
**Primary Milestone:** RS-PRODUCT-1.0 — Studio Workspace  
**Baseline Checkpoint:** `9ad1118` (RS-SPIKE-3C.3 completed)  
**Branch:** `feature/RS-PRODUCT-1.0-studio-workspace`  
**Platform:** macOS / Apple Silicon  
**Execution Standard:** Evidence-first engineering. Ground truth verification. Real application architecture with zero mock data. Professional studio UI with non-destructive guarantees.

---

## Phase 0: Repository Discovery & Architecture Audit
- [ ] 0.1 Deep inspection of existing repository: Metal pipeline, scene models, workspace controller, camera, geometry, lighting, materials, environment, reconstruction, and test suites.
- [ ] 0.2 Author `RS_PRODUCT_1_0_ARCHITECTURE_AUDIT.md`: Document current architecture, reusable components, missing application infrastructure, state management, persistence, performance constraints, and technical risks.
- [ ] 0.3 Author `RS_PRODUCT_1_0_IMPLEMENTATION_PLAN.md`: Document execution sequence, component dependencies, and acceptance criteria.

## Phase 1: Bounded Rendering Readiness Verification (RS-SPIKE-3C.3.1)
- [ ] 1.1 Verify GGX remediation remains intact.
- [ ] 1.2 Verify environment lighting CPU–Metal parity.
- [ ] 1.3 Verify existing E.1 guided-filter reconstruction path remains functional.
- [ ] 1.4 Verify direct + environment illumination energy conservation ($k_d + F_0 \le 1.0$) and non-double-counting additivity.
- [ ] 1.5 Verify protected-region zero-mutation ($0.0000000000$).
- [ ] 1.6 Audit photographic comparison boards and 1080p host wall-clock latency characteristics.
- [ ] 1.7 Author `RS_PRODUCT_1_0_RENDERING_READINESS.md`.

## Phase 2: RS-PRODUCT-1.0A — Core Application Architecture & Studio Workspace
- [ ] 2.1 Design and implement application package structure (`relight_studio/`):
  - Application controller (`relight_studio/controller.py`)
  - Project management & `.relight` bundle specification (`relight_studio/project.py`)
  - Rendering orchestrator with async worker and stale-frame cancellation (`relight_studio/orchestrator.py`)
  - Workspace UI server / client architecture (`relight_studio/server.py` & web assets)
- [ ] 2.2 Build the professional Dark Studio UI:
  - Photograph Viewport (Zoom, pan, fit-to-screen, before/after wipe, mode selection, live preview)
  - 3D Virtual Studio Viewport (Camera orbit/pan/zoom, ground/cove grid, subject proxy, area lights, selection & gizmo)
  - Scene Hierarchy Panel (Tree view, object selection, rename, toggle visibility, add/remove lights)
  - Context Inspector Panel (Exact parameter controls for Light, Material, Environment, Camera, Project)

## Phase 3: RS-PRODUCT-1.0B — Photograph & Project Workflow
- [ ] 3.1 Implement Project Creation, Photograph Import, and Metadata Extraction:
  - Support standard photographic formats (JPEG, PNG, TIFF, WebP).
  - Extract dimensions, color profiles, and maintain immutable source references.
  - Implement project bundle format (`.relight` bundle with `project.json` and asset links).
- [ ] 3.2 Implement Save, Load, and Recent Projects:
  - Serialize full authoritative scene state, camera, proxy, receiver, lights, materials, environment, render settings.
  - Non-destructive image guarantees: original photograph is never modified.
  - Reopen and deterministic reload validation.

## Phase 4: RS-PRODUCT-1.0C — Scene & Interaction Integration
- [ ] 4.1 Unify Authoritative Scene State between 3D Viewport, Photograph Viewport, Scene Tree, and Inspector.
- [ ] 4.2 Implement Light Selection and Interactive Manipulation:
  - Click-to-select in 3D viewport and scene hierarchy.
  - Interactive transform gizmo (Translate X/Y/Z, Rotate Pitch/Yaw/Roll, Scale Width/Height).
  - Multi-light management: Add new light, duplicate light, remove light, toggle emission, toggle shadow.
- [ ] 4.3 Implement Transactional Undo / Redo:
  - Multi-level history stack with state diffing and deterministic replay.

## Phase 5: RS-PRODUCT-1.0D — Live Rendering Integration
- [ ] 5.1 Connect Metal GPU pipeline (`MetalRenderBackend`) with CPU fallback (`RenderBackend`).
- [ ] 5.2 Implement Dual-Mode Rendering:
  - Interactive Preview Mode: Responsive 1024x576 rendering at high frame rates.
  - Final Quality Mode: Full resolution, high-sample Monte Carlo, deterministic export.
- [ ] 5.3 Implement Render Queue & Stale-Frame Cancellation:
  - Ensure fast mouse dragging generates smooth previews without request backlogs.
  - Discard outdated intermediate frames asynchronously.

## Phase 6: RS-PRODUCT-1.0E — Validation, Testing & Deliverables
- [ ] 6.1 Author comprehensive automated test suite (`tests/RS-PRODUCT-1.0/`):
  - Application architecture & state tests
  - Project workflow & serialization tests
  - Interaction & gizmo tests
  - Live rendering & async orchestrator tests
  - Non-destructive image preservation tests
- [ ] 6.2 Capture visual screenshots of all 10 required states:
  1. Empty application workspace
  2. New project
  3. Imported photograph
  4. Photograph viewport
  5. 3D scene viewport
  6. Scene hierarchy
  7. Light inspector
  8. Light selection and transformation
  9. Relit photograph
  10. Saved and reopened project
- [ ] 6.3 Benchmark application responsiveness, end-to-end latency, and memory stability.
- [ ] 6.4 Author remaining reports:
  - `RS_PRODUCT_1_0_IMPLEMENTATION_REPORT.md`
  - `RS_PRODUCT_1_0_VALIDATION_REPORT.md`
  - `RS_PRODUCT_1_0_PERFORMANCE_REPORT.md`
- [ ] 6.5 Deliver final milestone summary and verdict.
