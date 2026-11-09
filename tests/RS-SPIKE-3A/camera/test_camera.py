"""
Unit Tests for Camera3D (RS-SPIKE-3A)
"""

import pytest
import numpy as np
from studio3a.camera import Camera3D


def test_camera_orthonormal_basis():
    cam = Camera3D(pos=(0.0, 1.0, 2.0), target=(0.0, 0.0, 0.0), up=(0.0, 1.0, 0.0))
    # Dot products must be zero
    assert abs(np.dot(cam.forward, cam.right)) < 1e-6
    assert abs(np.dot(cam.forward, cam.up_cam)) < 1e-6
    assert abs(np.dot(cam.right, cam.up_cam)) < 1e-6
    # Lengths must be 1.0
    assert abs(np.linalg.norm(cam.forward) - 1.0) < 1e-6
    assert abs(np.linalg.norm(cam.right) - 1.0) < 1e-6
    assert abs(np.linalg.norm(cam.up_cam) - 1.0) < 1e-6


def test_camera_world_to_camera_roundtrip():
    cam = Camera3D(pos=(1.0, 2.0, 3.0), target=(0.0, 0.5, 0.0), up=(0.0, 1.0, 0.0))
    np.random.seed(42)
    world_pts = np.random.uniform(-5.0, 5.0, (50, 3)).astype(np.float32)
    
    cam_pts = cam.world_to_camera(world_pts)
    restored_world = cam.camera_to_world(cam_pts)
    diff = np.max(np.abs(world_pts - restored_world))
    assert diff < 1e-5, f"World-Camera roundtrip failure, max diff: {diff}"


def test_camera_ray_generation():
    H, W = 128, 192
    cam = Camera3D(pos=(0.0, 1.0, 2.0), target=(0.0, 0.0, 0.0), width=W, height=H, fov_deg=60.0)
    ray_o, ray_d = cam.generate_camera_rays()
    
    assert ray_o.shape == (H, W, 3)
    assert ray_d.shape == (H, W, 3)
    
    # All ray origins must equal camera pos
    assert np.allclose(ray_o, cam.pos)
    
    # All ray directions must be unit vectors
    norms = np.linalg.norm(ray_d, axis=-1)
    assert np.allclose(norms, 1.0, atol=1e-5)
    
    # Center pixel ray must be close to camera forward vector
    center_d = ray_d[H // 2, W // 2]
    cos_angle = np.dot(center_d, cam.forward)
    assert cos_angle > 0.999


def test_camera_project_point():
    cam = Camera3D(pos=(0.0, 0.0, 5.0), target=(0.0, 0.0, 0.0), width=400, height=300, fov_deg=90.0)
    
    # Target point at center of view (0, 0, 0)
    px, py, depth = cam.project_point(np.array([0.0, 0.0, 0.0], dtype=np.float32))
    assert abs(px - 200.0) < 1.0
    assert abs(py - 150.0) < 1.0
    assert abs(depth - 5.0) < 1e-4
