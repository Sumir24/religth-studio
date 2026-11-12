# RELIGHT STUDIO — RS-PRODUCT-1.2.1
## Persistence, Asset Handling & Regression Test Report

**Auditor:** Product Reliability Auditor & Quality Assurance Architect  
**Milestone:** RS-PRODUCT-1.2.1  
**Status:** PASS (186/186 Tests Passing, 0 Regressions)  

---

## 1. Executive Summary

This audit validates that project persistence, bundle serialization, schema migrations, and non-destructive image preservation function reliably, and that all automated tests across the repository pass without regressions.

---

## 2. Persistence & Migration Invariants

### 2.1 Project Schema Versioning
- **Active Schema:** `1.2.0`.
- **Legacy Migration Support:**
  - Projects from `1.0.0` and `1.1.0` load transparently without crash or data loss.
  - Missing parameters receive documented defaults:
    - `camera.focal_length_mm` defaults to $50.0\,\text{mm}$.
    - `receiver.cove_radius` defaults to $0.20\,\text{m}$.
    - `subject.rotation_deg[2]` (Roll) defaults to $0.0^\circ$.

### 2.2 Atomic Transactional Saving
- Bundle writes use atomic temporary directory assembly before replacing target `.relight` bundle:
  - `manifest.json` with SHA-256 hash of original plate.
  - `scene.json` with full scene graph serialization.
  - Isolated copy of original photograph in `source/original_image.jpg`.
- Prevents bundle corruption in case of unexpected process termination.

### 2.3 Explicit Missing Asset Handling
- When an asset (e.g. source image or depth map) is deleted externally from the filesystem:
  - `is_missing_assets` flag is set to `True`.
  - The UI displays an explicit error status pill: `MISSING ASSETS: original_image.jpg`.
  - The system does NOT silently invent or substitute a neutral grey placeholder.

---

## 3. Full Repository Regression Test Results

Executed full pytest suite: `PYTHONPATH=. .venv/bin/pytest tests/`

```
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sumirdayal/religth studio
collected 186 items

tests/RS-PRODUCT-1.0/test_app_controller_state.py .....                  [  2%]
tests/RS-PRODUCT-1.0/test_interaction_synchronization.py .....           [  5%]
tests/RS-PRODUCT-1.0/test_nondestructive_guarantees.py ...               [  6%]
tests/RS-PRODUCT-1.0/test_project_and_bundle.py ...                      [  8%]
tests/RS-PRODUCT-1.0/test_rendering_orchestrator.py ...                  [ 10%]
tests/RS-PRODUCT-1.1/test_dynamic_preview_quality.py ..                  [ 11%]
tests/RS-PRODUCT-1.1/test_gizmo_and_picking.py .....                     [ 13%]
tests/RS-PRODUCT-1.1/test_lighting_presets.py ...                        [ 15%]
tests/RS-PRODUCT-1.1/test_server_endpoints.py ......                     [ 18%]
tests/RS-PRODUCT-1.1/test_subject_receiver_control.py ...                [ 20%]
tests/RS-PRODUCT-1.1/test_transactional_persistence.py ..                [ 21%]
tests/RS-PRODUCT-1.2/test_alignment_diagnostics.py ....                  [ 23%]
tests/RS-PRODUCT-1.2/test_alignment_persistence.py ..                    [ 24%]
tests/RS-PRODUCT-1.2/test_camera_matching.py .....                       [ 27%]
tests/RS-PRODUCT-1.2/test_product_1_2_endpoints.py ......                [ 30%]
tests/RS-PRODUCT-1.2/test_receiver_alignment.py ...                      [ 32%]
tests/RS-PRODUCT-1.2/test_subject_geometry_editing.py ........           [ 36%]
tests/RS-SPIKE-3A/camera/test_camera.py ....                             [ 38%]
tests/RS-SPIKE-3A/geometry/test_geometry.py .......                      [ 42%]
tests/RS-SPIKE-3A/lighting/test_lighting.py ....                         [ 44%]
tests/RS-SPIKE-3A/reconstruction/test_reconstruction.py ...              [ 46%]
tests/RS-SPIKE-3A/renderer/test_renderer_repairs.py ....                 [ 48%]
tests/RS-SPIKE-3A/scene_state/test_scene_state.py ....                   [ 50%]
tests/RS-SPIKE-3A/shadows/test_shadows.py ..                             [ 51%]
tests/RS-SPIKE-3B/test_spike3b_regressions.py ....                       [ 53%]
tests/RS-SPIKE-3C/test_spike3c_regressions.py .......                    [ 57%]
tests/RS-SPIKE-3C.1/test_spike3c1_multilight.py ............             [ 63%]
tests/RS-SPIKE-3C.2/test_artist_interaction.py .....                     [ 66%]
tests/RS-SPIKE-3C.2/test_brdf_foundation.py ......                       [ 69%]
tests/RS-SPIKE-3C.2/test_brdf_validation.py ........                     [ 74%]
tests/RS-SPIKE-3C.2/test_material_model.py .....                         [ 76%]
tests/RS-SPIKE-3C.3/test_direct_ibl_energy_accounting.py .....           [ 79%]
tests/RS-SPIKE-3C.3/test_environment_model.py .....                      [ 82%]
tests/RS-SPIKE-3C.3/test_ibl_metal_parity.py ......                      [ 85%]
tests/RS-SPIKE-3C.3/test_photographic_ibl_integration.py ....            [ 87%]
tests/RS-SPIKE-3C.3/test_uncertainty_and_artist_controls.py .....        [ 90%]
tests/audit_3c21/test_adversarial_brdf.py ......                         [ 93%]
tests/test_pbr_engine.py ..                                              [ 94%]
tests/test_v3_engine.py .....                                            [ 97%]
tests/test_v5_engine.py .....                                            [100%]

======================== 186 passed in 68.51s (0:01:08) ========================
```

- Total Tests Passing: **186**
- Total Tests Failing: **0**
- Total Regressions: **0**
- Test Coverage Status: **100% PASS**

