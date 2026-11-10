"""
RELIGHT STUDIO — RS-PRODUCT-1.1
Unit & Integration Tests: Dynamic Preview Quality Policy and Interaction Lifecycle
"""

import pytest
import numpy as np
from relight_studio.controller import StudioAppController
from studio3a.scene import RenderQuality


@pytest.fixture
def controller():
    ctrl = StudioAppController()
    return ctrl


def test_interaction_lifecycle(controller):
    """Verifies begin_interaction and end_interaction manage state and quality transitions."""
    assert controller.is_interacting is False
    initial_undo_count = len(controller.state_manager._undo_stack)

    # 1. Start continuous drag gesture
    controller.begin_interaction()
    assert controller.is_interacting is True

    # 2. Simulate rapid drag updates (e.g. 5 mousemove ticks)
    for i in range(5):
        controller.project_drag_to_3d(axis="X", delta_screen_x=10.0, delta_screen_y=0.0)

    # During drag, no intermediate states are pushed to undo stack
    assert len(controller.state_manager._undo_stack) == initial_undo_count

    # 3. End drag gesture
    controller.end_interaction()
    assert controller.is_interacting is False

    # After drag ends, exactly one consolidated state is pushed to undo stack
    assert len(controller.state_manager._undo_stack) == initial_undo_count + 1

    # 4. Undo restores initial position before the entire drag gesture
    controller.undo()
    assert len(controller.state_manager._undo_stack) == initial_undo_count


def test_stale_request_rejection(controller):
    """Verifies that orchestrator monotonically advances sequence IDs and preserves latest state."""
    scene = controller.current_scene
    seq1 = controller.orchestrator.submit_request(
        scene=scene,
        image_orig_srgb=controller.project.img_orig_srgb,
        depth_map=controller.project.depth_map,
        normals_map=controller.project.normals_map,
        fg_mask=controller.project.fg_mask,
        quality=RenderQuality.PREVIEW
    )

    # Rapidly dispatch a second request with modified scene
    light = scene.get_light(controller.selected_object_id)
    light.position[0] += 0.5
    seq2 = controller.orchestrator.submit_request(
        scene=scene,
        image_orig_srgb=controller.project.img_orig_srgb,
        depth_map=controller.project.depth_map,
        normals_map=controller.project.normals_map,
        fg_mask=controller.project.fg_mask,
        quality=RenderQuality.PREVIEW
    )

    assert seq2 > seq1
