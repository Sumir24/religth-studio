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

from studio3a.material import MaterialData
from studio3a.environment import EnvironmentData


class ProxyType(str, Enum):
    OBB = "OBB"
    SUPERQUADRIC = "SUPERQUADRIC"
    MESH = "MESH"
    SPHERE = "SPHERE"


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
    version: str = "3.2.0"
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
    material: MaterialData = field(default_factory=MaterialData)

    def validate(self) -> None:
        self.material.validate()
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
    material: MaterialData = field(
        default_factory=lambda: MaterialData(
            id="mat_receiver",
            name="Cyclorama Matte",
            roughness=0.90,
            metallic=0.0,
            specular_intensity=0.20
        )
    )

    def validate(self) -> None:
        self.material.validate()
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
    cast_shadows: bool = True

    @property
    def light_id(self) -> str:
        return self.id

    @light_id.setter
    def light_id(self, val: str) -> None:
        self.id = val

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Area light ID cannot be empty.")
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
    enable_specular: bool = True
    specular_only: bool = False

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
    active_light_id: Optional[str] = None
    materials: List[MaterialData] = field(default_factory=lambda: [MaterialData()])
    active_material_id: Optional[str] = None
    environment: EnvironmentData = field(default_factory=EnvironmentData)

    def __post_init__(self) -> None:
        if self.active_light_id is None and self.lights:
            self.active_light_id = self.lights[0].id
        if self.active_material_id is None and self.materials:
            self.active_material_id = self.materials[0].id

    def validate(self) -> None:
        """Validates all scene parameters against physical invariants."""
        self.camera.validate()
        self.subject.validate()
        self.receiver.validate()
        if not self.lights and (self.environment is None or not self.environment.enabled):
            raise ValueError("StudioScene must contain at least one light or an active environment.")
        if len(self.lights) > 8:
            raise ValueError(f"StudioScene supports at most 8 lights on GPU pipeline (found {len(self.lights)}).")
        
        # Validate unique light IDs
        light_ids = set()
        for light in self.lights:
            light.validate()
            if light.id in light_ids:
                raise ValueError(f"Duplicate light ID detected: '{light.id}'")
            light_ids.add(light.id)

        # Validate active light selection
        if self.lights:
            if self.active_light_id is None or self.active_light_id not in light_ids:
                self.active_light_id = self.lights[0].id
        else:
            self.active_light_id = None

        # Validate materials
        if not self.materials:
            raise ValueError("StudioScene must contain at least one material.")
        mat_ids = set()
        for mat in self.materials:
            mat.validate()
            if mat.id in mat_ids:
                raise ValueError(f"Duplicate material ID detected: '{mat.id}'")
            mat_ids.add(mat.id)
        if self.active_material_id is None or self.active_material_id not in mat_ids:
            self.active_material_id = self.materials[0].id

        self.environment.validate()
        self.render_settings.validate()
        validate_finite_floats(asdict(self))

    def get_light(self, light_id: str) -> Optional[AreaLightData]:
        for l in self.lights:
            if l.id == light_id:
                return l
        return None

    def get_active_light(self) -> AreaLightData:
        if self.active_light_id:
            l = self.get_light(self.active_light_id)
            if l is not None:
                return l
        self.active_light_id = self.lights[0].id
        return self.lights[0]

    def select_light(self, light_id: str) -> bool:
        if any(l.id == light_id for l in self.lights):
            self.active_light_id = light_id
            return True
        return False

    def add_light(self, light: Optional[AreaLightData] = None) -> AreaLightData:
        if len(self.lights) >= 8:
            raise ValueError("Maximum number of lights (8) reached.")
        if light is None:
            idx = len(self.lights) + 1
            light = AreaLightData(
                id=f"light_{idx}_{int(time.time()*1000)%10000}",
                name=f"Studio Light {idx}",
                position=[-1.2, 1.8, 1.5] if idx % 2 == 0 else [1.2, 1.8, 1.5],
                rotation_deg=[-35.0, -30.0 if idx % 2 == 0 else 30.0, 0.0],
                width=0.60,
                height=0.60,
                intensity=1.0,
                color_rgb=[1.0, 1.0, 1.0],
                temperature_kelvin=5600.0,
                energy_convention=EnergyConvention.FIXED_RADIANCE,
                enabled=True,
                cast_shadows=True
            )
        base_id = light.id
        counter = 1
        while any(l.id == light.id for l in self.lights):
            light.id = f"{base_id}_{counter}"
            counter += 1
        self.lights.append(light)
        self.active_light_id = light.id
        return light

    def remove_light(self, light_id: str) -> bool:
        if len(self.lights) <= 1:
            raise ValueError("Cannot remove the last remaining light from the scene.")
        for i, l in enumerate(self.lights):
            if l.id == light_id:
                self.lights.pop(i)
                if self.active_light_id == light_id:
                    self.active_light_id = self.lights[min(i, len(self.lights) - 1)].id
                return True
        return False

    def duplicate_light(self, light_id: str) -> AreaLightData:
        src = self.get_light(light_id)
        if src is None:
            raise ValueError(f"Light '{light_id}' not found.")
        if len(self.lights) >= 8:
            raise ValueError("Maximum number of lights (8) reached.")
        new_light = copy.deepcopy(src)
        idx = len(self.lights) + 1
        new_light.id = f"{src.id}_copy_{int(time.time()*1000)%10000}"
        new_light.name = f"{src.name} (Copy)"
        # Slight physical spatial offset
        new_light.position = [src.position[0] + 0.25, src.position[1], src.position[2]]
        self.lights.append(new_light)
        self.active_light_id = new_light.id
        return new_light

    def toggle_light(self, light_id: str, enabled: Optional[bool] = None) -> bool:
        l = self.get_light(light_id)
        if l is None:
            raise ValueError(f"Light '{light_id}' not found.")
        if enabled is not None:
            l.enabled = enabled
        else:
            l.enabled = not l.enabled
        return l.enabled

    def toggle_light_shadows(self, light_id: str, cast_shadows: Optional[bool] = None) -> bool:
        l = self.get_light(light_id)
        if l is None:
            raise ValueError(f"Light '{light_id}' not found.")
        if cast_shadows is not None:
            l.cast_shadows = cast_shadows
        else:
            l.cast_shadows = not l.cast_shadows
        return l.cast_shadows

    def reorder_lights(self, order_ids: List[str]) -> None:
        if set(order_ids) != set(l.id for l in self.lights):
            raise ValueError("Order IDs must match existing scene light IDs exactly.")
        lookup = {l.id: l for l in self.lights}
        self.lights = [lookup[lid] for lid in order_ids]

    def get_material(self, mat_id: str) -> Optional[MaterialData]:
        for m in self.materials:
            if m.id == mat_id:
                return m
        return None

    def get_active_material(self) -> MaterialData:
        if self.active_material_id:
            m = self.get_material(self.active_material_id)
            if m is not None:
                return m
        self.active_material_id = self.materials[0].id
        return self.materials[0]

    def select_material(self, mat_id: str) -> bool:
        if any(m.id == mat_id for m in self.materials):
            self.active_material_id = mat_id
            return True
        return False

    def add_material(self, mat: Optional[MaterialData] = None) -> MaterialData:
        if mat is None:
            idx = len(self.materials) + 1
            mat = MaterialData(
                id=f"mat_{idx}_{int(time.time()*1000)%10000}",
                name=f"Studio Material {idx}"
            )
        base_id = mat.id
        counter = 1
        while any(m.id == mat.id for m in self.materials):
            mat.id = f"{base_id}_{counter}"
            counter += 1
        self.materials.append(mat)
        self.active_material_id = mat.id
        return mat

    def assign_material_to_subject(self, mat_id: str) -> bool:
        m = self.get_material(mat_id)
        if m is None:
            raise ValueError(f"Material '{mat_id}' not found in scene.")
        self.subject.material = copy.deepcopy(m)
        self.active_material_id = mat_id
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Serializes scene to a JSON-compatible dictionary."""
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StudioScene:
        """Deserializes scene from dictionary with backward compatibility and type safety."""
        d = copy.deepcopy(data)
        meta_raw = d.get("metadata", {})
        # Schema migration check: upgrade older scenes to 3.2.0
        meta = SceneMetadata(**meta_raw)
        meta.version = "3.2.0"
        
        cam = CameraData(**d.get("camera", {}))
        
        subj_raw = d.get("subject", {})
        if "proxy_type" in subj_raw:
            subj_raw["proxy_type"] = ProxyType(subj_raw["proxy_type"])
        if "material" in subj_raw:
            subj_raw["material"] = MaterialData.from_dict(subj_raw["material"])
        else:
            subj_raw["material"] = MaterialData()
        subj = SubjectProxyData(**subj_raw)
        
        rec_raw = d.get("receiver", {})
        if "receiver_type" in rec_raw:
            rec_raw["receiver_type"] = ReceiverType(rec_raw["receiver_type"])
        if "material" in rec_raw:
            rec_raw["material"] = MaterialData.from_dict(rec_raw["material"])
        else:
            rec_raw["material"] = MaterialData(
                id="mat_receiver",
                name="Cyclorama Matte",
                roughness=0.90,
                metallic=0.0,
                specular_intensity=0.20
            )
        rec = ReceiverData(**rec_raw)
        
        lights = []
        for idx, l_raw in enumerate(d.get("lights", [])):
            if "energy_convention" in l_raw:
                l_raw["energy_convention"] = EnergyConvention(l_raw["energy_convention"])
            # Backward-compatible migrations:
            if "cast_shadows" not in l_raw:
                l_raw["cast_shadows"] = True
            if "id" not in l_raw:
                l_raw["id"] = f"light_{idx+1}"
            if "name" not in l_raw:
                l_raw["name"] = f"Studio Light {idx+1}"
            lights.append(AreaLightData(**l_raw))
            
        rnd_raw = d.get("render_settings", {})
        if "quality" in rnd_raw:
            rnd_raw["quality"] = RenderQuality(rnd_raw["quality"])
        rnd = RenderSettingsData(**rnd_raw)
        
        active_lid = d.get("active_light_id")
        if not active_lid and lights:
            active_lid = lights[0].id

        materials = []
        for m_raw in d.get("materials", []):
            materials.append(MaterialData.from_dict(m_raw))
        if not materials:
            materials = [copy.deepcopy(subj.material)]

        active_mid = d.get("active_material_id")
        if not active_mid and materials:
            active_mid = materials[0].id

        env_raw = d.get("environment", {})
        env = EnvironmentData.from_dict(env_raw) if env_raw else EnvironmentData()
        
        scene = cls(
            metadata=meta,
            camera=cam,
            subject=subj,
            receiver=rec,
            lights=lights,
            render_settings=rnd,
            active_light_id=active_lid,
            materials=materials,
            active_material_id=active_mid,
            environment=env
        )
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
