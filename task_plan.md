# RS-PRODUCT-1.1 Task Plan: Interactive Scene, Real-Time Lighting & Photographic Control

**Role:** Principal macOS Application Architect, Senior 3D Interaction Engineer, Metal Rendering Engineer, Computational Photography Specialist, Product Designer, Independent QA Lead  
**Product:** Relight Studio  
**Milestone:** RS-PRODUCT-1.1  
**Baseline Checkpoint:** `27a38f8`  
**Branch:** `feature/RS-PRODUCT-1.1-interactive-scene`  
**Platform:** macOS / Apple Silicon / Metal 3  
**Execution Standard:** Evidence-first engineering. Accurate architectural classification. Direct 3D viewport interaction with real-time photograph response. Zero mock data.

---

## Phase 0: Baseline Audit & Discrepancy Reconciliation
- [ ] 0.1 Inspect checkpoint `27a38f8`, verify the 14 baseline aspects.
- [ ] 0.2 Resolve Discrepancy A: Application architecture (local web-based application served via FastAPI/Uvicorn, accessible via browser or desktop webview, not a native AppKit/SwiftUI binary).
- [ ] 0.3 Resolve Discrepancy B: Sample-count configuration (reconcile 32 samples per light in CPU reference / final UI requests vs 25 SPP in historical benchmarks).
- [ ] 0.4 Deliverable: Author `RS_PRODUCT_1_1_BASELINE_AUDIT.md`.

## Phase 1: Real 3D Interaction Engine
- [ ] 1.1 Direct 3D Light Selection:
  - Ray-casting / hit-testing in 3D viewport canvas for area light quads and gizmo handles.
  - Consistent selection synchronization across 3D canvas, hierarchy tree, and inspector.
- [ ] 1.2 3D Translation Gizmo ($X, Y, Z$):
  - Interactive mouse drag along projected world axes.
  - Active axis highlight and visual coordinate HUD.
  - Mutates actual world-space coordinates in authoritative scene state.
- [ ] 1.3 3D Rotation Gizmo & Euler Controls:
  - Pitch, Yaw, and Roll manipulation.
  - Normal emission vector recomputation and visual orientation cue.
  - Dynamic shadow penumbra and specular highlight updates in the photograph.
- [ ] 1.4 Light Dimensions & Scale:
  - Intuitive width and height adjustments in 3D viewport and inspector.
  - Updates physical emitting area and inverse-square / radiometric falloff.
- [ ] 1.5 Interaction Reliability:
  - Dragging safeguards: prevent camera movement during gizmo drag.
  - Transactional undo/redo grouping on drag end.

## Phase 2: Camera & Scene Navigation
- [ ] 2.1 Refine 3D Orbit, Pan, and Zoom in Stage Viewport:
  - Independent camera orbit (left drag), pan (shift drag / middle drag), and zoom (wheel).
  - Focus selected object button (centers view on active light or subject).
  - Reset camera button (returns to standard 3/4 perspective studio view).
  - Clear separation between camera navigation and gizmo picking.

## Phase 3: Subject & Receiver Interaction
- [ ] 3.1 Subject Proxy Selection & Control:
  - Select subject proxy in 3D viewport or hierarchy.
  - Adjust proxy type (OBB, Superquadric, Mesh), dimensions ($X, Y, Z$), and ground elevation.
  - Synchronous photograph update with geometry-dependent contact occlusion and shadow casting.
- [ ] 3.2 Receiver Geometry Selection & Control:
  - Select receiver in 3D viewport or hierarchy.
  - Adjust receiver type (Floor Plane vs Cyclorama Cove), cove radius, and wall $Z$.
  - Reflect curvature in 3D stage and photographic contact shadow.

## Phase 4: Photographic Viewport & 3D Stage Synchronization
- [ ] 4.1 Real-Time Synchronization Pipeline:
  - Ensure every light move, rotation, resize, intensity, color, roughness, environment rotation, and proxy transform updates the photograph immediately.
  - Stale-frame rejection: in-flight intermediate renders are cancelled when new state arrives.
- [ ] 4.2 Before / After Split Wipe & Inspection:
  - Draggable split wipe slider across original plate and relit image.
  - 1:1 pixel inspect, fit-to-screen, and smooth pan/zoom.

## Phase 5: Dynamic Preview Quality & Lighting Presets
- [ ] 5.1 Dynamic Preview Policy:
  - Fast, responsive $1024 \times 576$ preview during active dragging ($>190\,\text{FPS}$).
  - Progressive quality render once interaction settles ($250\,\text{ms}$ debounce).
  - Full-resolution Final Quality render on demand.
- [ ] 5.2 Studio Lighting Presets:
  - Verified starter configurations backed by real scene values: `Key Softbox`, `Fill Softbox`, `Rim Strip`, `Top Light`, `Side Light`.

## Phase 6: Project Reliability & Persistence Hardening
- [ ] 6.1 Transactional Project Saving:
  - Atomic write via temporary directory to prevent file corruption during interrupted saves.
  - Robust missing-asset detection and fallback recovery.

## Phase 7: Validation, Visual Evidence & Final Reports
- [ ] 7.1 Author comprehensive test suite in `tests/RS-PRODUCT-1.1/`.
- [ ] 7.2 Run full regression suite across all repository tests.
- [ ] 7.3 Capture 14 visual verification screenshots and interaction sequence records.
- [ ] 7.4 Deliver all required technical reports:
  - `RS_PRODUCT_1_1_IMPLEMENTATION_REPORT.md`
  - `RS_PRODUCT_1_1_INTERACTION_VALIDATION.md`
  - `RS_PRODUCT_1_1_RENDERING_VALIDATION.md`
  - `RS_PRODUCT_1_1_PERFORMANCE_REPORT.md`
  - `RS_PRODUCT_1_1_KNOWN_LIMITATIONS.md`
- [ ] 7.5 Final engineering verdict.
