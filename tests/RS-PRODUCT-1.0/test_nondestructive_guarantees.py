"""
RELIGHT STUDIO — RS-PRODUCT-1.0
================================
Unit Tests: Non-Destructive Photographic Guarantees
Verifies that original photograph files, memory buffers, and protected image regions
remain 100% bitwise unmodified through all application workflows.
"""

import os
import hashlib
import tempfile
import shutil
import numpy as np
import pytest
from PIL import Image

from studio3a.scene import RenderQuality
from relight_studio.controller import StudioAppController
from relight_studio.project import RelightProject


@pytest.fixture
def sample_plate():
    td = tempfile.mkdtemp(prefix="relight_nondestruct_")
    img_path = os.path.join(td, "original_plate.png")
    test_img = np.random.randint(40, 220, size=(128, 128, 3), dtype=np.uint8)
    Image.fromarray(test_img).save(img_path)
    # Compute initial SHA-256 hash
    with open(img_path, "rb") as f:
        orig_hash = hashlib.sha256(f.read()).hexdigest()
    yield td, img_path, orig_hash, test_img
    shutil.rmtree(td, ignore_errors=True)


def test_source_file_on_disk_never_modified(sample_plate):
    td, img_path, orig_hash, _ = sample_plate
    ctrl = StudioAppController(sample_image_path=img_path, use_metal=False)

    # Perform multiple mutations and renders
    ctrl.add_light()
    ctrl.update_light_transform(ctrl.selected_object_id, pos=[2.0, 3.0, 1.0], width=1.2)
    ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)
    ctrl.request_render(quality=RenderQuality.FINAL, async_mode=False)

    # Re-compute disk hash of source photograph
    with open(img_path, "rb") as f:
        final_hash = hashlib.sha256(f.read()).hexdigest()

    assert orig_hash == final_hash, "Violation: Original image file on disk was modified!"


def test_in_memory_plate_bitwise_identical(sample_plate):
    td, img_path, _, test_img = sample_plate
    ctrl = StudioAppController(sample_image_path=img_path, use_metal=False)

    initial_buf_copy = ctrl.project.img_orig_srgb.copy()

    # 10 consecutive render passes with different parameters
    for i in range(10):
        ctrl.update_light_properties(ctrl.selected_object_id, intensity=1.0 + i * 0.2)
        ctrl.request_render(quality=RenderQuality.PREVIEW, async_mode=False)

    # In-memory original buffer must be bitwise identical
    assert np.array_equal(ctrl.project.img_orig_srgb, initial_buf_copy), (
        "Violation: In-memory original image buffer was altered during rendering!"
    )


def test_protected_region_zero_mutation(sample_plate):
    td, img_path, _, _ = sample_plate
    ctrl = StudioAppController(sample_image_path=img_path, use_metal=False)

    H, W = ctrl.project.img_orig_srgb.shape[:2]
    # Create synthetic protected region (e.g. background banner)
    prot_mask = np.zeros((H, W), dtype=bool)
    prot_mask[0:20, :] = True
    ctrl.project.protected_mask = prot_mask

    res = ctrl.request_render(quality=RenderQuality.FINAL, async_mode=False)
    relit = res["relit_srgb"]
    orig = ctrl.project.img_orig_srgb

    # Max difference on protected pixels
    diff = np.abs(relit[prot_mask] - orig[prot_mask])
    max_err = float(np.max(diff))
    assert max_err == 0.0, f"Violation: Protected region mutated! Max error: {max_err}"
