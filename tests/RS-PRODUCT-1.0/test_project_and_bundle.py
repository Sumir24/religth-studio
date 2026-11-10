"""
RELIGHT STUDIO — RS-PRODUCT-1.0
================================
Unit Tests: Project Management & .relight Bundle Persistence
Verifies creation, non-destructive image preservation, relative path serialization,
and bundle loading determinism.
"""

import os
import shutil
import tempfile
import numpy as np
import pytest
from PIL import Image

from studio3a.scene import StudioScene, ProxyType, ReceiverType
from relight_studio.project import RelightProject


@pytest.fixture
def temp_workspace():
    td = tempfile.mkdtemp(prefix="relight_test_")
    # Create synthetic test image
    img_path = os.path.join(td, "test_input.png")
    test_img = np.full((128, 128, 3), 120, dtype=np.uint8)
    Image.fromarray(test_img).save(img_path)
    yield td, img_path
    shutil.rmtree(td, ignore_errors=True)


def test_project_creation(temp_workspace):
    td, img_path = temp_workspace
    proj = RelightProject(name="Test Shoot", image_path=img_path)

    assert proj.name == "Test Shoot"
    assert proj.img_orig_srgb is not None
    assert proj.img_orig_srgb.shape == (128, 128, 3)
    assert proj.scene.camera.width == 128
    assert proj.scene.camera.height == 128
    assert len(proj.scene.lights) >= 1


def test_bundle_save_and_load_roundtrip(temp_workspace):
    td, img_path = temp_workspace
    proj = RelightProject(name="Roundtrip Test", image_path=img_path)

    # Modify scene state
    proj.scene.subject.proxy_type = ProxyType.SUPERQUADRIC
    proj.scene.receiver.receiver_type = ReceiverType.CYCLORAMA
    proj.scene.lights[0].intensity = 3.5
    proj.scene.lights[0].position = [1.5, 2.0, 1.2]

    # Save to bundle
    bundle_path = os.path.join(td, "my_session.relight")
    saved_dir = proj.save(bundle_path)

    assert os.path.exists(saved_dir)
    assert os.path.exists(os.path.join(saved_dir, "project.json"))
    assert os.path.exists(os.path.join(saved_dir, "scene.json"))
    assert os.path.exists(os.path.join(saved_dir, "source"))

    # Load bundle
    loaded_proj = RelightProject.load(saved_dir)

    assert loaded_proj.name == "Roundtrip Test"
    assert loaded_proj.scene.subject.proxy_type == ProxyType.SUPERQUADRIC
    assert loaded_proj.scene.receiver.receiver_type == ReceiverType.CYCLORAMA
    assert loaded_proj.scene.lights[0].intensity == 3.5
    assert np.allclose(loaded_proj.scene.lights[0].position, [1.5, 2.0, 1.2])

    # Check original image preserved identically
    assert loaded_proj.img_orig_srgb is not None
    assert np.allclose(loaded_proj.img_orig_srgb, proj.img_orig_srgb)


def test_relative_path_portability(temp_workspace):
    td, img_path = temp_workspace
    proj = RelightProject(name="Portability Test", image_path=img_path)
    bundle_path = os.path.join(td, "portable.relight")
    proj.save(bundle_path)

    # Move bundle to new location
    new_bundle_path = os.path.join(td, "moved_bundle.relight")
    shutil.move(bundle_path, new_bundle_path)

    # Load moved bundle
    loaded = RelightProject.load(new_bundle_path)
    assert loaded.img_orig_srgb is not None
    assert loaded.img_orig_srgb.shape == (128, 128, 3)
