# RELIGHT STUDIO — RS-SPIKE-3B.1 AUDIT DELIVERABLE
# 06: REGRESSION AND REPRODUCIBILITY AUDIT

**Author:** Principal Software Quality Architect & Independent Systems Auditor  
**Date:** November 10, 2026  
**Audited Checkpoint:** `efed4ed` (RS-SPIKE-3B)  
**Execution Environment:** macOS Darwin 24 (arm64, Apple M5), Python 3.14.6, Metal 3.0  
**Test Framework:** Pytest 9.2.0, Pluggy 1.7.0  

---

## 1. AUTOMATED REGRESSION TEST SUITE EXECUTION

The complete automated test suite was executed against the audited checkpoint:
```bash
PYTHONPATH=. ./.venv/bin/pytest -v
```

### 1.1. Summary Scorecard
- **Total Tests Collected:** 51
- **Passed:** 51
- **Failed:** 0
- **Errors:** 0
- **Skipped:** 0 (zero mocks, zero skips)
- **Expected Failures (xfail):** 0
- **Total Execution Time:** **4.88 seconds**
- **Test Integrity:** Every test executes against concrete numerical solvers, native Metal shared libraries, or live image buffers. Zero mock objects are utilized.

### 1.2. Test Breakdown by Subsystem

| Subsystem / Test Module | Test Count | Pass Rate | Key Capabilities Verified |
| :--- | :---: | :---: | :--- |
| `metal2/tests/test_math_parity.py` | 4 | 100% | Sky masking parity, CPU vs Metal irradiance parity, bitwise zero-mutation, P95 latency bounds. |
| `metal2/tests/test_metal_device.py` | 3 | 100% | Metal UMA device initialization, dynamic MSL shader compilation, basic compute dispatch. |
| `metal2/tests/test_metal_reconstruction.py` | 1 | 100% | C3 Oklab constant-hue gamut mapping on Metal GPU. |
| `metal2/tests/test_shadow_evaluation.py` | 4 | 100% | Soft IoU metric behavior, continuous SDE, superellipse contact grounding gate, integrated evaluation. |
| `tests/RS-SPIKE-3A/camera/` | 4 | 100% | Orthonormal basis, ray generation, world-to-camera roundtrip, perspective projection. |
| `tests/RS-SPIKE-3A/geometry/` | 7 | 100% | Euler matrix orthonormality, OBB slab intersection, superquadric stability, footwear hull mesh, cyc cove multi-region. |
| `tests/RS-SPIKE-3A/lighting/` | 4 | 100% | Blackbody Kelvin-to-RGB, area light energy conventions (FIXED_POWER vs FIXED_ILLUMINANCE), stratified sampling, inverse-square law. |
| `tests/RS-SPIKE-3A/reconstruction/` | 3 | 100% | Identity preservation, protected mask immutability, uncertainty supervisor channels. |
| `tests/RS-SPIKE-3A/renderer/` | 4 | 100% | Sky pixel masking, receiver cove self-shadowing, contact occlusion footprint, workspace dropdown binding. |
| `tests/RS-SPIKE-3A/scene_state/` | 4 | 100% | Default instantiation, JSON serialization roundtrip, parameter validation rejection, undo/redo manager. |
| `tests/RS-SPIKE-3A/shadows/` | 2 | 100% | Occlusion behind OBB, contact occlusion seam sharpness. |
| `tests/RS-SPIKE-3B/test_spike3b_regressions.py` | 4 | 100% | Superquadric normalized metric stability, area light inverse-square law, Metal bitwise zero-mutation, canonical parity. |
| Historical Engine Tests (`test_pbr_engine.py`, `test_v3_engine.py`) | 7 | 100% | Texture-preserving relighting, scene preprocessor, v3 identity preservation, point/spot lights, chromatic adaptation. |

---

## 2. INDEPENDENT DETERMINISTIC REPLAY VERIFICATION

The master engineering directive requires that serializing authoritative scene state to JSON, deserializing it, and re-rendering on GPU produces bitwise identical pixels:
$$\max \left| \mathcal{R}\left(S\right) - \mathcal{R}\left(\text{deserialize}\left(\text{serialize}\left(S\right)\right)\right) \right| = 0.0000000000$$

### Experimental Methodology
Five distinct scene configurations spanning all supported geometry and receiver types were instantiated, rendered on Metal GPU (`FINAL`, 64 samples), serialized to JSON, deserialized back into `StudioScene`, and re-rendered with identical camera and lighting:

```python
r1 = mb.render(scene, img, depth, normals, fg, quality=RenderQuality.FINAL)
json_str = scene.to_json()
scene_reloaded = StudioScene.from_json(json_str)
r2 = mb.render(scene_reloaded, img, depth, normals, fg, quality=RenderQuality.FINAL)
diff = np.max(np.abs(r1["relit_srgb"] - r2["relit_srgb"]))
```

### Empirical Results

| Scene Geometry & Configuration | Receiver Type | Replay Max Delta (sRGB) | Bitwise Parity Status |
| :--- | :--- | :---: | :---: |
| **OBB Subject Proxy** | Ground Plane | **0.0000000000** | **IDENTICAL** |
| **OBB Subject Proxy** | Cyclorama Cove | **0.0000000000** | **IDENTICAL** |
| **Superquadric ($e_1=0.3, e_2=0.3$)** | Ground Plane | **0.0000000000** | **IDENTICAL** |
| **Superquadric ($e_1=0.3, e_2=1.0$)** | Cyclorama Cove | **0.0000000000** | **IDENTICAL** |
| **Footwear Mesh (280 Triangles)** | Ground Plane | **0.0000000000** | **IDENTICAL** |

**Conclusion:** The scene state model is strictly deterministic, completely preserving all geometric and optical parameters through JSON roundtrip serialization.

---

## 3. BACKWARD COMPATIBILITY & HISTORICAL INTEGRITY

### 3.1. CPU Reference Renderer
- The authoritative CPU reference implementation in `studio3a/renderer.py` remains fully functional.
- It acts as the mathematical gold standard for all Metal GPU regression tests.

### 3.2. Preservation of Historical Evidence
- All prior spike outputs and engineering reports remain preserved and untouched in their designated versioned directories:
  - `spike1_output/`, `docs/MASTER_ENGINEERING_ARCHITECTURE_v1.1.md`
  - `spike2_1_output/`, `docs/spike2_1/`
  - `spike2_2_output/`, `docs/spike2_2/`
  - `docs/RS-SPIKE-3A/`
  - `docs/RS-SPIKE-3A.1/`
  - `docs/RS-SPIKE-3B/`
- No historical reports or benchmark outputs were deleted or overwritten during this audit.

---

## 4. REPRODUCIBILITY CHECKLIST FOR THIRD-PARTY AUDITORS

To independently reproduce every finding of this audit milestone from clean repository state:

1. **Environment Setup:**
   ```bash
   cd "relight studio"
   source .venv/bin/activate
   ```
2. **Rebuild Metal Dynamic Library:**
   ```bash
   make -C metal2 clean
   make -C metal2
   ```
3. **Execute Full Automated Regression Suite:**
   ```bash
   PYTHONPATH=. ./.venv/bin/pytest -v
   ```
4. **Reproduce Phase 1 (Superquadric Brent Root-Solver Audit):**
   ```bash
   PYTHONPATH=. ./.venv/bin/python3 benchmarks/independent_superquadric_audit.py
   # Results saved to docs/RS-SPIKE-3B.1/superquadric_independent_audit_results.json
   ```
5. **Reproduce Phase 2 (Independent N=256 Shadow Ground Truth Audit):**
   ```bash
   PYTHONPATH=. ./.venv/bin/python3 benchmarks/independent_shadow_ground_truth_audit.py
   # Results saved to docs/RS-SPIKE-3B.1/independent_shadow_audit_results.json
   ```
6. **Reproduce Phase 3 (Performance & Latency Disaggregation):**
   ```bash
   PYTHONPATH=. ./.venv/bin/python3 benchmarks/reconcile_performance.py
   # Results saved to docs/RS-SPIKE-3B.1/performance_reconciliation_results.json
   ```
7. **Reproduce Phase 4 & 5 (Visual Contact Sheets & Photographic Fidelity):**
   ```bash
   PYTHONPATH=. ./.venv/bin/python3 benchmarks/generate_audit_visual_boards.py
   # Images saved to docs/RS-SPIKE-3B.1/visual_boards/
   ```
