"""
RELIGHT STUDIO — RS-SPIKE-3C.2: ARTIST INTERACTION & WORKSPACE TEST SUITE
========================================================================
Validates interactive artist controls in StudioWorkspaceSession:
  1. Material profile switching (Fabric, Marble, Plastic, Rough Metal, Polished Metal)
  2. Continuous slider parameter adjustment (roughness, metallic, F0, intensity)
  3. Specular transport toggle and specular-only diagnostic mode
  4. Undo / Redo history integrity
  5. Deterministic JSON scene preset save & load
"""

import os
import tempfile
import numpy as np
import pytest

from studio3a.workspace import StudioWorkspaceSession
from studio3a.material import MaterialData
from studio3a.scene import RenderQuality


@pytest.fixture
def workspace_session():
    """Initializes workspace session with test assets."""
    sess = StudioWorkspaceSession(use_metal=True)
    return sess


def test_workspace_material_profile_selection(workspace_session):
    sess = workspace_session
    
    # 1. Switch to Marble
    res_marble = sess.set_material_profile("marble")
    assert res_marble["relit_srgb"] is not None
    assert sess.state_manager.current_scene.subject.material.name == "Honed Marble"
    assert sess.state_manager.current_scene.subject.material.roughness == 0.35
    assert sess.state_manager.current_scene.subject.material.metallic == 0.0

    # 2. Switch to Polished Metal
    res_metal = sess.set_material_profile("polished_metal")
    assert sess.state_manager.current_scene.subject.material.name == "Polished Chrome / Gold"
    assert sess.state_manager.current_scene.subject.material.roughness == 0.08
    assert sess.state_manager.current_scene.subject.material.metallic == 1.0


def test_workspace_material_parameter_adjustment(workspace_session):
    sess = workspace_session

    res = sess.update_material_params(
        roughness=0.28,
        metallic=0.65,
        specular_f0=0.08,
        specular_intensity=1.5
    )
    assert res["relit_srgb"] is not None
    mat = sess.state_manager.current_scene.subject.material
    assert mat.roughness == 0.28
    assert mat.metallic == 0.65
    assert mat.specular_f0 == 0.08
    assert mat.specular_intensity == 1.5


def test_workspace_specular_toggles(workspace_session):
    sess = workspace_session

    # Toggle specular OFF
    sess.toggle_specular(False)
    assert sess.state_manager.current_scene.render_settings.enable_specular is False
    res_off = sess.execute_render(RenderQuality.PREVIEW)
    # Specular radiance should be zero
    if "specular_radiance" in res_off:
        assert np.max(res_off["specular_radiance"]) == 0.0

    # Toggle specular ON
    sess.toggle_specular(True)
    assert sess.state_manager.current_scene.render_settings.enable_specular is True

    # Toggle Specular-Only Inspection
    sess.toggle_specular_only(True)
    assert sess.state_manager.current_scene.render_settings.specular_only is True
    res_spec_only = sess.execute_render(RenderQuality.PREVIEW)
    assert res_spec_only["relit_srgb"] is not None


def test_workspace_undo_redo_material_history(workspace_session):
    sess = workspace_session

    # Baseline roughness
    initial_roughness = sess.state_manager.current_scene.subject.material.roughness

    # Step 1: Set to Fabric
    sess.set_material_profile("fabric")
    assert sess.state_manager.current_scene.subject.material.roughness == 0.85

    # Step 2: Set to Plastic
    sess.set_material_profile("plastic")
    assert sess.state_manager.current_scene.subject.material.roughness == 0.22

    # Step 3: Undo -> Should return to Fabric
    sess.undo_action()
    assert sess.state_manager.current_scene.subject.material.roughness == 0.85

    # Step 4: Undo again -> Should return to Initial
    sess.undo_action()
    assert sess.state_manager.current_scene.subject.material.roughness == initial_roughness

    # Step 5: Redo -> Should return to Fabric
    sess.redo_action()
    assert sess.state_manager.current_scene.subject.material.roughness == 0.85

    # Step 6: Redo again -> Should return to Plastic
    sess.redo_action()
    assert sess.state_manager.current_scene.subject.material.roughness == 0.22


def test_workspace_scene_preset_save_and_load(workspace_session):
    sess = workspace_session

    sess.set_material_profile("marble")
    sess.update_material_params(roughness=0.31, metallic=0.15)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        sess.save_scene(tmp_path)
        assert os.path.exists(tmp_path)

        # Create new fresh session and load
        sess2 = StudioWorkspaceSession(use_metal=True)
        sess2.load_scene(tmp_path)

        loaded_mat = sess2.state_manager.current_scene.subject.material
        assert loaded_mat.roughness == 0.31
        assert loaded_mat.metallic == 0.15
        assert sess2.state_manager.current_scene.metadata.version == "3.2.0"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
