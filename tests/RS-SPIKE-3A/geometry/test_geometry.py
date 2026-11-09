"""
Unit Tests for 3D Geometry Engine (RS-SPIKE-3A)
"""

import pytest
import numpy as np
from studio3a.geometry import (
    OrientedBoundingBox, SuperquadricEllipsoid, LowPolyMesh,
    GroundPlaneReceiver, CycloramaReceiver, euler_to_rotation_matrix
)


def test_euler_to_rotation_matrix_orthonormality():
    R = euler_to_rotation_matrix(30.0, 45.0, 60.0)
    # R @ R.T must equal identity
    assert np.allclose(R @ R.T, np.eye(3), atol=1e-5)
    assert abs(np.linalg.det(R) - 1.0) < 1e-5


def test_obb_intersection_and_normals():
    obb = OrientedBoundingBox(position=(0.0, 1.0, 0.0), half_extents=(0.5, 0.5, 0.5))
    
    # Ray aimed straight at front face along -Z
    ray_o = np.array([[0.0, 1.0, 3.0]], dtype=np.float32)
    ray_d = np.array([[0.0, 0.0, -1.0]], dtype=np.float32)
    
    hit, t, norm = obb.intersect_rays(ray_o, ray_d)
    assert hit[0]
    assert abs(t[0] - 2.5) < 1e-3  # Hits at z = 0.5 -> dist = 3.0 - 0.5 = 2.5
    assert np.allclose(norm[0], [0.0, 0.0, 1.0], atol=1e-3)
    
    # Ray missing box
    ray_o_miss = np.array([[2.0, 1.0, 3.0]], dtype=np.float32)
    hit_miss, _, _ = obb.intersect_rays(ray_o_miss, ray_d)
    assert not hit_miss[0]


def test_superquadric_sphere_equivalence():
    # When e1=1.0 and e2=1.0, superquadric is an analytical ellipsoid
    sq = SuperquadricEllipsoid(position=(0.0, 0.0, 0.0), radii=(1.0, 1.0, 1.0), sq_exponents=(1.0, 1.0))
    
    # Ray along -Z hitting pole
    ray_o = np.array([[0.0, 0.0, 3.0]], dtype=np.float32)
    ray_d = np.array([[0.0, 0.0, -1.0]], dtype=np.float32)
    
    hit, t, norm = sq.intersect_rays(ray_o, ray_d)
    assert hit[0]
    assert abs(t[0] - 2.0) < 1e-2  # Sphere radius 1, enters at z=1 -> t=2.0
    assert np.allclose(norm[0], [0.0, 0.0, 1.0], atol=1e-2)


def test_superquadric_numerical_stability():
    # Test sharp box-like superquadric (e1=0.2, e2=0.2)
    sq = SuperquadricEllipsoid(position=(0.0, 0.5, 0.0), radii=(0.5, 0.5, 0.5), sq_exponents=(0.2, 0.2))
    
    ray_o = np.array([[0.0, 0.5, 2.0]], dtype=np.float32)
    ray_d = np.array([[0.0, 0.0, -1.0]], dtype=np.float32)
    
    hit, t, norm = sq.intersect_rays(ray_o, ray_d)
    assert hit[0]
    assert np.isfinite(t[0])
    assert np.all(np.isfinite(norm[0]))


def test_low_poly_footwear_hull_intersection():
    mesh = LowPolyMesh.create_footwear_hull(position=(0.0, 0.15, 0.0))
    assert len(mesh.faces) > 200
    
    # Ray hitting top of instep
    ray_o = np.array([[0.0, 2.0, 0.0]], dtype=np.float32)
    ray_d = np.array([[0.0, -1.0, 0.0]], dtype=np.float32)
    
    hit, t, norm = mesh.intersect_rays(ray_o, ray_d)
    assert hit[0]
    assert t[0] > 1.0  # Above ground
    assert norm[0, 1] > 0.5  # Normal points generally upwards (+Y)


def test_ground_plane_intersection():
    plane = GroundPlaneReceiver(ground_y=0.0)
    ray_o = np.array([[0.0, 2.0, 0.0]], dtype=np.float32)
    ray_d = np.array([[0.0, -1.0, 0.0]], dtype=np.float32)
    
    hit, t, norm = plane.intersect_rays(ray_o, ray_d)
    assert hit[0]
    assert abs(t[0] - 2.0) < 1e-4
    assert np.allclose(norm[0], [0.0, 1.0, 0.0])


def test_cyclorama_receiver_multi_region():
    cyclo = CycloramaReceiver(ground_y=0.0, cove_center_yz=(0.40, -0.80), cove_radius=0.40, wall_z=-1.20)
    
    # 1. Floor hit: ray hitting floor at z = 0.0
    ray_o1 = np.array([[0.0, 2.0, 0.0]], dtype=np.float32)
    ray_d1 = np.array([[0.0, -1.0, 0.0]], dtype=np.float32)
    hit1, t1, norm1 = cyclo.intersect_rays(ray_o1, ray_d1)
    assert hit1[0]
    assert abs(t1[0] - 2.0) < 1e-3
    assert np.allclose(norm1[0], [0.0, 1.0, 0.0])
    
    # 2. Vertical Wall hit: ray hitting vertical wall at z = -1.20, y = 1.0
    ray_o2 = np.array([[0.0, 1.0, 2.0]], dtype=np.float32)
    ray_d2 = np.array([[0.0, 0.0, -1.0]], dtype=np.float32)
    hit2, t2, norm2 = cyclo.intersect_rays(ray_o2, ray_d2)
    assert hit2[0]
    assert abs(t2[0] - 3.20) < 1e-3  # z goes from 2.0 to -1.20 -> dist = 3.20
    assert np.allclose(norm2[0], [0.0, 0.0, 1.0])
    
    # 3. Fillet Cove hit: ray aimed at the cove fillet (z = -1.0, y = 0.2)
    ray_o3 = np.array([[0.0, 0.20, 2.0]], dtype=np.float32)
    ray_d3 = np.array([[0.0, 0.0, -1.0]], dtype=np.float32)
    hit3, t3, norm3 = cyclo.intersect_rays(ray_o3, ray_d3)
    assert hit3[0]
    # Inward normal on curved fillet must have both +Y and +Z components
    assert norm3[0, 1] > 0.0
    assert norm3[0, 2] > 0.0
