"""
Unit Tests for Reconstruction and Uncertainty (RS-SPIKE-3A)
"""

import pytest
import numpy as np
from studio3a.reconstruction import (
    ReconstructionEngine, srgb_to_linear, linear_to_srgb,
    color_reconstruct_C3, linear_to_luminance
)
from studio3a.uncertainty import UncertaintySupervisor


def test_reconstruction_identity_preservation():
    """When direct lighting matches ambient base, output must match input within float precision."""
    recon = ReconstructionEngine()
    H, W = 64, 64
    
    np.random.seed(42)
    img_orig = np.random.uniform(0.2, 0.8, (H, W, 3)).astype(np.float32)
    
    # Direct irradiance set to match baseline (ratio = 1.0)
    img_lin = srgb_to_linear(img_orig)
    Y_orig = linear_to_luminance(img_lin)
    
    # Set direct lighting such that Y_indirect + Y_direct == Y_orig
    ambient_fill = 0.15
    irr = np.ones((H, W, 3), dtype=np.float32) * (1.0 - ambient_fill)
    vis = np.ones((H, W), dtype=np.float32)
    
    res = recon.reconstruct_relit_image(img_orig, irr, vis, ambient_fill=ambient_fill)
    
    # Max difference should be tiny
    diff = np.max(np.abs(res["relit_srgb"] - img_orig))
    assert diff < 0.02, f"Identity preservation violated, diff: {diff}"


def test_protected_region_zero_mutation():
    """Regions designated as protected must have exactly zero change."""
    recon = ReconstructionEngine()
    H, W = 64, 64
    img_orig = np.random.uniform(0.2, 0.8, (H, W, 3)).astype(np.float32)
    
    # Left half is protected
    protected_mask = np.zeros((H, W), dtype=bool)
    protected_mask[:, :W//2] = True
    
    irr = np.ones((H, W, 3), dtype=np.float32) * 5.0 # intense new lighting
    vis = np.ones((H, W), dtype=np.float32)
    
    res = recon.reconstruct_relit_image(img_orig, irr, vis, protected_mask=protected_mask)
    
    # Left half must have exactly 0 difference
    left_diff = np.max(np.abs(res["relit_srgb"][:, :W//2] - img_orig[:, :W//2]))
    assert left_diff == 0.0, f"Protected region was mutated! Diff: {left_diff}"
    
    # Right half must be relit (diff > 0)
    right_diff = np.max(np.abs(res["relit_srgb"][:, W//2:] - img_orig[:, W//2:]))
    assert right_diff > 0.05


def test_uncertainty_supervisor_channels():
    sup = UncertaintySupervisor()
    H, W = 64, 64
    depth = np.ones((H, W), dtype=np.float32) * 2.0
    # Add a sharp depth cliff at x = 32
    depth[:, 32:] = 4.0
    
    normals = np.zeros((H, W, 3), dtype=np.float32)
    normals[..., 2] = -1.0 # Facing camera
    view_dir = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    image_lin = np.ones((H, W, 3), dtype=np.float32) * 0.5
    fg_mask = np.ones((H, W), dtype=bool)
    
    unc = sup.evaluate_uncertainty(depth, normals, view_dir, image_lin, fg_mask)
    
    assert "sigma_geom" in unc
    assert "sigma_occl" in unc
    assert "sigma_mat" in unc
    assert "composite_confidence" in unc
    
    # Geometry uncertainty must peak near depth cliff x = 32
    assert unc["sigma_geom"][:, 32].mean() > unc["sigma_geom"][:, 10].mean()
    # Values must be bounded in [0, 1]
    assert np.all((unc["sigma_geom"] >= 0.0) & (unc["sigma_geom"] <= 1.0))
    assert np.all((unc["composite_confidence"] >= 0.0) & (unc["composite_confidence"] <= 1.0))
