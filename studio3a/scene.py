"""
RELIGHT STUDIO — RS-SPIKE-3A: SCENE MODEL & STATE MANAGEMENT
============================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Architectural Invariant: Scene state is authoritative, serializable,
independent of UI state, and supports deterministic replay with undo/redo.
"""

from __future__ import annotations

import json
import time
import math
import copy
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


class ProxyType(str, Enum):
    OBB = "OBB"
    SUPERQUADRIC = "SUPERQUADRIC"
    MESH = "MESH"


class ReceiverType(str, Enum):
    PLANE = "PLANE"
    CYCLORAMA = "CYCLORAMA"


class EnergyConvention(str, Enum):
    FIXED_RADIANCE = "FIXED_RADIANCE"
    FIXED_POWER = "FIXED_POWER"


class RenderQuality(str, Enum):
    PREVIEW = "PREVIEW"
    FINAL = "FINAL"


def validate_finite_floats(obj: Any, path: str = "scene") -> None:
    """Recursively validates that all numerical fields contain finite floats."""
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"Non-finite float detected at '{path}': {obj}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            validate_finite_floats(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            validate_finite_floats(v, f"{path}[{i}]")


@dataclass
class SceneMetadata:
    name: str = "Untitled Studio Scene"
    created_at: float = field(default_factory=time.time)
    version: str = "3.0.0"
    author: str = "Relight Artist"


@dataclass
class CameraData:
    pos: List[float] = field(default_factory=lambda: [0.0, 1.2, 2.5])
    target: List[float] = field(default_factory=lambda: [0.0, 0.35, 0.0])
    up: List[float] = field(default_factory=lambda: [0.0, 1.0, 0.0])
    fov_deg: float = 45.0
    width: int = 384
    height: int = 256
    focal_length_mm: float = 50.0

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Invalid image dimensions: {self.width}x{self.height}")
        if not (1.0 <= self.fov_deg <= 170.0):
            raise ValueError(f"FOV out of valid range [1, 170]: {self.fov_deg}")
        if np.allclose(self.pos, self.target):
            raise ValueError("Camera position cannot coincide with camera target.")


@dataclass
class SubjectProxyData:
    proxy_type: ProxyType = ProxyType.OBB
    position: List[float] = field(default_factory=lambda: [0.0, 0.35, 0.0])
    rotation_deg: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # Euler angles [pitch, yaw, roll]
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    # Dimensions (half-extents for OBB [ex, ey, ez], radii for superquadric [rx, ry, rz])
    dimensions: List[float] = field(default_factory=lambda: [0.35, 0.35, 0.35])
    # Superquadric shape exponents (e1=vertical, e2=horizontal)
    sq_exponents: List[float] = field(default_factory=lambda: [1.0, 1.0])
    # Mesh filename or descriptor (if MESH)
    mesh_path: Optional[str] = None
    visible: bool = True

    def validate(self) -> None:
        for d in self.dimensions:
            if d <= 0.0:
                raise ValueError(f"Proxy dimensions must be strictly positive: {self.dimensions}")
        for s in self.scale:
            if s <= 0.0:
                raise ValueError(f"Proxy scale must be strictly positive: {self.scale}")
        for e in self.sq_exponents:
            if not (0.05 <= e <= 10.0):
                raise ValueError(f"Superquadric exponent out of stable range [0.05, 10.0]: {e}")


@dataclass
class ReceiverData:
    receiver_type: ReceiverType = ReceiverType.CYCLORAMA
    ground_y: float = 0.0
    # Cyclorama cove fillet parameters
    cove_center_yz: List[float] = field(default_factory=lambda: [0.40, -0.80])
    cove_radius: float = 0.40
    wall_z: float = -1.20
    visible: bool = True

    def validate(self) -> None:
        if self.cove_radius <= 0.0:
            raise ValueError(f"Cyclorama cove radius must be strictly positive: {self.cove_radius}")


@dataclass
class AreaLightData:
    id: str = "key_light_1"
    name: str = "Key Softbox"
    position: List[float] = field(default_factory=lambda: [1.2, 1.8, 1.5])
    rotation_deg: List[float] = field(default_factory=lambda: [-35.0, 30.0, 0.0])  # Aim towards origin
    width: float = 0.60   # Emitter width in meters
    height: float = 0.60  # Emitter height in meters
    intensity: float = 1.0
    color_rgb: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    temperature_kelvin: float = 5600.0  # Daylight standard
    energy_convention: EnergyConvention = EnergyConvention.FIXED_RADIANCE
    enabled: bool = True

    def validate(self) -> None:
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError(f"Area light dimensions must be positive: {self.width}x{self.height}")
        if self.intensity < 0.0:
            raise ValueError(f"Area light intensity cannot be negative: {self.intensity}")
        for c in self.color_rgb:
            if not (0.0 <= c <= 2.0):
                raise ValueError(f"Area light color channel out of expected range [0, 2]: {self.color_rgb}")


@dataclass
class RenderSettingsData:
    quality: RenderQuality = RenderQuality.PREVIEW
    preview_samples: int = 4
    final_samples: int = 32
    enable_cast_shadows: bool = True
    enable_contact_grounding: bool = True
    enable_hbao: bool = True
    ambient_fill: float = 0.15
    exposure: float = 1.0

    def validate(self) -> None:
        if self.preview_samples < 1 or self.final_samples < 1:
            raise ValueError("Sample counts must be >= 1")
        if not (0.0 <= self.ambient_fill <= 1.0):
            raise ValueError("Ambient fill must be in [0, 1]")


@dataclass
class StudioScene:
    metadata: SceneMetadata = field(default_factory=SceneMetadata)
    camera: CameraData = field(default_factory=CameraData)
    subject: SubjectProxyData = field(default_factory=SubjectProxyData)
    receiver: ReceiverData = field(default_factory=ReceiverData)
    lights: List[AreaLightData] = field(default_factory=lambda: [AreaLightData()])
    render_settings: RenderSettingsData = field(default_factory=RenderSettingsData)

    def validate(self) -> None:
        """Validates all scene parameters against physical invariants."""
        self.camera.validate()
        self.subject.validate()
        self.receiver.validate()
        if not self.lights:
            raise ValueError("StudioScene must contain at least one light.")
        for light in self.lights:
            light.validate()
        self.render_settings.validate()
        validate_finite_floats(asdict(self))

    def to_dict(self) -> Dict[str, Any]:
        """Serializes scene to a JSON-compatible dictionary."""
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StudioScene:
        """Deserializes scene from dictionary with type safety."""
        d = copy.deepcopy(data)
        meta = SceneMetadata(**d.get("metadata", {}))
        cam = CameraData(**d.get("camera", {}))
        
        subj_raw = d.get("subject", {})
        if "proxy_type" in subj_raw:
            subj_raw["proxy_type"] = ProxyType(subj_raw["proxy_type"])
        subj = SubjectProxyData(**subj_raw)
        
        rec_raw = d.get("receiver", {})
        if "receiver_type" in rec_raw:
            rec_raw["receiver_type"] = ReceiverType(rec_raw["receiver_type"])
        rec = ReceiverData(**rec_raw)
        
        lights = []
        for l_raw in d.get("lights", []):
            if "energy_convention" in l_raw:
                l_raw["energy_convention"] = EnergyConvention(l_raw["energy_convention"])
            lights.append(AreaLightData(**l_raw))
            
        rnd_raw = d.get("render_settings", {})
        if "quality" in rnd_raw:
            rnd_raw["quality"] = RenderQuality(rnd_raw["quality"])
        rnd = RenderSettingsData(**rnd_raw)
        
        scene = cls(metadata=meta, camera=cam, subject=subj, receiver=rec, lights=lights, render_settings=rnd)
        scene.validate()
        return scene

    def to_json(self, indent: int = 2) -> str:
        """Serializes scene to a formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> StudioScene:
        """Loads scene from JSON string."""
        return cls.from_dict(json.loads(json_str))


class SceneStateManager:
    """
    Authoritative state manager maintaining undo/redo snapshot stack.
    Guarantees that artist actions mutate scene state deterministically.
    """
    def __init__(self, initial_scene: Optional[StudioScene] = None, max_history: int = 50):
        self._current_scene: StudioScene = initial_scene or StudioScene()
        self._current_scene.validate()
        self._undo_stack: List[str] = [self._current_scene.to_json()]
        self._redo_stack: List[str] = []
        self._max_history: int = max_history

    @property
    def current_scene(self) -> StudioScene:
        return self._current_scene

    def push_state(self, new_scene: StudioScene) -> None:
        """Pushes a new verified scene snapshot onto the undo history."""
        new_scene.validate()
        snapshot = new_scene.to_json()
        if snapshot == self._undo_stack[-1]:
            return  # No state change
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._current_scene = copy.deepcopy(new_scene)

    def undo(self) -> bool:
        """Reverts to the previous scene snapshot."""
        if len(self._undo_stack) <= 1:
            return False
        current_snapshot = self._undo_stack.pop()
        self._redo_stack.append(current_snapshot)
        prev_snapshot = self._undo_stack[-1]
        self._current_scene = StudioScene.from_json(prev_snapshot)
        return True

    def redo(self) -> bool:
        """Re-applies the next undone scene snapshot."""
        if not self._redo_stack:
            return False
        next_snapshot = self._redo_stack.pop()
        self._undo_stack.append(next_snapshot)
        self._current_scene = StudioScene.from_json(next_snapshot)
        return True

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 1

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0
