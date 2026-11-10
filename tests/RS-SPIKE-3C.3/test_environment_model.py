"""
RELIGHT STUDIO — RS-SPIKE-3C.3: UNIT TESTS
===========================================
Environment Data Model, Serialization, BRDF LUT & Precomputation Invariants
"""

import math
import pytest
import numpy as np

from studio3a.environment import EnvironmentData, PreintegratedBRDFLUT, EnvironmentMapProcessor
from studio3a.scene import StudioScene, SceneStateManager
from benchmarks.reference_ibl.synthetic_studio_env import SyntheticStudioEnvironment


def test_environment_data_validation():
    """Verifies physical parameter bounds and validation logic."""
    env = EnvironmentData()
    env.validate()

    assert env.enabled is False
    assert env.intensity == 1.0
    assert env.rotation_deg == 0.0
    assert env.diffuse_weight == 1.0
    assert env.specular_weight == 1.0

    # Negative intensity must fail
    with pytest.raises(ValueError, match="intensity cannot be negative"):
        EnvironmentData(intensity=-0.1).validate()

    # Out of range weights must fail
    with pytest.raises(ValueError, match="Diffuse weight out of valid range"):
        EnvironmentData(diffuse_weight=6.0).validate()

    with pytest.raises(ValueError, match="Specular weight out of valid range"):
        EnvironmentData(specular_weight=-0.5).validate()

    # Out of range tint
    with pytest.raises(ValueError, match="Tint channel out of valid range"):
        EnvironmentData(tint_rgb=[2.5, 1.0, 1.0]).validate()


def test_environment_serialization_roundtrip():
    """Verifies dictionary and JSON serialization round-tripping."""
    env = EnvironmentData(
        id="env_custom_studio",
        name="Custom Warm Studio",
        enabled=True,
        intensity=1.85,
        rotation_deg=45.0,
        diffuse_weight=1.2,
        specular_weight=0.9,
        is_hdr=True,
        tint_rgb=[1.0, 0.95, 0.90]
    )
    d = env.to_dict()
    reconstructed = EnvironmentData.from_dict(d)

    assert reconstructed.id == env.id
    assert reconstructed.name == env.name
    assert reconstructed.intensity == env.intensity
    assert reconstructed.rotation_deg == env.rotation_deg
    assert reconstructed.diffuse_weight == env.diffuse_weight
    assert reconstructed.specular_weight == env.specular_weight
    assert reconstructed.tint_rgb == env.tint_rgb


def test_scene_environment_integration_and_undo_redo():
    """Verifies that StudioScene encapsulates EnvironmentData and survives SceneStateManager undo/redo."""
    scene = StudioScene()
    assert hasattr(scene, "environment")
    assert isinstance(scene.environment, EnvironmentData)

    manager = SceneStateManager(scene)

    # Mutate environment rotation and intensity
    scene2 = StudioScene.from_json(scene.to_json())
    scene2.environment.rotation_deg = 90.0
    scene2.environment.intensity = 2.0
    manager.push_state(scene2)

    assert manager.current_scene.environment.rotation_deg == 90.0
    assert manager.current_scene.environment.intensity == 2.0

    # Undo
    assert manager.can_undo
    manager.undo()
    assert manager.current_scene.environment.rotation_deg == 0.0
    assert manager.current_scene.environment.intensity == 1.0

    # Redo
    assert manager.can_redo
    manager.redo()
    assert manager.current_scene.environment.rotation_deg == 90.0
    assert manager.current_scene.environment.intensity == 2.0


def test_preintegrated_brdf_lut_invariants():
    """
    Verifies mathematical invariants of the Preintegrated 2D BRDF LUT:
      1. Correct shape (256, 256, 2)
      2. Values in physically valid ranges [0, 1.05]
      3. Energy conservation: scale + bias <= 1.005 for all (nv, roughness)
      4. Grazing angle asymptotic convergence: at nv -> 0, scale + bias -> 1.0
    """
    lut = PreintegratedBRDFLUT.get_lut(size=256, n_samples=256)
    assert lut.shape == (256, 256, 2)

    scale = lut[..., 0]
    bias = lut[..., 1]

    # Non-negative
    assert np.all(scale >= 0.0)
    assert np.all(bias >= 0.0)

    # Upper bound
    assert np.all(scale <= 1.05)
    assert np.all(bias <= 1.05)

    # Total directional-hemispherical reflectance for white furnace (F0 = 1.0):
    # R(nv) = 1.0 * scale + bias
    r_total = scale + bias
    assert np.all(r_total <= 1.005), f"BRDF LUT energy violation: max sum = {np.max(r_total)}"

    # At grazing angle nv -> 0 (index 0 along X axis):
    grazing_sum = r_total[:, 0]
    assert np.all(grazing_sum >= 0.85), f"Grazing angle Fresnel did not approach unity: min = {np.min(grazing_sum)}"


def test_environment_map_convolution():
    """Verifies diffuse irradiance and specular prefiltered maps from synthetic studio environment."""
    env = SyntheticStudioEnvironment(width=256, height=128)
    
    # 1. Diffuse Irradiance
    irr = EnvironmentMapProcessor.compute_diffuse_irradiance_map(env.data, out_width=64, out_height=32, n_samples=64)
    assert irr.shape == (32, 64, 3)
    assert np.all(irr >= 0.0)
    assert np.all(np.isfinite(irr))
    # Diffuse convolution should be strictly smoother than raw environment:
    assert float(np.max(irr)) < float(np.max(env.data))
    assert float(np.min(irr)) > float(np.min(env.data))

    # 2. Specular Prefiltered Map
    spec_04 = EnvironmentMapProcessor.compute_specular_prefiltered_map(env.data, roughness=0.04, out_width=64, out_height=32, n_samples=64)
    spec_50 = EnvironmentMapProcessor.compute_specular_prefiltered_map(env.data, roughness=0.50, out_width=64, out_height=32, n_samples=64)

    assert spec_04.shape == (32, 64, 3)
    assert spec_50.shape == (32, 64, 3)
    assert float(np.max(spec_04)) > float(np.max(spec_50)), "Peak radiance must blur down with roughness!"
