"""
Tests for RS-SPIKE-3A.1 Continuous Shadow Evaluation Module
"""

import numpy as np
import pytest
from metal2.shadow_evaluation import (
    compute_shadow_opacity,
    compute_soft_iou,
    compute_continuous_sde,
    compute_penumbra_metrics,
    compute_contour_boundary_displacement,
    compute_contact_grounding_metrics,
    evaluate_comprehensive_shadow_fidelity
)


def test_soft_iou_identity_and_shifts():
    H, W = 100, 100
    mask = np.ones((H, W), dtype=bool)
    
    # Fully identical smooth shadow fields
    V1 = np.ones((H, W), dtype=np.float32)
    V1[30:70, 30:70] = 0.2
    
    assert compute_soft_iou(V1, V1, mask) == 1.0
    
    # Slightly shifted field
    V2 = np.ones((H, W), dtype=np.float32)
    V2[32:72, 32:72] = 0.2
    
    soft_iou = compute_soft_iou(V1, V2, mask)
    assert 0.80 < soft_iou < 1.0, f"Expected high soft IoU for 2px shift, got {soft_iou}"


def test_continuous_sde_measurement():
    H, W = 100, 100
    mask = np.ones((H, W), dtype=bool)
    
    V1 = np.ones((H, W), dtype=np.float32)
    V1[40:60, 40:60] = 0.1 # Centroid at (49.5, 49.5)
    
    # 5px shift along X
    V2 = np.ones((H, W), dtype=np.float32)
    V2[40:60, 45:65] = 0.1 # Centroid at (49.5, 54.5)
    
    sde = compute_continuous_sde(V1, V2, mask)
    assert abs(sde - 5.0) < 0.1, f"Expected 5.0px SDE, got {sde}"


def test_contact_grounding_gate():
    H, W = 64, 64
    contact_mask = np.zeros((H, W), dtype=bool)
    contact_mask[30:34, 30:34] = True
    
    V_good = np.ones((H, W), dtype=np.float32)
    V_good[contact_mask] = 0.04 # Passes gate <= 0.06
    
    metrics_good = compute_contact_grounding_metrics(V_good, contact_mask)
    assert metrics_good["gate_contact"] == "PASS"
    assert metrics_good["contact_min_vis"] == 0.04
    
    V_bad = np.ones((H, W), dtype=np.float32)
    V_bad[contact_mask] = 0.25 # Fails gate
    
    metrics_bad = compute_contact_grounding_metrics(V_bad, contact_mask)
    assert metrics_bad["gate_contact"] == "FAIL"


def test_comprehensive_evaluation_integration():
    H, W = 64, 64
    mask = np.ones((H, W), dtype=bool)
    contact_mask = np.zeros((H, W), dtype=bool)
    contact_mask[30, 30] = True
    
    V_cand = np.ones((H, W), dtype=np.float32)
    V_gt = np.ones((H, W), dtype=np.float32)
    V_cand[20:40, 20:40] = 0.05
    V_gt[20:40, 20:40] = 0.05
    
    report = evaluate_comprehensive_shadow_fidelity(V_cand, V_gt, mask, contact_mask)
    assert report["soft_iou"] == 1.0
    assert report["continuous_sde_px"] == 0.0
    assert report["shadow_field_mae"] == 0.0
    assert report["contour_displacement_px"] == 0.0
