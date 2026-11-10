# RS-SPIKE-3C.0 — Engineering Report 07: Automated Regression Test Report
**Milestone:** RS-SPIKE-3C.0 (Single-Light Pipeline Completion)  
**Author:** Independent Verification Lead & QA Architect  
**Branch:** `feature/RS-SPIKE-3C.0-single-light-completion`  
**Execution Timestamp:** 2026-11-10  
**Test Suite Status:** 63 PASSED, 0 FAILED, 0 SKIPPED, 0 XFAIL, 0 MOCKED

---

## 1. Executive Summary

A continuous, non-negotiable requirement of RS-SPIKE-3C.0 was the establishment of an exhaustive automated regression suite with:
- Zero mock objects or synthetic placeholders in core computational paths.
- Zero skipped or xfailed tests.
- 100% live hardware execution against Apple Silicon (Metal 3).

The expanded test suite grew from 51 tests (RS-SPIKE-3B baseline) to **63 comprehensive tests**, all executing and passing in **10.29 seconds**.

---

## 2. Test Suite Composition & Results Breakdown

```
[Total Test Suite: 63 Tests Passing in 10.29s]
├── tests/RS-SPIKE-3A/ (28 tests)
│   ├── camera/test_camera.py:                       4 passed
│   ├── geometry/test_geometry.py:                   7 passed
│   ├── lighting/test_lighting.py:                   4 passed
│   ├── reconstruction/test_reconstruction.py:       3 passed
│   ├── renderer/test_renderer_repairs.py:           4 passed
│   ├── scene_state/test_scene_state.py:             4 passed
│   └── shadows/test_shadows.py:                     2 passed
├── tests/RS-SPIKE-3B/ (4 tests)
│   └── test_spike3b_regressions.py:                 4 passed
├── tests/RS-SPIKE-3C/ (7 tests - NEW)
│   └── test_spike3c_regressions.py:                 7 passed
├── tests/test_pbr_engine.py:                        2 passed
├── tests/test_v3_engine.py:                         5 passed
├── tests/test_v5_engine.py: (5 tests - POPULATED)   5 passed
└── metal2/tests/ (12 tests)
    ├── test_math_parity.py:                         4 passed
    ├── test_metal_device.py:                        3 passed
    ├── test_metal_reconstruction.py:                1 passed
    └── test_shadow_evaluation.py:                   4 passed
```

---

## 3. Detailed Results of Newly Added & Populated Test Suites

### 3.1 Suite `tests/RS-SPIKE-3C/test_spike3c_regressions.py` (7 Tests)
1. `test_metal_e1_guided_filter_parity_vs_cpu`: Asserts that GPU E.1 separable box filter matches CPU `ReconstructionEngine` ($MAE = 0.00050$, $MaxDiff = 0.00066 \le 0.010$). **PASSED**
2. `test_metal_e1_restores_foreground_dci_on_photograph`: Asserts that Foreground DCI on Nike sneaker reaches $\ge 0.95$ ($DCI = 0.99842$). **PASSED**
3. `test_exact_sphere_analytical_intersection_and_normals`: Asserts that `SphereProxy` solves quadratic ray-sphere intersection with unit normal orientation. **PASSED**
4. `test_sphere_shadow_area_error_vs_analytical_truth`: Asserts that `SphereProxy` eliminates OBB cube approximation error, achieving area error $\le 1.0\%$ ($0.388\%$). **PASSED**
5. `test_sphere_cpu_metal_parity`: Asserts that Metal sphere rendering matches CPU reference ($\text{Soft IoU} = 0.95570 \ge 0.93$, $\text{SDE} = 0.450\,\text{px} \le 1.0\,\text{px}$). **PASSED**
6. `test_persistent_buffer_pool_zero_allocations_in_steady_state`: Asserts that buffer allocations remain flat at 1 in steady state across 10 frames ($0$ dynamic allocations). **PASSED**
7. `test_exact_bitwise_zero_mutation_with_e1`: Asserts that protected regions experience strictly $0.0000000000$ mutation on GPU. **PASSED**

### 3.2 Suite `tests/test_v5_engine.py` (Populated from 0-byte state) (5 Tests)
1. `test_v5_polar_coordinates_and_distance_normalization`: Asserts that `polar(az, el)` produces unit vectors ($|\vec{v}| = 1.0 \pm 10^{-5}$) with correct cardinal coordinate signs (+X right, -X left, +Z top). **PASSED**
2. `test_v5_hbao_crevice_occlusion`: Asserts that HBAO stays bounded in $[0, 1]$, darkens deep crevices, and produces $\ge 0.90$ on flat surfaces. **PASSED**
3. `test_v5_exposure_compensation_bounds`: Asserts that `soft_clamp_log` prevents dynamic range blowout across extreme exposures ($-10.0$ to $+10.0$) and remains monotonic. **PASSED**
4. `test_v5_albedo_regularization_edge_preservation`: Asserts that `masked_guided` preserves sharp step edges without halo leakage. **PASSED**
5. `test_v5_real_photographs`: Asserts end-to-end relighting of Nike sneaker with warm key and cool rim lights, zero NaNs, zero Infs, and Foreground DCI $\ge 0.85$ ($DCI = 0.8652$). **PASSED**

---

## 4. Verification Evidence Command Log
```bash
$ PYTHONPATH=. ./.venv/bin/pytest tests/ metal2/tests/
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sumirdayal/religth studio
collected 63 items

tests/RS-SPIKE-3A/camera/test_camera.py ....                             [  6%]
tests/RS-SPIKE-3A/geometry/test_geometry.py .......                      [ 17%]
tests/RS-SPIKE-3A/lighting/test_lighting.py ....                         [ 23%]
tests/RS-SPIKE-3A/reconstruction/test_reconstruction.py ...              [ 28%]
tests/RS-SPIKE-3A/renderer/test_renderer_repairs.py ....                 [ 34%]
tests/RS-SPIKE-3A/scene_state/test_scene_state.py ....                   [ 41%]
tests/RS-SPIKE-3A/shadows/test_shadows.py ..                             [ 44%]
tests/RS-SPIKE-3B/test_spike3b_regressions.py ....                       [ 50%]
tests/RS-SPIKE-3C/test_spike3c_regressions.py .......                    [ 61%]
tests/test_pbr_engine.py ..                                              [ 65%]
tests/test_v3_engine.py .....                                            [ 73%]
tests/test_v5_engine.py .....                                            [ 80%]
metal2/tests/test_math_parity.py ....                                    [ 87%]
metal2/tests/test_metal_device.py ...                                    [ 92%]
metal2/tests/test_metal_reconstruction.py .                              [ 93%]
metal2/tests/test_shadow_evaluation.py ....                              [100%]

============================= 63 passed in 10.29s ==============================
```

