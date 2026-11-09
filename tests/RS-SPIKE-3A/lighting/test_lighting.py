"""
Unit Tests for Lighting Engine (RS-SPIKE-3A)
"""

import pytest
import numpy as np
from studio3a.lighting import RectangularAreaLight, kelvin_to_linear_rgb
from studio3a.scene import EnergyConvention


def test_kelvin_to_linear_rgb():
    # 5600K daylight should be near neutral / balanced
    rgb_5600 = kelvin_to_linear_rgb(5600.0)
    assert len(rgb_5600) == 3
    assert np.all(rgb_5600 > 0.0)
    # Warm 2700K must have more red than blue
    rgb_2700 = kelvin_to_linear_rgb(2700.0)
    assert rgb_2700[0] > rgb_2700[2]
    # Cool 8000K must have more blue than red
    rgb_8000 = kelvin_to_linear_rgb(8000.0)
    assert rgb_8000[2] > rgb_8000[0]


def test_area_light_energy_conventions():
    # FIXED_RADIANCE: when width doubles, radiance is unchanged, but area doubles
    l1 = RectangularAreaLight(width=0.5, height=0.5, intensity=2.0, energy_convention=EnergyConvention.FIXED_RADIANCE)
    l2 = RectangularAreaLight(width=1.0, height=0.5, intensity=2.0, energy_convention=EnergyConvention.FIXED_RADIANCE)
    assert np.allclose(l1.get_emitted_radiance(), l2.get_emitted_radiance())
    assert abs(l2.area - 2.0 * l1.area) < 1e-5

    # FIXED_POWER: when area doubles, radiance is halved
    lp1 = RectangularAreaLight(width=0.5, height=0.5, intensity=2.0, energy_convention=EnergyConvention.FIXED_POWER)
    lp2 = RectangularAreaLight(width=1.0, height=0.5, intensity=2.0, energy_convention=EnergyConvention.FIXED_POWER)
    assert np.allclose(lp1.get_emitted_radiance(), lp2.get_emitted_radiance() * 2.0)


def test_area_light_sample_emitter_points():
    light = RectangularAreaLight(position=(1.0, 2.0, 3.0), width=0.4, height=0.6)
    pts = light.sample_emitter_points(n_samples=16, seed=42)
    assert pts.shape == (16, 3)
    # Centroid of samples should be near emitter position
    centroid = np.mean(pts, axis=0)
    assert np.allclose(centroid, light.pos, atol=0.05)


def test_area_light_distance_attenuation_inverse_square():
    light = RectangularAreaLight(
        position=(0.0, 0.0, 0.0), rotation_euler=(0.0, 0.0, 0.0),
        width=0.1, height=0.1, intensity=10.0,
        energy_convention=EnergyConvention.FIXED_RADIANCE
    )
    # Emitter points down -Z (normal=[0, 0, -1])
    # Test two points along -Z: at z = -1.0 and at z = -2.0
    p1 = np.array([[[0.0, 0.0, -1.0]]], dtype=np.float32)
    n1 = np.array([[[0.0, 0.0, 1.0]]], dtype=np.float32)  # Facing light
    
    p2 = np.array([[[0.0, 0.0, -2.0]]], dtype=np.float32)
    n2 = np.array([[[0.0, 0.0, 1.0]]], dtype=np.float32)
    
    irr1 = light.evaluate_unshadowed_irradiance(p1, n1, n_samples=16)
    irr2 = light.evaluate_unshadowed_irradiance(p2, n2, n_samples=16)
    
    ratio = irr1[0, 0, 0] / irr2[0, 0, 0]
    # Distance doubled -> irradiance should drop by factor of ~4
    assert abs(ratio - 4.0) < 0.25
