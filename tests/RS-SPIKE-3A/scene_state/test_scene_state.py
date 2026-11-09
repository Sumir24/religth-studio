"""
Unit Tests for StudioScene and SceneStateManager (RS-SPIKE-3A)
"""

import pytest
import numpy as np
from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, RenderSettingsData, SceneStateManager,
    ProxyType, ReceiverType, EnergyConvention, RenderQuality
)


def test_scene_default_instantiation_and_validation():
    scene = StudioScene()
    scene.validate()
    assert scene.camera.width == 384
    assert scene.camera.height == 256
    assert len(scene.lights) == 1
    assert scene.subject.proxy_type == ProxyType.OBB


def test_scene_serialization_roundtrip():
    scene = StudioScene()
    scene.camera.pos = [1.0, 2.0, 3.0]
    scene.subject.dimensions = [0.4, 0.5, 0.6]
    scene.lights[0].intensity = 2.5
    scene.lights[0].energy_convention = EnergyConvention.FIXED_POWER

    d = scene.to_dict()
    restored = StudioScene.from_dict(d)
    assert restored.camera.pos == [1.0, 2.0, 3.0]
    assert restored.subject.dimensions == [0.4, 0.5, 0.6]
    assert restored.lights[0].intensity == 2.5
    assert restored.lights[0].energy_convention == EnergyConvention.FIXED_POWER

    json_str = scene.to_json()
    from_json_scene = StudioScene.from_json(json_str)
    assert from_json_scene.to_dict() == scene.to_dict()


def test_scene_rejects_invalid_parameters():
    scene = StudioScene()
    
    # Negative dimensions
    scene.subject.dimensions = [-0.1, 0.2, 0.3]
    with pytest.raises(ValueError):
        scene.validate()
    scene.subject.dimensions = [0.1, 0.2, 0.3]

    # Non-finite float (NaN)
    scene.camera.pos = [float('nan'), 1.0, 2.0]
    with pytest.raises(ValueError):
        scene.validate()
    scene.camera.pos = [0.0, 1.0, 2.0]

    # Empty lights
    scene.lights = []
    with pytest.raises(ValueError):
        scene.validate()


def test_scene_state_manager_undo_redo():
    scene0 = StudioScene()
    mgr = SceneStateManager(scene0)
    assert not mgr.can_undo
    assert not mgr.can_redo

    # Push state 1
    scene1 = StudioScene.from_dict(scene0.to_dict())
    scene1.subject.dimensions = [0.5, 0.5, 0.5]
    mgr.push_state(scene1)
    assert mgr.can_undo
    assert not mgr.can_redo
    assert mgr.current_scene.subject.dimensions == [0.5, 0.5, 0.5]

    # Push state 2
    scene2 = StudioScene.from_dict(scene1.to_dict())
    scene2.lights[0].intensity = 3.0
    mgr.push_state(scene2)
    assert mgr.current_scene.lights[0].intensity == 3.0

    # Undo to state 1
    assert mgr.undo()
    assert mgr.current_scene.lights[0].intensity == 1.0
    assert mgr.current_scene.subject.dimensions == [0.5, 0.5, 0.5]
    assert mgr.can_redo

    # Undo to state 0
    assert mgr.undo()
    assert mgr.current_scene.subject.dimensions == [0.35, 0.35, 0.35]
    assert not mgr.can_undo

    # Redo back to state 1
    assert mgr.redo()
    assert mgr.current_scene.subject.dimensions == [0.5, 0.5, 0.5]
