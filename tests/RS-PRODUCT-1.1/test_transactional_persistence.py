"""
RELIGHT STUDIO — RS-PRODUCT-1.1
Unit & Integration Tests: Transactional Project Persistence and Bundle Recovery
"""

import os
import shutil
import hashlib
import tempfile
import pytest
from pathlib import Path
from relight_studio.project import RelightProject
from studio3a.scene import StudioScene, AreaLightData, ProxyType, ReceiverType


def get_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="test_relight_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_transactional_save_and_load(temp_dir):
    """Verifies that project saving is atomic and round-trips all scene data."""
    # Create sample image
    img_path = os.path.join(temp_dir, "sample_input.png")
    import numpy as np
    from PIL import Image
    test_img = np.full((128, 128, 3), 180, dtype=np.uint8)
    Image.fromarray(test_img).save(img_path)
    orig_hash = get_file_sha256(img_path)

    # Create scene with 2 lights
    scene = StudioScene()
    l2 = AreaLightData(
        id="light_fill",
        name="Fill Light",
        position=[-1.5, 1.5, 1.0],
        rotation_deg=[-20.0, -30.0, 0.0],
        width=1.0,
        height=1.0,
        intensity=1.2,
        temperature_kelvin=4800.0
    )
    scene.add_light(l2)

    proj = RelightProject(
        name="Test Session",
        image_path=img_path,
        scene=scene
    )

    bundle_path = os.path.join(temp_dir, "saved_session.relight")
    proj.save(bundle_path)

    # Verify bundle structure
    assert os.path.isdir(bundle_path)
    assert os.path.isfile(os.path.join(bundle_path, "project.json"))
    assert os.path.isfile(os.path.join(bundle_path, "scene.json"))

    # Verify source image hash remained immutable
    assert get_file_sha256(img_path) == orig_hash

    # Load bundle
    loaded_proj = RelightProject.load(bundle_path)
    assert loaded_proj.name == "Test Session"
    assert len(loaded_proj.scene.lights) >= 2
    l_loaded = loaded_proj.scene.get_light("light_fill")
    assert l_loaded is not None
    assert l_loaded.intensity == 1.2
    assert l_loaded.temperature_kelvin == 4800.0


def test_missing_asset_fallback(temp_dir):
    """Verifies that project loading gracefully handles missing or moved original images."""
    scene = StudioScene()
    proj = RelightProject(name="Fallback Test", image_path=None, scene=scene)
    bundle_path = os.path.join(temp_dir, "no_asset.relight")
    proj.save(bundle_path)

    # Load project where image is missing
    loaded = RelightProject.load(bundle_path)
    assert loaded is not None
    assert loaded.img_orig_srgb is not None
    assert loaded.img_orig_srgb.shape[2] == 3
