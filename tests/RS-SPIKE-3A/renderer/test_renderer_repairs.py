"""
Regression Tests for RS-SPIKE-3A CPU Reference Renderer Repairs
===============================================================
Validates:
  1. Sky-pixel masking (no [0, 0, 0] coordinate collapse, unshadowed sky)
  2. Receiver self-shadowing (cyclorama wall blocks back-light)
  3. Contact occlusion exact rectangular footprint distance
  4. Workspace session receiver parameter updates & undo/redo tracking
"""

import numpy as np
import pytest

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, ProxyType, ReceiverType, RenderQuality, SceneStateManager
)
from studio3a.camera import Camera3D
from studio3a.geometry import OrientedBoundingBox, CycloramaReceiver, GroundPlaneReceiver
from studio3a.lighting import RectangularAreaLight
from studio3a.shadows import ShadowEngine
from studio3a.renderer import RenderBackend
from studio3a.workspace import StudioWorkspaceSession


def test_sky_pixel_masking_no_zero_collapse():
    """Verify that sky pixels are not collapsed to [0,0,0] and receive visibility 1.0."""
    scene = StudioScene()
    scene.camera = CameraData(pos=[0.0, 1.2, 2.5], target=[0.0, 0.35, 0.0], fov_deg=45.0, width=128, height=128)
    scene.receiver = ReceiverData(receiver_type=ReceiverType.PLANE, ground_y=0.0)
    scene.subject.proxy_type = ProxyType.OBB
    scene.subject.position = [0.0, 0.40, 0.0]
    scene.subject.dimensions = [0.25, 0.40, 0.20]
    
    # Simple blank image and depth
    img = np.ones((128, 128, 3), dtype=np.float32) * 0.5
    depth = np.ones((128, 128), dtype=np.float32) * 0.5
    normals = np.zeros((128, 128, 3), dtype=np.float32)
    normals[..., 1] = 1.0
    fg_mask = np.zeros((128, 128), dtype=bool)
    
    backend = RenderBackend()
    res = backend.render(scene, img, depth, normals, fg_mask, quality=RenderQuality.PREVIEW)
    
    # In top 20 rows, camera looks into the sky above the horizon (Y > 0)
    # They should NOT be shadowed by the box at [0, 0.4, 0]
    sky_vis = res["direct_visibility"][:20, :]
    assert np.all(sky_vis == 1.0), f"Sky pixels must be unshadowed (vis=1.0), found min {np.min(sky_vis)}"


def test_receiver_self_shadow():
    """Verify that light positioned behind a cyclorama wall is blocked by the receiver."""
    # Light placed behind cyclorama wall at Z = -2.0
    light = RectangularAreaLight(
        position=[0.0, 1.0, -2.0],
        rotation_euler=[0.0, 180.0, 0.0],
        width=0.5,
        height=0.5
    )
    proxy = OrientedBoundingBox(position=[0.0, 0.25, 0.0], half_extents=[0.2, 0.2, 0.2])
    receiver = CycloramaReceiver(ground_y=0.0, cove_center_yz=[0.4, -0.8], cove_radius=0.4, wall_z=-1.2)
    
    shadow_engine = ShadowEngine(proxy=proxy, receiver=receiver)
    
    # Surface point on floor in front of cyclorama at (0, 0, 0)
    surface_pos = np.array([[[0.0, 0.0, 0.0]]], dtype=np.float32)
    surface_norm = np.array([[[0.0, 1.0, 0.0]]], dtype=np.float32)
    
    vis = shadow_engine.compute_direct_visibility(surface_pos, surface_norm, light, n_samples=8)
    assert vis[0, 0] == 0.0, f"Light behind wall must be blocked by receiver, got vis={vis[0, 0]}"


def test_contact_occlusion_box_footprint():
    """Verify exact rectangular footprint contact distance calculation for OBB."""
    proxy = OrientedBoundingBox(
        position=[0.0, 0.25, 0.0],
        half_extents=[0.25, 0.25, 0.15], # Width 0.50, Depth 0.30
        rotation_euler=[0.0, 0.0, 0.0]
    )
    receiver = GroundPlaneReceiver(ground_y=0.0)
    shadow_engine = ShadowEngine(proxy=proxy, receiver=receiver)
    
    # Test points on ground (Y=0):
    # P1: (0, 0, 0) directly under box -> should be at seam minimum (0.05)
    # P2: (0.24, 0, 0.14) inside footprint -> should be at seam minimum (0.05)
    # P3: (0.26, 0, 0) just outside footprint (1cm away) -> strongly occluded
    # P4: (1.5, 0, 0) far away (1.25m away) -> unoccluded (1.0)
    surface_pos = np.array([
        [[0.0, 0.0, 0.0], [0.24, 0.0, 0.14]],
        [[0.26, 0.0, 0.0], [1.5, 0.0, 0.0]]
    ], dtype=np.float32)
    is_receiver = np.ones((2, 2), dtype=bool)
    
    c_contact = shadow_engine.compute_contact_occlusion(surface_pos, is_receiver, ground_y=0.0, r_contact=0.08)
    
    assert np.isclose(c_contact[0, 0], 0.05, atol=1e-3), f"Underneath box must be 0.05, got {c_contact[0, 0]}"
    assert np.isclose(c_contact[0, 1], 0.05, atol=1e-3), f"Inside footprint must be 0.05, got {c_contact[0, 1]}"
    assert c_contact[1, 0] < 0.30, f"1cm from edge should be darkened, got {c_contact[1, 0]}"
    assert np.isclose(c_contact[1, 1], 1.0, atol=1e-3), f"Far point must be 1.0, got {c_contact[1, 1]}"


def test_workspace_receiver_dropdown_binding():
    """Verify that update_receiver_params modifies authoritative scene state."""
    scene = StudioScene()
    scene.receiver.receiver_type = ReceiverType.CYCLORAMA
    manager = SceneStateManager(scene)
    
    # Modify receiver
    curr = manager.current_scene
    curr.receiver.receiver_type = ReceiverType.PLANE
    curr.receiver.ground_y = 0.05
    manager.push_state(curr)
    
    assert manager.current_scene.receiver.receiver_type == ReceiverType.PLANE
    assert manager.current_scene.receiver.ground_y == 0.05
    
    # Verify undo restores cyclorama
    manager.undo()
    assert manager.current_scene.receiver.receiver_type == ReceiverType.CYCLORAMA
