"""
RELIGHT STUDIO — RS-PRODUCT-1.0
================================
Project Management & Non-Destructive Bundle Specification
Handles creation, serialization, deserialization, and asset preservation for .relight project bundles.
"""

from __future__ import annotations

import os
import json
import time
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
from PIL import Image
import cv2

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, RenderSettingsData, ProxyType, ReceiverType,
    EnergyConvention, RenderQuality
)
from studio3a.material import MaterialData
from studio3a.environment import EnvironmentData


class RelightProject:
    """
    Authoritative Relight Studio project representation.
    Ensures non-destructive source image handling, relative asset resolution,
    and complete scene serialization.
    """
    VERSION = "1.0.0"

    def __init__(
        self,
        name: str = "Untitled Project",
        image_path: Optional[str] = None,
        scene: Optional[StudioScene] = None,
        project_dir: Optional[str] = None
    ):
        self.project_id: str = str(uuid.uuid4())
        self.name: str = name
        self.project_dir: Optional[str] = project_dir
        self.created_at: float = time.time()
        self.modified_at: float = self.created_at

        # Authoritative scene
        self.scene: StudioScene = scene or StudioScene()

        # Image Assets
        self.image_path: Optional[str] = image_path
        self.depth_path: Optional[str] = None
        self.normals_path: Optional[str] = None

        # Pixel Buffers (float32 linear / sRGB)
        self.img_orig_srgb: Optional[np.ndarray] = None
        self.depth_map: Optional[np.ndarray] = None
        self.normals_map: Optional[np.ndarray] = None
        self.fg_mask: Optional[np.ndarray] = None
        self.protected_mask: Optional[np.ndarray] = None

        # Rendered Output Cache
        self.last_render_output: Optional[Dict[str, Any]] = None

        if self.image_path and os.path.exists(self.image_path):
            self.load_image_assets(self.image_path)

    def load_image_assets(
        self,
        image_path: str,
        depth_path: Optional[str] = None,
        normals_path: Optional[str] = None
    ) -> None:
        """
        Loads the source photograph, extracting dimensions and initializing
        immutable image buffers and proxy guidance maps.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Source photograph not found: {image_path}")

        self.image_path = os.path.abspath(image_path)
        im = Image.open(self.image_path).convert("RGB")
        W, H = im.size

        # Immutable original image sRGB float32 in [0, 1]
        self.img_orig_srgb = np.array(im, dtype=np.float32) / 255.0

        # Load or generate depth map
        if depth_path and os.path.exists(depth_path):
            self.depth_path = os.path.abspath(depth_path)
            d_im = Image.open(self.depth_path)
            d_arr = np.array(d_im, dtype=np.float32) / 255.0
            if d_arr.ndim == 3:
                d_arr = d_arr[..., 0]
            self.depth_map = cv2.resize(d_arr, (W, H), interpolation=cv2.INTER_LINEAR)
        else:
            # Fallback planar gradient depth for stage placement
            y_coords = np.linspace(0.8, 0.2, H, dtype=np.float32)[:, None]
            self.depth_map = np.tile(y_coords, (1, W))

        # Load or generate surface normals
        if normals_path and os.path.exists(normals_path):
            self.normals_path = os.path.abspath(normals_path)
            n_im = Image.open(self.normals_path)
            n_arr = (np.array(n_im, dtype=np.float32) / 255.0) * 2.0 - 1.0
            norm = np.clip(np.linalg.norm(n_arr, axis=-1, keepdims=True), 1e-6, None)
            self.normals_map = cv2.resize(n_arr / norm, (W, H), interpolation=cv2.INTER_LINEAR)
        else:
            # Camera-facing normal with subtle hemisphere tilt
            self.normals_map = np.zeros((H, W, 3), dtype=np.float32)
            self.normals_map[..., 2] = -1.0

        # Foreground mask & ground segmentation
        ground_y = int(H * 0.85)
        self.fg_mask = (self.depth_map > 0.35) & (np.arange(H)[:, None] <= ground_y)

        # Synchronize camera resolution with photograph
        self.scene.camera.width = W
        self.scene.camera.height = H
        self.modified_at = time.time()

    def to_dict(self, relative_to_dir: Optional[str] = None) -> Dict[str, Any]:
        """Serializes project metadata and scene state to dictionary."""
        img_ref = self.image_path
        if relative_to_dir and self.image_path:
            try:
                img_ref = os.path.relpath(self.image_path, relative_to_dir)
            except ValueError:
                img_ref = self.image_path

        return {
            "version": self.VERSION,
            "project_id": self.project_id,
            "name": self.name,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "image_path": img_ref,
            "depth_path": self.depth_path,
            "normals_path": self.normals_path,
            "scene": self.scene.to_dict()
        }

    def save(self, bundle_path: str) -> str:
        """
        Saves project into a portable .relight directory bundle:
          bundle_path/
            project.json
            scene.json
            source/
              original_image.<ext>
        """
        bundle_dir = Path(bundle_path)
        if not str(bundle_dir).endswith(".relight"):
            bundle_dir = Path(str(bundle_dir) + ".relight")

        bundle_dir.mkdir(parents=True, exist_ok=True)
        source_dir = bundle_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        # Copy original image if not already inside the bundle
        target_img_name = "original_image" + os.path.splitext(self.image_path)[1]
        target_img_path = source_dir / target_img_name

        if os.path.abspath(self.image_path) != os.path.abspath(target_img_path):
            shutil.copy2(self.image_path, target_img_path)

        # Save project manifest with relative asset path
        rel_img_path = os.path.relpath(target_img_path, bundle_dir)
        manifest = {
            "version": self.VERSION,
            "project_id": self.project_id,
            "name": self.name,
            "created_at": self.created_at,
            "modified_at": time.time(),
            "image_file": rel_img_path,
            "scene_file": "scene.json"
        }

        with open(bundle_dir / "project.json", "w") as f:
            json.dump(manifest, f, indent=2)

        with open(bundle_dir / "scene.json", "w") as f:
            f.write(self.scene.to_json(indent=2))

        self.project_dir = str(bundle_dir)
        self.modified_at = manifest["modified_at"]
        return str(bundle_dir)

    @classmethod
    def load(cls, bundle_path: str) -> RelightProject:
        """Loads a project from a .relight bundle."""
        bundle_dir = Path(bundle_path)
        if not bundle_dir.exists():
            raise FileNotFoundError(f"Project bundle not found: {bundle_path}")

        proj_file = bundle_dir / "project.json"
        if not proj_file.exists():
            raise FileNotFoundError(f"Invalid bundle: missing project.json in {bundle_path}")

        with open(proj_file, "r") as f:
            manifest = json.load(f)

        scene_file = bundle_dir / manifest.get("scene_file", "scene.json")
        with open(scene_file, "r") as f:
            scene = StudioScene.from_json(f.read())

        img_rel = manifest.get("image_file", "source/original_image.png")
        img_abs = str((bundle_dir / img_rel).resolve())

        proj = cls(
            name=manifest.get("name", bundle_dir.stem),
            image_path=img_abs,
            scene=scene,
            project_dir=str(bundle_dir)
        )
        proj.project_id = manifest.get("project_id", proj.project_id)
        proj.created_at = manifest.get("created_at", proj.created_at)
        proj.modified_at = manifest.get("modified_at", proj.modified_at)
        return proj
