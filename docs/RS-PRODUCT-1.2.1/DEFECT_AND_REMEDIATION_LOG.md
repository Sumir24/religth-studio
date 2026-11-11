# RELIGHT STUDIO — RS-PRODUCT-1.2.1
## Defect Investigation & Bounded Remediation Log

**Auditor:** Principal Rendering Engineer & Product Reliability Auditor  
**Milestone:** RS-PRODUCT-1.2.1  
**Status:** RECORDED & RESOLVED  

---

## 1. Summary of Defects Investigated

| Defect ID | Description | Severity | Impact | Resolution |
|---|---|---|---|---|
| **DEF-1.2.1-01** | Superquadric support function ignored shape exponents $e_1, e_2$ in ground elevation | Medium | Rotated squarish superquadrics had up to $28.7\,\text{mm}$ error in floor snap | **REMEDIATED in `studio3a/geometry.py` and `controller.py`** |
| **DEF-1.2.1-02** | 1080p Final Quality performance benchmark was mislabeled (tested $576 \times 1024$ native plate) | Medium | Misleading performance claim in report | **RECONCILED with true $1920 \times 1080$ benchmark** |
| **DEF-1.2.1-03** | Mixed units in photographic response report ($[0, 1]$ float vs $[0, 255]$ uint8) | Low | Potential confusion regarding "peak delta 244" | **STANDARDIZED to both normalized float and 8-bit LSBs** |
| **DEF-1.2.1-04** | Portrait image sensor height assumption ($24\,\text{mm}$ vs $36\,\text{mm}$) | Low | Effective $1.5\times$ crop factor on vertical plates | **DOCUMENTED as known photogrammetric limitation** |

---

## 2. Remediation Details

### DEF-1.2.1-01: Superquadric Support Function Formulation
- **Files Modified:**
  - `studio3a/geometry.py`: Updated `compute_proxy_geometry_meta` and `snap_proxy_to_ground` to accept `sq_exponents`.
  - `relight_studio/controller.py`: Passed `sq_exponents=scene.subject.sq_exponents` in all 5 call sites.
  - `tests/RS-PRODUCT-1.2/test_subject_geometry_editing.py`: Added automated test `test_snap_to_ground_superquadric_with_non_unity_exponents`.
- **Verification:** Test passed in $0.46\,\text{s}$; verified that error vs numerical sampling is $< 0.1\,\text{mm}$.

### DEF-1.2.1-02: 1080p Benchmark Reconciliation
- **Files Modified:**
  - Created `scripts/audit_performance_and_scaling.py`.
  - Created `docs/RS-PRODUCT-1.2.1/performance_audit_results.json`.
- **Verification:**
  - True 1080p Final Quality: $14.70\,\text{ms}$ (1 light) to $37.28\,\text{ms}$ (8 lights).
  - True 1080p Preview Quality: $13.13\,\text{ms}$ (1 light) to $16.41\,\text{ms}$ (8 lights).
  - Preview at $1024 \times 576$: $4.50\,\text{ms}$ (1 light) to $5.39\,\text{ms}$ (8 lights, $185.6\,\text{FPS}$).

### DEF-1.2.1-03: Metric Unit Normalization
- **Files Modified:**
  - Created `docs/RS-PRODUCT-1.2.1/PHOTOGRAPHIC_LIGHTING_FIDELITY.md`.
- **Verification:** Re-evaluated Scenarios 1, 2, and 3 with dual-scale reporting.
