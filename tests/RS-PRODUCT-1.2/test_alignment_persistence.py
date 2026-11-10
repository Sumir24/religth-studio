"""
RS-PRODUCT-1.2 Test Suite: Alignment Persistence & Schema 1.2.0
===============================================================
Validates project bundle roundtrip, Schema 1.2.0 manifest format,
source photograph SHA-256 preservation, and explicit missing asset handling.
"""

import os
import tempfile
import hashlib
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from studio3a.scene import StudioScene
from relight_studio.project import RelightProject
from relight_studio.controller import StudioAppController


def test_schema_1_2_0_bundle_roundtrip():
    """Verify saving and loading project bundles with Schema 1.2.0 preserves alignment and camera state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        photo_path = os.path.join(tmpdir, "test_plate.png")
        arr = (np.random.rand(256, 384, 3) * 255).astype(np.uint8)
        Image.fromarray(arr).save(photo_path)
        orig_sha = hashlib.sha256(open(photo_path, "rb").read()).hexdigest()

        # Create and customize scene
        ctrl = StudioAppController(sample_image_path=photo_path)
        ctrl.apply_camera_preset("85mm")
        ctrl.update_subject_proxy_params(
            position=[0.1, 0.45, -0.2],
            rotation_deg=[15.0, -25.0, 10.0],
            dimensions=[0.3, 0.4, 0.5]
        )
        ctrl.update_receiver_params(receiver_type="CYCLORAMA", ground_y=0.08, cove_radius=0.55)

        # Save bundle
        bundle_path = os.path.join(tmpdir, "session_test.relight")
        saved_path = ctrl.save_project(bundle_path)
        assert os.path.exists(saved_path)

        # Load back
        loaded_proj = RelightProject.load(saved_path)
        assert loaded_proj.VERSION == "1.2.0"
        assert loaded_proj.image_sha256 == orig_sha
        assert loaded_proj.is_missing_assets is False
        assert len(loaded_proj.missing_assets) == 0

        # Verify camera & alignment integrity
        cam = loaded_proj.scene.camera
        assert abs(cam.focal_length_mm - 85.0) < 0.2
        assert abs(cam.fov_deg - 16.08) < 0.2

        subj = loaded_proj.scene.subject
        assert np.allclose(subj.position, [0.1, 0.45, -0.2])
        assert np.allclose(subj.rotation_deg, [15.0, -25.0, 10.0])
        assert np.allclose(subj.dimensions, [0.3, 0.4, 0.5])

        rec = loaded_proj.scene.receiver
        assert abs(rec.ground_y - 0.08) < 1e-4
        assert abs(rec.cove_radius - 0.55) < 1e-4


def test_explicit_missing_asset_handling():
    """Verify that if photograph asset is removed from bundle, is_missing_assets flag is set explicitly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        photo_path = os.path.join(tmpdir, "plate.png")
        arr = (np.random.rand(128, 128, 3) * 255).astype(np.uint8)
        Image.fromarray(arr).save(photo_path)

        ctrl = StudioAppController(sample_image_path=photo_path)
        bundle_path = os.path.join(tmpdir, "missing_test.relight")
        saved_path = ctrl.save_project(bundle_path)

        # Simulate missing photograph asset by deleting source image
        source_dir = Path(saved_path) / "source"
        for img_file in list(source_dir.glob("*")):
            img_file.unlink()

        # Load bundle - should load safely without crashing but flag missing assets
        loaded = RelightProject.load(saved_path)
        assert loaded.is_missing_assets is True
        assert len(loaded.missing_assets) > 0
        assert "original_image" in loaded.missing_assets[0]

