"""
RELIGHT STUDIO — RS-PRODUCT-1.1
Unit & Integration Tests: Subject Proxy and Receiver Manipulation
"""

import pytest
import numpy as np
from relight_studio.controller import StudioAppController
from studio3a.scene import ProxyType, ReceiverType, RenderQuality


@pytest.fixture
def controller():
    ctrl = StudioAppController()
    return ctrl


def test_subject_proxy_params_update(controller):
    """Verifies that changing subject proxy geometry modifies scene state."""
    scene = controller.current_scene
    initial_type = scene.subject.proxy_type

    controller.update_subject_proxy_params(
        proxy_type="CYLINDER",
        dimensions=[0.5, 0.8, 0.5],
        position_y=0.1
    )

    # "CYLINDER" maps gracefully to SUPERQUADRIC approximation
    assert controller.current_scene.subject.proxy_type == ProxyType.SUPERQUADRIC
    assert controller.current_scene.subject.dimensions == [0.5, 0.8, 0.5]
    assert controller.current_scene.subject.position[1] == 0.1

    # Check undo
    controller.undo()
    assert controller.current_scene.subject.proxy_type == initial_type


def test_receiver_params_update(controller):
    """Verifies that background receiver configuration is controllable."""
    controller.update_receiver_params(
        receiver_type="PLANE",
        ground_y=-0.2,
        cove_radius=0.5
    )

    assert controller.current_scene.receiver.receiver_type == ReceiverType.PLANE
    assert controller.current_scene.receiver.ground_y == -0.2

    # Switch back to Cyclorama
    controller.update_receiver_params(
        receiver_type="CYCLORAMA",
        ground_y=0.0,
        cove_radius=0.8
    )
    assert controller.current_scene.receiver.receiver_type == ReceiverType.CYCLORAMA
    assert controller.current_scene.receiver.cove_radius == 0.8


def test_geometry_photographic_consequence(controller):
    """Verifies that modifying subject elevation/scale updates rendered photographic lighting."""
    controller.update_subject_proxy_params(position_y=0.0, dimensions=[0.3, 0.3, 0.3])
    res1 = controller.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    img1 = res1["relit_srgb"]

    controller.update_subject_proxy_params(position_y=0.4, dimensions=[0.6, 0.6, 0.6])
    res2 = controller.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    img2 = res2["relit_srgb"]

    # Changing proxy geometry must alter the lighting/shadow distribution on the photo
    diff = np.mean(np.abs(img1 - img2))
    assert diff > 0.005, f"Expected photographic response to proxy geometry change, got diff={diff}"
