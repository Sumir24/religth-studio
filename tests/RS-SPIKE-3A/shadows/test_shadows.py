"""
Unit Tests for Shadow Engine (RS-SPIKE-3A)
"""

import pytest
import numpy as np
from studio3a.geometry import OrientedBoundingBox, GroundPlaneReceiver, CycloramaReceiver
from studio3a.lighting import RectangularAreaLight
from studio3a.shadows import ShadowEngine


def test_shadow_occlusion_behind_obb():
    # Box at center (0, 0.5, 0)
    obb = OrientedBoundingBox(position=(0.0, 0.5, 0.0), half_extents=(0.3, 0.3, 0.3))
    floor = GroundPlaneReceiver(ground_y=0.0)
    engine = ShadowEngine(proxy=obb, receiver=floor)
    
    # Light overhead at (0, 3.0, 0) pointing down (-90 pitch)
    light = RectangularAreaLight(
        position=(0.0, 3.0, 0.0), rotation_euler=(-90.0, 0.0, 0.0),
        width=0.2, height=0.2, intensity=1.0
    )
    
    # Receiver point directly under box (0, 0, 0)
    p_under = np.array([[[0.0, 0.0, 0.0]]], dtype=np.float32)
    n_under = np.array([[[0.0, 1.0, 0.0]]], dtype=np.float32)
    
    # Receiver point far away (5, 0, 0)
    p_away = np.array([[[5.0, 0.0, 0.0]]], dtype=np.float32)
    n_away = np.array([[[0.0, 1.0, 0.0]]], dtype=np.float32)
    
    vis_under = engine.compute_direct_visibility(p_under, n_under, light, n_samples=16)
    vis_away = engine.compute_direct_visibility(p_away, n_away, light, n_samples=16)
    
    # Under the box must be completely in shadow (vis = 0.0)
    assert vis_under[0, 0] < 0.05
    # Far away must be fully illuminated (vis = 1.0)
    assert vis_away[0, 0] > 0.95


def test_contact_occlusion_sharpness_at_seam():
    obb = OrientedBoundingBox(position=(0.0, 0.25, 0.0), half_extents=(0.25, 0.25, 0.25))
    floor = GroundPlaneReceiver(ground_y=0.0)
    engine = ShadowEngine(proxy=obb, receiver=floor)
    
    # Point right at contact edge
    p_edge = np.array([[[0.25, 0.0, 0.0]]], dtype=np.float32)
    is_rec = np.array([[True]], dtype=bool)
    
    # Point far from contact (2m away)
    p_far = np.array([[[2.0, 0.0, 0.0]]], dtype=np.float32)
    
    c_edge = engine.compute_contact_occlusion(p_edge, is_rec, ground_y=0.0, r_contact=0.08)
    c_far = engine.compute_contact_occlusion(p_far, is_rec, ground_y=0.0, r_contact=0.08)
    
    # Edge point must be darkened (C_contact < 0.15)
    assert c_edge[0, 0] <= 0.10
    # Far point must be unoccluded (C_contact = 1.0)
    assert c_far[0, 0] >= 0.99
