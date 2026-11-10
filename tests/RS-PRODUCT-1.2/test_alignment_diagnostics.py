"""
RS-PRODUCT-1.2 Test Suite: Alignment Diagnostics & Photograph Overlays
======================================================================
Validates 2D image-space projection of proxy wireframe, silhouette polygon,
horizon vanishing line, ground grid, ground contact marker, IoU diagnostics,
and multi-mode photographic composite rendering.
"""

import numpy as np
import pytest

from studio3a.camera import Camera3D
from relight_studio.controller import StudioAppController


def test_alignment_projection_meta_structure():
    """Verify get_alignment_projection_meta produces all necessary 2D geometry keys."""
    ctrl = StudioAppController()
    meta = ctrl.get_alignment_projection_meta(canvas_w=1024, canvas_h=576)

    assert meta["image_width"] == 1024
    assert meta["image_height"] == 576
    assert len(meta["corners_screen"]) == 8
    assert len(meta["corners_visible"]) == 8
    assert len(meta["edges"]) == 12
    assert len(meta["silhouette_polygon"]) >= 3
    assert len(meta["horizon_line"]) == 2
    assert len(meta["ground_grid"]) > 0
    assert meta["ground_contact_screen"] is not None
    assert "diagnostics" in meta


def test_horizon_line_projection():
    """Verify horizon line reflects camera pitch angle correctly."""
    ctrl = StudioAppController()

    # Camera looking level
    ctrl.update_camera_params(pos=[0.0, 1.2, 3.0], target=[0.0, 1.2, 0.0])
    meta_level = ctrl.get_alignment_projection_meta(canvas_w=1024, canvas_h=576)
    # When camera is level with zero roll, horizon should be at center: Y = 576 / 2 = 288
    h_y_level = meta_level["horizon_line"][0][1]
    assert abs(h_y_level - 288.0) < 5.0

    # Camera pitched downwards looking at floor
    ctrl.update_camera_params(pos=[0.0, 2.5, 3.0], target=[0.0, 0.0, 0.0])
    meta_pitch = ctrl.get_alignment_projection_meta(canvas_w=1024, canvas_h=576)
    # Horizon should rise towards top of the image (lower pixel Y)
    h_y_pitch = meta_pitch["horizon_line"][0][1]
    assert h_y_pitch < h_y_level


def test_quantitative_alignment_diagnostics():
    """Verify silhouette IoU, foreground coverage, and bounding box delta computation."""
    ctrl = StudioAppController()
    meta = ctrl.get_alignment_projection_meta(canvas_w=1024, canvas_h=576)
    diag = meta["diagnostics"]

    assert "silhouette_iou" in diag
    assert "foreground_coverage" in diag
    assert "bbox_delta_px" in diag
    assert "ground_gap_m" in diag
    assert "contact_state" in diag
    assert 0.0 <= diag["silhouette_iou"] <= 1.0
    assert 0.0 <= diag["foreground_coverage"] <= 1.0


def test_photograph_overlay_rendering_modes():
    """Verify render_photograph_with_overlay produces valid image buffers for all modes."""
    ctrl = StudioAppController()

    modes = ["original", "relit", "wireframe", "silhouette", "guides", "mismatch"]
    for mode in modes:
        img = ctrl.render_photograph_with_overlay(mode=mode, opacity=0.7, width=640, height=480)
        assert isinstance(img, np.ndarray)
        assert img.shape == (480, 640, 3)
        assert img.dtype == np.uint8
        # Ensure image is not completely empty/black
        assert np.mean(img) > 1.0, f"Mode {mode} rendered empty canvas"

