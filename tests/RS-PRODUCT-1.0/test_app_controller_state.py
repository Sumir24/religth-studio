"""
RELIGHT STUDIO — RS-PRODUCT-1.0
================================
Unit Tests: StudioAppController Authoritative State & Hierarchy
Verifies scene updates, object selection, undo/redo, hierarchy generation,
and inspector data binding.
"""

import os
import numpy as np
import pytest

from studio3a.scene import EnergyConvention, RenderQuality, ProxyType, ReceiverType
from relight_studio.controller import StudioAppController


@pytest.fixture
def controller():
    # Use synthetic sample image
    img_path = "benchmarks/reference_ibl/diagnostic_boards/synthetic_studio_env_preview.png"
    return StudioAppController(sample_image_path=img_path, use_metal=False)


def test_controller_initial_state(controller):
    scene = controller.current_scene
    assert len(scene.lights) >= 1
    assert controller.selected_object_id in [l.id for l in scene.lights]
    hierarchy = controller.get_scene_hierarchy()
    assert "scene" in hierarchy
    assert len(hierarchy["scene"]["children"]) == 5


def test_light_lifecycle_and_selection(controller):
    init_count = len(controller.current_scene.lights)

    # 1. Add Light
    new_id = controller.add_light()
    assert len(controller.current_scene.lights) == init_count + 1
    assert controller.selected_object_id == new_id

    # 2. Modify Transform
    controller.update_light_transform(new_id, pos=[2.0, 3.0, 1.5], width=1.0, height=1.0)
    l = controller.current_scene.get_light(new_id)
    assert np.allclose(l.position, [2.0, 3.0, 1.5])
    assert l.width == 1.0

    # 3. Modify Properties
    controller.update_light_properties(new_id, intensity=2.5, temperature_kelvin=4500.0)
    assert l.intensity == 2.5
    assert l.temperature_kelvin == 4500.0

    # 4. Duplicate Light
    dup_id = controller.duplicate_light(new_id)
    assert len(controller.current_scene.lights) == init_count + 2
    assert controller.selected_object_id == dup_id

    # 5. Delete Light
    controller.delete_light(dup_id)
    assert len(controller.current_scene.lights) == init_count + 1
    assert controller.current_scene.get_light(dup_id) is None


def test_transactional_undo_redo(controller):
    scene = controller.current_scene
    target_id = scene.lights[0].id
    orig_pos = list(scene.lights[0].position)

    # Modify light position
    controller.update_light_transform(target_id, pos=[orig_pos[0] + 1.0, orig_pos[1], orig_pos[2]])
    assert not np.allclose(controller.current_scene.get_light(target_id).position, orig_pos)

    # Undo
    controller.undo()
    assert np.allclose(controller.current_scene.get_light(target_id).position, orig_pos)

    # Redo
    controller.redo()
    assert np.allclose(controller.current_scene.get_light(target_id).position, [orig_pos[0] + 1.0, orig_pos[1], orig_pos[2]])


def test_inspector_data_binding(controller):
    # Test light inspector
    light_id = controller.current_scene.lights[0].id
    controller.select_object(light_id)
    data = controller.get_inspector_data()
    assert data["type"] == "light"
    assert data["id"] == light_id
    assert "intensity" in data
    assert "temperature_kelvin" in data

    # Test subject/material inspector
    controller.select_object("subject")
    mat_data = controller.get_inspector_data()
    assert mat_data["type"] == "subject"
    assert "roughness" in mat_data
    assert "metallic" in mat_data

    # Test environment inspector
    controller.select_object("environment")
    env_data = controller.get_inspector_data()
    assert env_data["type"] == "environment"
    assert "enabled" in env_data
    assert "intensity" in env_data


def test_material_profile_update(controller):
    controller.set_material_profile("polished_metal")
    mat = controller.current_scene.subject.material
    assert mat.metallic == 1.0
    assert mat.roughness <= 0.10

    controller.set_material_profile("fabric")
    mat2 = controller.current_scene.subject.material
    assert mat2.metallic == 0.0
    assert mat2.roughness >= 0.70
