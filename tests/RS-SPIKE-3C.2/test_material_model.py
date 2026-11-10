"""
Unit Tests for Material Model & Scene Architecture
Relight Studio — RS-SPIKE-3C.2
"""

import json
import numpy as np
import pytest
from studio3a.material import MaterialData
from studio3a.scene import (
    StudioScene,
    SubjectProxyData,
    ReceiverData,
    AreaLightData,
    RenderSettingsData,
    SceneMetadata
)


def test_material_defaults_and_validation():
    """Validates default MaterialData fields and parameter boundary validation."""
    mat = MaterialData()
    mat.validate()
    assert mat.roughness == 0.50
    assert mat.metallic == 0.0
    assert mat.specular_f0 == 0.04
    assert mat.specular_intensity == 1.0

    # Bounds checking
    with pytest.raises(ValueError):
        MaterialData(roughness=-0.1).validate()
    with pytest.raises(ValueError):
        MaterialData(roughness=1.1).validate()
    with pytest.raises(ValueError):
        MaterialData(metallic=-0.1).validate()
    with pytest.raises(ValueError):
        MaterialData(metallic=1.1).validate()
    with pytest.raises(ValueError):
        MaterialData(specular_f0=-0.01).validate()
    with pytest.raises(ValueError):
        MaterialData(specular_intensity=-0.5).validate()
    with pytest.raises(ValueError):
        MaterialData(id="").validate()


def test_material_profiles_and_physical_invariants():
    """Validates predefined material profiles and energy rules."""
    # Fabric
    fabric = MaterialData.fabric()
    fabric.validate()
    assert fabric.roughness == 0.85
    assert fabric.metallic == 0.0
    assert fabric.specular_intensity < 1.0
    assert np.all(fabric.get_effective_diffuse_albedo() > 0.0)

    # Polished Metal
    gold = MaterialData.polished_metal(base_color=[1.0, 0.76, 0.33])
    gold.validate()
    assert gold.roughness == 0.08
    assert gold.metallic == 1.0
    # Conductor: diffuse albedo must be 0
    assert np.allclose(gold.get_effective_diffuse_albedo(), 0.0)
    # Specular F0 must match base color
    assert np.allclose(gold.get_effective_f0(), [1.0, 0.76, 0.33])

    # Smooth Plastic
    plastic = MaterialData.plastic()
    plastic.validate()
    assert plastic.roughness == 0.22
    assert plastic.metallic == 0.0
    assert np.allclose(plastic.get_effective_f0(), 0.04)


def test_scene_material_management():
    """Validates StudioScene material CRUD, selection, and assignment."""
    scene = StudioScene()
    assert len(scene.materials) == 1
    assert scene.active_material_id == scene.materials[0].id

    # Add materials
    mat_metal = scene.add_material(MaterialData.polished_metal(mat_id="gold_metal"))
    assert len(scene.materials) == 2
    assert scene.active_material_id == "gold_metal"

    # Assign to proxy
    scene.assign_material_to_subject("gold_metal")
    assert scene.subject.material.id == "gold_metal"
    assert scene.subject.material.metallic == 1.0


def test_legacy_scene_migration_v32():
    """
    Verifies that legacy scenes (from 3.0 or 3.1) missing material fields
    deserialize seamlessly and populate valid material defaults.
    """
    legacy_json = {
        "metadata": {"name": "Old Scene", "version": "3.1.0"},
        "camera": {"pos": [0, 1, 2], "target": [0, 0, 0]},
        "subject": {
            "proxy_type": "OBB",
            "position": [0, 0, 0],
            "dimensions": [0.5, 0.5, 0.5]
            # No material field
        },
        "receiver": {
            "receiver_type": "CYCLORAMA"
            # No material field
        },
        "lights": [
            {"id": "l1", "name": "Key", "position": [1, 2, 1], "width": 0.5, "height": 0.5}
        ]
        # No materials field
    }

    scene = StudioScene.from_dict(legacy_json)
    assert scene.metadata.version == "3.2.0"
    assert scene.subject.material is not None
    assert scene.subject.material.id == "mat_default"
    assert scene.receiver.material is not None
    assert scene.receiver.material.id == "mat_receiver"
    assert len(scene.materials) >= 1


def test_material_serialization_roundtrip():
    """Verifies that to_json -> from_json is deterministic and preserves material fields."""
    scene = StudioScene()
    scene.subject.material = MaterialData.rough_metal(mat_id="brushed_steel", base_color=[0.9, 0.9, 0.9])
    scene.add_material(scene.subject.material)

    json_str = scene.to_json()
    reloaded = StudioScene.from_json(json_str)

    assert reloaded.metadata.version == "3.2.0"
    assert reloaded.subject.material.id == "brushed_steel"
    assert reloaded.subject.material.roughness == 0.45
    assert reloaded.subject.material.metallic == 1.0
    assert np.allclose(reloaded.subject.material.base_color, [0.9, 0.9, 0.9])
    assert reloaded.to_json() == json_str
