"""
RELIGHT STUDIO — RS-PRODUCT-1.1
================================
Studio Application Controller
Authoritative application controller coordinating scene state, projects, selection,
undo/redo history, 3D stage projection, 3D transform gizmos, and asynchronous rendering.
"""

from __future__ import annotations

import os
import copy
import time
import uuid
import math
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
import cv2

from studio3a.scene import (
    StudioScene, CameraData, SubjectProxyData, ReceiverData,
    AreaLightData, RenderSettingsData, ProxyType, ReceiverType,
    EnergyConvention, RenderQuality, SceneStateManager
)
from studio3a.material import MaterialData
from studio3a.lighting import RectangularAreaLight
from studio3a.environment import EnvironmentData
from studio3a.renderer import RenderBackend
from studio3a.camera import Camera3D, fov_to_focal_length_mm, focal_length_to_fov_deg
from studio3a.geometry import compute_proxy_geometry_meta, snap_proxy_to_ground

from relight_studio.project import RelightProject
from relight_studio.orchestrator import RenderingOrchestrator


class StudioAppController:
    """
    Central authoritative controller for the Relight Studio application.
    Enforces the product architecture:
      Application UI -> StudioAppController -> Authoritative Scene State ->
      RenderingOrchestrator -> Rendering Engine -> Photographic Viewport
    """
    def __init__(self, sample_image_path: Optional[str] = None, use_metal: bool = True):
        self.orchestrator = RenderingOrchestrator(use_metal=use_metal)
        
        # 3D Stage Viewport Orbit Camera State
        self.stage_orbit_yaw_deg: float = 35.0
        self.stage_orbit_pitch_deg: float = 25.0
        self.stage_orbit_dist: float = 3.8
        self.stage_pan_offset: List[float] = [0.0, 0.0]

        # Active selection (e.g. 'light_01', 'subject', 'camera', 'receiver', 'environment')
        self.selected_object_id: str = "light_01"

        # Interaction state for dynamic preview quality
        self.is_interacting: bool = False

        # Initialize default project
        img_path = sample_image_path or "demo_output/nike_sample.jpg"
        if not os.path.exists(img_path):
            img_path = "benchmarks/reference_ibl/diagnostic_boards/synthetic_studio_env_preview.png"

        self.project: Optional[RelightProject] = None
        self.state_manager: Optional[SceneStateManager] = None

        if os.path.exists(img_path):
            self.new_project(name="Nike Footwear Commercial", image_path=img_path)
        else:
            # Create headless fallback scene
            scene = StudioScene()
            self.state_manager = SceneStateManager(scene)
            self.selected_object_id = scene.lights[0].id if scene.lights else "camera"

    # -----------------------------------------------------------------------
    # 1. PROJECT LIFECYCLE
    # -----------------------------------------------------------------------

    def new_project(self, name: str, image_path: str) -> None:
        """Creates a new project from a source photograph."""
        scene = StudioScene()
        # Default studio setup: Key light + Rim light
        scene.lights = [
            AreaLightData(
                id="light_01",
                name="Key Softbox",
                position=[1.2, 1.8, 1.5],
                rotation_deg=[-35.0, 30.0, 0.0],
                width=0.6,
                height=0.6,
                intensity=1.2,
                temperature_kelvin=5600.0,
                energy_convention=EnergyConvention.FIXED_RADIANCE,
                cast_shadows=True,
                enabled=True
            ),
            AreaLightData(
                id="light_02",
                name="Rim Strip",
                position=[-1.5, 1.2, 0.8],
                rotation_deg=[-20.0, -50.0, 0.0],
                width=0.3,
                height=1.0,
                intensity=0.8,
                temperature_kelvin=6500.0,
                energy_convention=EnergyConvention.FIXED_RADIANCE,
                cast_shadows=True,
                enabled=True
            )
        ]
        scene.active_light_id = "light_01"
        scene.subject.material = MaterialData.fabric()
        scene.receiver.receiver_type = ReceiverType.CYCLORAMA

        # Load depth/normal if companion files exist
        base_dir = os.path.dirname(image_path)
        stem = os.path.splitext(os.path.basename(image_path))[0]
        depth_guess = os.path.join("demo_output", "nike_test", "depth.png")
        normals_guess = os.path.join("demo_output", "nike_test", "normals.png")

        self.project = RelightProject(name=name, image_path=image_path, scene=scene)
        if os.path.exists(depth_guess) and os.path.exists(normals_guess):
            self.project.load_image_assets(image_path, depth_guess, normals_guess)

        self.state_manager = SceneStateManager(self.project.scene)
        self.selected_object_id = "light_01"
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=False)

    def save_project(self, bundle_path: str) -> str:
        """Saves current project state to a .relight bundle."""
        if not self.project:
            raise ValueError("No active project to save.")
        self.project.scene = self.state_manager.current_scene
        return self.project.save(bundle_path)

    def open_project(self, bundle_path: str) -> None:
        """Opens an existing .relight project bundle."""
        self.project = RelightProject.load(bundle_path)
        self.state_manager = SceneStateManager(self.project.scene)
        self.selected_object_id = self.project.scene.lights[0].id if self.project.scene.lights else "camera"
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=False)

    def import_photograph(self, image_path: str) -> None:
        """Imports and replaces the active photograph in the current project."""
        if not self.project:
            self.new_project(name="Untitled Project", image_path=image_path)
            return

        self.project.load_image_assets(image_path)
        scene = self.state_manager.current_scene
        scene.camera.width = self.project.img_orig_srgb.shape[1]
        scene.camera.height = self.project.img_orig_srgb.shape[0]
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=False)

    # -----------------------------------------------------------------------
    # 2. SCENE MUTATION & ARTIST ACTIONS
    # -----------------------------------------------------------------------

    @property
    def current_scene(self) -> StudioScene:
        return self.state_manager.current_scene

    def select_object(self, object_id: str) -> None:
        """Selects an object in the scene hierarchy and 3D stage."""
        self.selected_object_id = object_id
        scene = self.current_scene
        if object_id in [l.id for l in scene.lights]:
            scene.active_light_id = object_id

    def add_light(self) -> str:
        """Adds a new studio light and selects it."""
        scene = self.current_scene
        new_idx = len(scene.lights) + 1
        new_id = f"light_{new_idx:02d}"
        
        # Position with pleasant studio offset
        angle = math.radians(45.0 * len(scene.lights))
        pos_x = 1.6 * math.cos(angle)
        pos_z = 1.6 * math.sin(angle)
        
        new_light = AreaLightData(
            id=new_id,
            name=f"Studio Light {new_idx:02d}",
            position=[round(pos_x, 2), 1.8, round(pos_z, 2)],
            rotation_deg=[-30.0, round(math.degrees(angle) + 180.0, 1), 0.0],
            width=0.6,
            height=0.6,
            intensity=1.0,
            temperature_kelvin=5500.0,
            energy_convention=EnergyConvention.FIXED_RADIANCE,
            cast_shadows=True,
            enabled=True
        )
        scene.add_light(new_light)
        self.selected_object_id = new_id
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)
        return new_id

    def duplicate_light(self, light_id: Optional[str] = None) -> str:
        """Duplicates an existing light."""
        target_id = light_id or self.selected_object_id
        scene = self.current_scene
        new_light = scene.duplicate_light(target_id)
        if new_light:
            self.selected_object_id = new_light.id
            self.state_manager.push_state(scene)
            self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)
            return new_light.id
        return target_id

    def delete_light(self, light_id: Optional[str] = None) -> None:
        """Removes a light from the scene."""
        target_id = light_id or self.selected_object_id
        scene = self.current_scene
        scene.remove_light(target_id)
        if scene.lights:
            self.selected_object_id = scene.lights[0].id
        else:
            self.selected_object_id = "camera"
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def toggle_light_enabled(self, light_id: Optional[str] = None) -> bool:
        """Toggles light emission on/off."""
        target_id = light_id or self.selected_object_id
        scene = self.current_scene
        light = scene.get_light(target_id)
        if light:
            light.enabled = not light.enabled
            self.state_manager.push_state(scene)
            self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)
            return light.enabled
        return False

    def toggle_light_shadows(self, light_id: Optional[str] = None) -> bool:
        """Toggles shadow ray-tracing for a light."""
        target_id = light_id or self.selected_object_id
        scene = self.current_scene
        light = scene.get_light(target_id)
        if light:
            light.cast_shadows = not light.cast_shadows
            self.state_manager.push_state(scene)
            self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)
            return light.cast_shadows
        return False

    def rename_light(self, light_id: str, new_name: str) -> None:
        """Renames a light in the scene."""
        scene = self.current_scene
        light = scene.get_light(light_id)
        if light:
            light.name = new_name.strip()
            self.state_manager.push_state(scene)

    def update_light_transform(
        self,
        light_id: str,
        pos: Optional[List[float]] = None,
        rot_deg: Optional[List[float]] = None,
        width: Optional[float] = None,
        height: Optional[float] = None
    ) -> None:
        """Updates light position, orientation, and dimensions."""
        scene = self.current_scene
        light = scene.get_light(light_id)
        if not light:
            return

        if pos is not None:
            light.position = [float(p) for p in pos]
        if rot_deg is not None:
            light.rotation_deg = [float(r) for r in rot_deg]
        if width is not None:
            light.width = max(0.05, float(width))
        if height is not None:
            light.height = max(0.05, float(height))

        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def update_light_properties(
        self,
        light_id: str,
        intensity: Optional[float] = None,
        temperature_kelvin: Optional[float] = None,
        energy_convention: Optional[str] = None,
        enabled: Optional[bool] = None,
        cast_shadows: Optional[bool] = None
    ) -> None:
        """Updates light photometric and radiometric properties."""
        scene = self.current_scene
        light = scene.get_light(light_id)
        if not light:
            return

        if intensity is not None:
            light.intensity = max(0.0, float(intensity))
        if temperature_kelvin is not None:
            light.temperature_kelvin = max(1000.0, min(12000.0, float(temperature_kelvin)))
        if energy_convention is not None:
            light.energy_convention = EnergyConvention(energy_convention)
        if enabled is not None:
            light.enabled = bool(enabled)
        if cast_shadows is not None:
            light.cast_shadows = bool(cast_shadows)

        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    # -----------------------------------------------------------------------
    # LIGHTING PRESETS
    # -----------------------------------------------------------------------

    def apply_lighting_preset(self, preset_name: str, light_id: Optional[str] = None) -> str:
        """
        Applies a verified studio lighting preset backed by real 3D coordinates,
        orientations, dimensions, intensities, and Kelvin color temperatures.
        """
        target_id = light_id or self.selected_object_id
        scene = self.current_scene
        light = scene.get_light(target_id)
        if not light:
            # Create a light if none selected
            new_id = self.add_light()
            light = scene.get_light(new_id)

        p = preset_name.lower().replace("-", "_").replace(" ", "_")
        if p == "key_softbox":
            light.name = "Key Softbox"
            light.position = [1.2, 1.8, 1.5]
            light.rotation_deg = [-35.0, 30.0, 0.0]
            light.width = 0.8
            light.height = 0.8
            light.intensity = 1.8
            light.temperature_kelvin = 5600.0
        elif p == "fill_softbox":
            light.name = "Fill Softbox"
            light.position = [-1.4, 1.4, 1.6]
            light.rotation_deg = [-25.0, -30.0, 0.0]
            light.width = 1.0
            light.height = 1.0
            light.intensity = 0.8
            light.temperature_kelvin = 5200.0
        elif p == "rim_strip":
            light.name = "Rim Strip"
            light.position = [-1.6, 1.5, -0.6]
            light.rotation_deg = [-15.0, -120.0, 0.0]
            light.width = 0.3
            light.height = 1.4
            light.intensity = 2.2
            light.temperature_kelvin = 6500.0
        elif p == "top_light":
            light.name = "Top Softbox"
            light.position = [0.0, 2.8, 0.0]
            light.rotation_deg = [-90.0, 0.0, 0.0]
            light.width = 1.2
            light.height = 1.2
            light.intensity = 1.8
            light.temperature_kelvin = 5800.0
        elif p == "side_light":
            light.name = "Side Rake"
            light.position = [2.2, 1.0, 0.2]
            light.rotation_deg = [0.0, 85.0, 0.0]
            light.width = 0.6
            light.height = 1.2
            light.intensity = 1.4
            light.temperature_kelvin = 4500.0
        else:
            raise ValueError(f"Unknown preset '{preset_name}'")

        light.enabled = True
        light.cast_shadows = True
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)
        return light.id

    # -----------------------------------------------------------------------
    # 3D GIZMO PROJECTION & INTERACTION
    # -----------------------------------------------------------------------

    def _get_stage_projector(self, width: int = 640, height: int = 480):
        """Helper computing stage camera basis and perspective projection function."""
        yaw = math.radians(self.stage_orbit_yaw_deg)
        pitch = math.radians(self.stage_orbit_pitch_deg)
        r = self.stage_orbit_dist

        cam_tgt = np.array([self.stage_pan_offset[0], 0.35, self.stage_pan_offset[1]], dtype=np.float32)
        cam_pos = cam_tgt + np.array([
            r * math.cos(pitch) * math.sin(yaw),
            r * math.sin(pitch),
            r * math.cos(pitch) * math.cos(yaw)
        ], dtype=np.float32)

        fwd = cam_tgt - cam_pos
        fwd /= np.linalg.norm(fwd)
        up_tmp = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        right = np.cross(fwd, up_tmp)
        if np.linalg.norm(right) < 1e-4:
            right = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        else:
            right /= np.linalg.norm(right)
        cam_up = np.cross(right, fwd)

        fov = math.radians(45.0)
        f_len = (height / 2.0) / math.tan(fov / 2.0)

        def to_screen(pt3d: np.ndarray) -> Tuple[Tuple[int, int], bool]:
            rel = pt3d - cam_pos
            z_cam = float(np.dot(rel, fwd))
            if z_cam <= 0.1:
                return (0, 0), False
            x_cam = float(np.dot(rel, right))
            y_cam = float(np.dot(rel, cam_up))
            sx = int(width / 2.0 + (x_cam / z_cam) * f_len)
            sy = int(height / 2.0 - (y_cam / z_cam) * f_len)
            return (sx, sy), (z_cam > 0.1)

        return cam_pos, to_screen, right, cam_up, fwd, f_len

    def get_stage_projection_meta(
        self,
        width: int = 640,
        height: int = 480,
        canvas_w: Optional[int] = None,
        canvas_h: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Returns full screen coordinates for 3D picking, gizmo handles, and object hit-testing.
        """
        w = canvas_w if canvas_w is not None else width
        h = canvas_h if canvas_h is not None else height
        cam_pos, to_screen, right, cam_up, fwd, f_len = self._get_stage_projector(w, h)
        scene = self.current_scene

        meta = {
            "selected_id": self.selected_object_id,
            "lights": [],
            "gizmo": None,
            "subject": None,
            "camera": None
        }

        # Project lights
        active_light = None
        for l in scene.lights:
            p_ctr, v_ctr = to_screen(np.array(l.position, dtype=np.float32))
            l_obj = RectangularAreaLight(
                position=l.position,
                rotation_euler=l.rotation_deg,
                width=l.width,
                height=l.height
            )
            hw = l.width / 2.0
            hh = l.height / 2.0
            l_pos = np.array(l.position, dtype=np.float32)
            corners_3d = [
                l_pos + (-hw) * l_obj.u_tangent + (-hh) * l_obj.v_bitangent,
                l_pos + ( hw) * l_obj.u_tangent + (-hh) * l_obj.v_bitangent,
                l_pos + ( hw) * l_obj.u_tangent + ( hh) * l_obj.v_bitangent,
                l_pos + (-hw) * l_obj.u_tangent + ( hh) * l_obj.v_bitangent
            ]
            corners_screen = [to_screen(pt)[0] for pt in corners_3d]
            light_entry = {
                "id": l.id,
                "name": l.name,
                "center": list(p_ctr),
                "visible": v_ctr,
                "corners": corners_screen
            }
            meta["lights"].append(light_entry)
            if l.id == self.selected_object_id:
                active_light = l

        # Project 3D Gizmo for active light or selected subject
        if active_light:
            g_pos = np.array(active_light.position, dtype=np.float32)
            p_ctr, v_ctr = to_screen(g_pos)
            if v_ctr:
                axis_len = 0.50
                p_x, _ = to_screen(g_pos + np.array([axis_len, 0.0, 0.0]))
                p_y, _ = to_screen(g_pos + np.array([0.0, axis_len, 0.0]))
                p_z, _ = to_screen(g_pos + np.array([0.0, 0.0, axis_len]))
                
                # Pitch ring handle (in YZ plane)
                p_pitch, _ = to_screen(g_pos + np.array([0.0, axis_len * 0.7, axis_len * 0.7]))
                # Yaw ring handle (in XZ plane)
                p_yaw, _ = to_screen(g_pos + np.array([axis_len * 0.7, 0.0, axis_len * 0.7]))
                # Roll ring handle (in XY plane)
                p_roll, _ = to_screen(g_pos + np.array([axis_len * 0.7, axis_len * 0.7, 0.0]))

                meta["gizmo"] = {
                    "target_id": active_light.id,
                    "light_id": active_light.id,
                    "center": list(p_ctr),
                    "axis_x": list(p_x),
                    "axis_y": list(p_y),
                    "axis_z": list(p_z),
                    "rot_pitch": list(p_pitch),
                    "rot_yaw": list(p_yaw),
                    "rot_roll": list(p_roll)
                }

        elif self.selected_object_id == "subject":
            g_pos = np.array(scene.subject.position, dtype=np.float32)
            p_ctr, v_ctr = to_screen(g_pos)
            if v_ctr:
                axis_len = 0.50
                p_x, _ = to_screen(g_pos + np.array([axis_len, 0.0, 0.0]))
                p_y, _ = to_screen(g_pos + np.array([0.0, axis_len, 0.0]))
                p_z, _ = to_screen(g_pos + np.array([0.0, 0.0, axis_len]))
                
                # Pitch, Yaw, Roll handles
                p_pitch, _ = to_screen(g_pos + np.array([0.0, axis_len * 0.7, axis_len * 0.7]))
                p_yaw, _ = to_screen(g_pos + np.array([axis_len * 0.7, 0.0, axis_len * 0.7]))
                p_roll, _ = to_screen(g_pos + np.array([axis_len * 0.7, axis_len * 0.7, 0.0]))
                p_scale, _ = to_screen(g_pos + np.array([axis_len * 0.5, axis_len * 0.5, axis_len * 0.5]))

                pmeta = compute_proxy_geometry_meta(
                    proxy_type=scene.subject.proxy_type.value,
                    position=scene.subject.position,
                    dimensions=scene.subject.dimensions,
                    rotation_euler=scene.subject.rotation_deg,
                    scale=scene.subject.scale,
                    ground_y=scene.receiver.ground_y,
                    sq_exponents=scene.subject.sq_exponents
                )
                p_gnd, _ = to_screen(np.array(pmeta["ground_marker_world"], dtype=np.float32))

                meta["gizmo"] = {
                    "target_id": "subject",
                    "light_id": None,
                    "center": list(p_ctr),
                    "axis_x": list(p_x),
                    "axis_y": list(p_y),
                    "axis_z": list(p_z),
                    "rot_pitch": list(p_pitch),
                    "rot_yaw": list(p_yaw),
                    "rot_roll": list(p_roll),
                    "scale_uniform": list(p_scale),
                    "ground_contact": list(p_gnd),
                    "ground_gap_m": pmeta["ground_gap_m"],
                    "contact_state": pmeta["contact_state"]
                }

        # Project Subject
        subj_pos = np.array(scene.subject.position, dtype=np.float32)
        p_subj, v_subj = to_screen(subj_pos)
        meta["subject"] = {
            "center": list(p_subj),
            "visible": v_subj
        }

        # Project Camera
        p_cam, v_cam = to_screen(np.array(scene.camera.pos, dtype=np.float32))
        meta["camera"] = {
            "center": list(p_cam),
            "visible": v_cam
        }

        return meta

    def project_drag_to_3d(
        self,
        axis: str,
        delta_screen_x: float,
        delta_screen_y: float,
        light_id: Optional[str] = None,
        canvas_w: int = 640,
        canvas_h: int = 480
    ) -> None:
        """
        Projects screen pixel dragging along a 3D gizmo axis into true world-space displacement.
        Supports both area lights and subject proxy geometry with near-parallel singularity protection.
        """
        target_id = light_id or self.selected_object_id
        scene = self.current_scene

        # --- SUBJECT PROXY EDITING ---
        if target_id == "subject":
            subj = scene.subject
            cam_pos, to_screen, right, cam_up, fwd, f_len = self._get_stage_projector(canvas_w, canvas_h)
            p0 = np.array(subj.position, dtype=np.float32)
            s0, _ = to_screen(p0)

            ax = axis.upper()
            if ax in ("X", "Y", "Z"):
                dir_map = {
                    "X": np.array([1.0, 0.0, 0.0], dtype=np.float32),
                    "Y": np.array([0.0, 1.0, 0.0], dtype=np.float32),
                    "Z": np.array([0.0, 0.0, 1.0], dtype=np.float32)
                }
                v_dir = dir_map[ax]
                p1 = p0 + v_dir
                s1, _ = to_screen(p1)

                sv = np.array([s1[0] - s0[0], s1[1] - s0[1]], dtype=np.float32)
                length = float(np.linalg.norm(sv))
                if length >= 4.0:
                    u_dir = sv / length
                    mouse_disp = np.array([delta_screen_x, delta_screen_y], dtype=np.float32)
                    dist_m = float(np.dot(mouse_disp, u_dir) / length)
                else:
                    # Near-parallel singularity protection: fall back to vertical mouse drag
                    dist_m = float(-delta_screen_y * 0.005)

                if ax == "X":
                    subj.position[0] = round(subj.position[0] + dist_m, 3)
                elif ax == "Y":
                    subj.position[1] = round(subj.position[1] + dist_m, 3)
                elif ax == "Z":
                    subj.position[2] = round(subj.position[2] + dist_m, 3)

            elif ax == "PITCH":
                delta_pitch = -delta_screen_y * 0.5
                subj.rotation_deg[0] = max(-180.0, min(180.0, round(subj.rotation_deg[0] + delta_pitch, 1)))

            elif ax == "YAW":
                delta_yaw = delta_screen_x * 0.5
                subj.rotation_deg[1] = round((subj.rotation_deg[1] + delta_yaw) % 360.0, 1)
                if subj.rotation_deg[1] > 180.0:
                    subj.rotation_deg[1] -= 360.0

            elif ax == "ROLL":
                delta_roll = delta_screen_x * 0.5
                subj.rotation_deg[2] = round((subj.rotation_deg[2] + delta_roll) % 360.0, 1)
                if subj.rotation_deg[2] > 180.0:
                    subj.rotation_deg[2] -= 360.0

            elif ax in ("SCALE", "UNIFORM_SCALE"):
                delta_scale = (delta_screen_x - delta_screen_y) * 0.005
                factor = max(0.1, 1.0 + delta_scale)
                subj.dimensions = [max(0.01, round(d * factor, 3)) for d in subj.dimensions]

            elif ax == "WIDTH":
                delta_w = delta_screen_x * 0.005
                subj.dimensions[0] = max(0.01, round(subj.dimensions[0] + delta_w, 3))

            elif ax == "HEIGHT":
                delta_h = -delta_screen_y * 0.005
                subj.dimensions[1] = max(0.01, round(subj.dimensions[1] + delta_h, 3))

            elif ax == "DEPTH":
                delta_d = delta_screen_x * 0.005
                subj.dimensions[2] = max(0.01, round(subj.dimensions[2] + delta_d, 3))

            self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)
            return

        # --- AREA LIGHT EDITING ---
        light = scene.get_light(target_id)
        if not light:
            return

        cam_pos, to_screen, right, cam_up, fwd, f_len = self._get_stage_projector(canvas_w, canvas_h)
        p0 = np.array(light.position, dtype=np.float32)
        s0, _ = to_screen(p0)

        ax = axis.upper()
        if ax in ("X", "Y", "Z"):
            dir_map = {
                "X": np.array([1.0, 0.0, 0.0], dtype=np.float32),
                "Y": np.array([0.0, 1.0, 0.0], dtype=np.float32),
                "Z": np.array([0.0, 0.0, 1.0], dtype=np.float32)
            }
            v_dir = dir_map[ax]
            p1 = p0 + v_dir
            s1, _ = to_screen(p1)

            # Screen vector corresponding to 1 meter in 3D
            sv = np.array([s1[0] - s0[0], s1[1] - s0[1]], dtype=np.float32)
            length = float(np.linalg.norm(sv))
            if length >= 4.0:
                u_dir = sv / length
                mouse_disp = np.array([delta_screen_x, delta_screen_y], dtype=np.float32)
                dist_m = float(np.dot(mouse_disp, u_dir) / length)
            else:
                # Near-parallel singularity protection: fall back to vertical mouse drag
                dist_m = float(-delta_screen_y * 0.005)
            
            if ax == "X":
                light.position[0] = round(light.position[0] + dist_m, 3)
            elif ax == "Y":
                light.position[1] = max(0.0, round(light.position[1] + dist_m, 3))
            elif ax == "Z":
                light.position[2] = round(light.position[2] + dist_m, 3)

        elif ax == "PITCH":
            delta_pitch = -delta_screen_y * 0.5
            light.rotation_deg[0] = max(-90.0, min(90.0, round(light.rotation_deg[0] + delta_pitch, 1)))

        elif ax == "YAW":
            delta_yaw = delta_screen_x * 0.5
            light.rotation_deg[1] = round((light.rotation_deg[1] + delta_yaw) % 360.0, 1)
            if light.rotation_deg[1] > 180.0:
                light.rotation_deg[1] -= 360.0

        elif ax == "ROLL":
            delta_roll = delta_screen_x * 0.5
            light.rotation_deg[2] = round((light.rotation_deg[2] + delta_roll) % 360.0, 1)
            if light.rotation_deg[2] > 180.0:
                light.rotation_deg[2] -= 360.0

        elif ax == "WIDTH":
            delta_w = delta_screen_x * 0.01
            light.width = max(0.1, round(light.width + delta_w, 2))

        elif ax == "HEIGHT":
            delta_h = -delta_screen_y * 0.01
            light.height = max(0.1, round(light.height + delta_h, 2))

        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def focus_selected_object(self) -> None:
        """Centers the 3D studio viewport camera on the selected object."""
        scene = self.current_scene
        sel_id = self.selected_object_id
        light = scene.get_light(sel_id)
        if light:
            self.stage_pan_offset = [light.position[0], light.position[2]]
            self.stage_orbit_dist = 3.2
        elif sel_id == "subject":
            self.stage_pan_offset = [0.0, 0.0]
            self.stage_orbit_dist = 2.8
        else:
            self.stage_pan_offset = [0.0, 0.0]
            self.stage_orbit_dist = 3.8

    def reset_camera_stage(self) -> None:
        """Resets the 3D studio viewport camera to the standard 3/4 perspective."""
        self.stage_orbit_yaw_deg = 35.0
        self.stage_orbit_pitch_deg = 25.0
        self.stage_orbit_dist = 3.8
        self.stage_pan_offset = [0.0, 0.0]

    # -----------------------------------------------------------------------
    # SUBJECT, RECEIVER, MATERIAL & ENVIRONMENT CONTROLS
    # -----------------------------------------------------------------------

    def set_material_profile(self, profile_name: str) -> None:
        """Sets subject material from one of the canonical PBR profiles."""
        p_name = profile_name.lower().replace(" ", "_")
        if p_name == "fabric":
            mat = MaterialData.fabric()
        elif p_name == "marble":
            mat = MaterialData.marble()
        elif p_name == "plastic":
            mat = MaterialData.plastic()
        elif p_name in ("rough_metal", "rough metal"):
            mat = MaterialData.rough_metal()
        elif p_name in ("polished_metal", "polished metal"):
            mat = MaterialData.polished_metal()
        else:
            mat = MaterialData()

        scene = self.current_scene
        scene.subject.material = mat
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def update_material_params(
        self,
        roughness: Optional[float] = None,
        metallic: Optional[float] = None,
        specular_f0: Optional[float] = None,
        specular_intensity: Optional[float] = None,
        enable_specular: Optional[bool] = None
    ) -> None:
        """Updates microfacet BRDF material parameters."""
        scene = self.current_scene
        mat = scene.subject.material
        if roughness is not None:
            mat.roughness = max(0.04, min(1.0, float(roughness)))
        if metallic is not None:
            mat.metallic = max(0.0, min(1.0, float(metallic)))
        if specular_f0 is not None:
            mat.specular_f0 = max(0.0, min(0.20, float(specular_f0)))
        if specular_intensity is not None:
            mat.specular_intensity = max(0.0, float(specular_intensity))
        if enable_specular is not None:
            scene.render_settings.enable_specular = bool(enable_specular)

        mat.validate()
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def update_environment_params(
        self,
        enabled: Optional[bool] = None,
        intensity: Optional[float] = None,
        rotation_deg: Optional[float] = None,
        diffuse_weight: Optional[float] = None,
        specular_weight: Optional[float] = None
    ) -> None:
        """Updates environment lighting / IBL parameters."""
        scene = self.current_scene
        env = scene.environment
        if enabled is not None:
            env.enabled = bool(enabled)
        if intensity is not None:
            env.intensity = max(0.0, float(intensity))
        if rotation_deg is not None:
            env.rotation_deg = float(rotation_deg) % 360.0
        if diffuse_weight is not None:
            env.diffuse_weight = max(0.0, min(1.0, float(diffuse_weight)))
        if specular_weight is not None:
            env.specular_weight = max(0.0, min(1.0, float(specular_weight)))

        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def update_subject_proxy_params(
        self,
        proxy_type: Optional[str] = None,
        dimensions: Optional[List[float]] = None,
        position: Optional[List[float]] = None,
        position_y: Optional[float] = None,
        rotation_deg: Optional[List[float]] = None,
        scale: Optional[List[float]] = None
    ) -> None:
        """Updates subject proxy geometry type, dimensions, position, rotation, and scale."""
        scene = self.current_scene
        if proxy_type is not None:
            pt = str(proxy_type).upper().strip()
            if pt in ("BOX", "CUBE"):
                pt = "OBB"
            elif pt in ("CYLINDER", "CAPSULE"):
                pt = "SUPERQUADRIC"
            scene.subject.proxy_type = ProxyType(pt)
        if dimensions is not None:
            scene.subject.dimensions = [max(0.01, float(d)) for d in dimensions]
        if position is not None:
            scene.subject.position = [float(p) for p in position]
        elif position_y is not None:
            scene.subject.position[1] = float(position_y)
        if rotation_deg is not None:
            scene.subject.rotation_deg = [float(r) for r in rotation_deg]
        if scale is not None:
            scene.subject.scale = [max(0.01, float(s)) for s in scale]

        scene.subject.validate()
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def snap_subject_to_ground(self) -> float:
        """Adjusts subject elevation so its lowest point rests precisely on the receiver ground."""
        scene = self.current_scene
        new_pos = snap_proxy_to_ground(
            position=scene.subject.position,
            dimensions=scene.subject.dimensions,
            rotation_euler=scene.subject.rotation_deg,
            scale=scene.subject.scale,
            ground_y=scene.receiver.ground_y,
            proxy_type=scene.subject.proxy_type.value,
            sq_exponents=scene.subject.sq_exponents
        )
        scene.subject.position = new_pos
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)
        return new_pos[1]

    def update_receiver_params(
        self,
        receiver_type: str,
        ground_y: Optional[float] = None,
        cove_radius: Optional[float] = None,
        wall_z: Optional[float] = None
    ) -> None:
        """Updates background receiver geometry (plane vs cyclorama)."""
        scene = self.current_scene
        if isinstance(receiver_type, str):
            try:
                scene.receiver.receiver_type = ReceiverType(receiver_type.upper())
            except ValueError:
                scene.receiver.receiver_type = ReceiverType(receiver_type)
        else:
            scene.receiver.receiver_type = receiver_type
        if ground_y is not None:
            scene.receiver.ground_y = float(ground_y)
        if cove_radius is not None:
            scene.receiver.cove_radius = max(0.05, float(cove_radius))
        if wall_z is not None:
            scene.receiver.wall_z = float(wall_z)

        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def undo(self) -> None:
        """Reverts to previous scene snapshot."""
        if self.state_manager.can_undo:
            self.state_manager.undo()
            self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def redo(self) -> None:
        """Re-applies next undone scene snapshot."""
        if self.state_manager.can_redo:
            self.state_manager.redo()
            self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    # -----------------------------------------------------------------------
    # 3. RENDERING DISPATCH & DYNAMIC PROGRESSIVE QUALITY
    # -----------------------------------------------------------------------

    def begin_interaction(self) -> None:
        """Signals start of continuous drag gesture for responsive previewing."""
        self.is_interacting = True

    def end_interaction(self) -> None:
        """Signals end of drag gesture: commits state snapshot and triggers progressive refinement."""
        self.is_interacting = False
        self.state_manager.push_state(self.current_scene)
        # Settle render in progressive final quality
        self.request_render(quality=RenderQuality.FINAL, async_mode=True)

    def request_render(self, quality: RenderQuality = RenderQuality.PREVIEW, async_mode: bool = True) -> Dict[str, Any]:
        """Dispatches a render pass using the authoritative scene state."""
        if not self.project or self.project.img_orig_srgb is None:
            return {}

        scene = self.current_scene
        if async_mode:
            self.orchestrator.submit_request(
                scene=scene,
                image_orig_srgb=self.project.img_orig_srgb,
                depth_map=self.project.depth_map,
                normals_map=self.project.normals_map,
                fg_mask=self.project.fg_mask,
                quality=quality,
                protected_mask=self.project.protected_mask
            )
            return self.orchestrator.get_latest_result() or {}
        else:
            res = self.orchestrator.render_sync(
                scene=scene,
                image_orig_srgb=self.project.img_orig_srgb,
                depth_map=self.project.depth_map,
                normals_map=self.project.normals_map,
                fg_mask=self.project.fg_mask,
                quality=quality,
                protected_mask=self.project.protected_mask
            )
            self.project.last_render_output = res
            return res

    # -----------------------------------------------------------------------
    # 4. VIEWPORT DATA & 3D STAGE PROJECTION
    # -----------------------------------------------------------------------

    def get_scene_hierarchy(self) -> Dict[str, Any]:
        """Returns structured hierarchy for Scene Tree view."""
        scene = self.current_scene
        return {
            "selected_id": self.selected_object_id,
            "scene": {
                "name": "Studio Scene",
                "version": scene.metadata.version,
                "children": [
                    {
                        "id": "camera",
                        "name": f"Camera ({scene.camera.width}x{scene.camera.height})",
                        "type": "camera"
                    },
                    {
                        "id": "subject",
                        "name": f"Subject ({scene.subject.proxy_type.value})",
                        "type": "subject",
                        "material": scene.subject.material.to_dict()
                    },
                    {
                        "id": "receiver",
                        "name": f"Receiver ({scene.receiver.receiver_type.value})",
                        "type": "receiver"
                    },
                    {
                        "id": "environment",
                        "name": "Studio Environment (IBL)",
                        "type": "environment",
                        "enabled": scene.environment.enabled
                    },
                    {
                        "id": "lights_group",
                        "name": f"Lights ({len(scene.lights)})",
                        "type": "group",
                        "children": [
                            {
                                "id": l.id,
                                "name": l.name,
                                "type": "light",
                                "enabled": l.enabled,
                                "cast_shadows": l.cast_shadows,
                                "intensity": l.intensity,
                                "temperature_kelvin": l.temperature_kelvin
                            }
                            for l in scene.lights
                        ]
                    }
                ]
            }
        }

    def get_inspector_data(self) -> Dict[str, Any]:
        """Returns property dictionary for the currently selected object."""
        scene = self.current_scene
        sel_id = self.selected_object_id

        # Check if light selected
        light = scene.get_light(sel_id)
        if light:
            return {
                "type": "light",
                "id": light.id,
                "name": light.name,
                "position": light.position,
                "rotation_deg": light.rotation_deg,
                "width": light.width,
                "height": light.height,
                "intensity": light.intensity,
                "temperature_kelvin": light.temperature_kelvin,
                "energy_convention": light.energy_convention.value,
                "enabled": light.enabled,
                "cast_shadows": light.cast_shadows
            }

        if sel_id == "subject":
            mat = scene.subject.material
            pmeta = compute_proxy_geometry_meta(
                proxy_type=scene.subject.proxy_type.value,
                position=scene.subject.position,
                dimensions=scene.subject.dimensions,
                rotation_euler=scene.subject.rotation_deg,
                scale=scene.subject.scale,
                ground_y=scene.receiver.ground_y,
                sq_exponents=scene.subject.sq_exponents
            )
            return {
                "type": "subject",
                "proxy_type": scene.subject.proxy_type.value,
                "position": scene.subject.position,
                "position_y": scene.subject.position[1],
                "rotation_deg": scene.subject.rotation_deg,
                "dimensions": scene.subject.dimensions,
                "scale": scene.subject.scale,
                "ground_gap_m": pmeta["ground_gap_m"],
                "contact_state": pmeta["contact_state"],
                "lowest_y": pmeta["lowest_y"],
                "roughness": mat.roughness,
                "metallic": mat.metallic,
                "specular_f0": mat.specular_f0,
                "specular_intensity": mat.specular_intensity,
                "enable_specular": scene.render_settings.enable_specular
            }

        if sel_id == "environment":
            env = scene.environment
            return {
                "type": "environment",
                "enabled": env.enabled,
                "intensity": env.intensity,
                "rotation_deg": env.rotation_deg,
                "diffuse_weight": env.diffuse_weight,
                "specular_weight": env.specular_weight
            }

        if sel_id == "receiver":
            rec = scene.receiver
            return {
                "type": "receiver",
                "receiver_type": rec.receiver_type.value,
                "ground_y": rec.ground_y,
                "cove_radius": rec.cove_radius,
                "wall_z": rec.wall_z
            }

        # Camera
        cam = scene.camera
        dist = round(float(np.linalg.norm(np.array(cam.pos, dtype=np.float32) - np.array(cam.target, dtype=np.float32))), 3)
        return {
            "type": "camera",
            "pos": cam.pos,
            "target": cam.target,
            "fov_deg": cam.fov_deg,
            "focal_length_mm": getattr(cam, "focal_length_mm", fov_to_focal_length_mm(cam.fov_deg)),
            "width": cam.width,
            "height": cam.height,
            "elevation": cam.pos[1],
            "distance": dist
        }

    def render_3d_stage_canvas(
        self,
        width: int = 640,
        height: int = 480,
        draw_gizmo: bool = True
    ) -> np.ndarray:
        """
        Renders the 3D Virtual Studio stage with orbit camera, metric grid,
        cyclorama arc, subject proxy, area lights, and interactive 3D transform gizmo.
        """
        scene = self.current_scene
        canvas = np.full((height, width, 3), 24, dtype=np.uint8)

        cam_pos, to_screen, right, cam_up, fwd, f_len = self._get_stage_projector(width, height)

        # 1. Metric Ground Grid (0.5m spacing)
        grid_range = 2.5
        step = 0.5
        for x in np.arange(-grid_range, grid_range + 1e-4, step):
            p1, v1 = to_screen(np.array([x, 0.0, -grid_range]))
            p2, v2 = to_screen(np.array([x, 0.0, grid_range]))
            if v1 or v2:
                col = (60, 60, 65) if abs(x) < 1e-4 else (40, 40, 42)
                cv2.line(canvas, p1, p2, col, 1, cv2.LINE_AA)

        for z in np.arange(-grid_range, grid_range + 1e-4, step):
            p1, v1 = to_screen(np.array([-grid_range, 0.0, z]))
            p2, v2 = to_screen(np.array([grid_range, 0.0, z]))
            if v1 or v2:
                col = (60, 60, 65) if abs(z) < 1e-4 else (40, 40, 42)
                cv2.line(canvas, p1, p2, col, 1, cv2.LINE_AA)

        # 2. Cyclorama Wall/Cove
        if scene.receiver.receiver_type == ReceiverType.CYCLORAMA:
            rec = scene.receiver
            cz = rec.cove_center_yz[1]
            p_c1, v_c1 = to_screen(np.array([-grid_range, 0.0, cz]))
            p_c2, v_c2 = to_screen(np.array([grid_range, 0.0, cz]))
            if v_c1 or v_c2:
                cv2.line(canvas, p_c1, p_c2, (80, 80, 110), 1, cv2.LINE_AA)
            p_w1, v_w1 = to_screen(np.array([-grid_range, rec.cove_radius, rec.wall_z]))
            p_w2, v_w2 = to_screen(np.array([grid_range, rec.cove_radius, rec.wall_z]))
            if v_w1 or v_w2:
                cv2.line(canvas, p_w1, p_w2, (100, 100, 140), 2, cv2.LINE_AA)

        # 3. Subject Proxy Wireframe (Cyan)
        backend = RenderBackend()
        proxy = backend.instantiate_proxy_geometry(scene)
        hx, hy, hz = (
            proxy.half_extents if hasattr(proxy, 'half_extents')
            else proxy.radii if hasattr(proxy, 'radii')
            else (0.35, 0.35, 0.35)
        )
        local_box = np.array([
            [-hx, -hy, -hz], [hx, -hy, -hz], [hx, hy, -hz], [-hx, hy, -hz],
            [-hx, -hy,  hz], [hx, -hy,  hz], [hx, hy,  hz], [-hx, hy,  hz]
        ], dtype=np.float32)
        world_box = (local_box @ proxy.R_inv) + proxy.center
        box_pts = [to_screen(pt)[0] for pt in world_box]
        box_vis = [to_screen(pt)[1] for pt in world_box]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7)
        ]
        is_subj_selected = (self.selected_object_id == "subject")
        box_color = (0, 240, 255) if is_subj_selected else (200, 220, 0)
        for e1, e2 in edges:
            if box_vis[e1] and box_vis[e2]:
                cv2.line(canvas, box_pts[e1], box_pts[e2], box_color, 2 if is_subj_selected else 1, cv2.LINE_AA)

        # 4. Photograph Camera Frustum (Yellow)
        c_pos = np.array(scene.camera.pos, dtype=np.float32)
        c_tgt = np.array(scene.camera.target, dtype=np.float32)
        p_cam, v_cam = to_screen(c_pos)
        p_tgt, v_tgt = to_screen(c_tgt)
        if v_cam:
            cv2.circle(canvas, p_cam, 5, (0, 220, 255), -1, cv2.LINE_AA)
            cv2.putText(canvas, "Camera", (p_cam[0] + 8, p_cam[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 220, 255), 1)
        if v_cam and v_tgt:
            cv2.line(canvas, p_cam, p_tgt, (0, 140, 180), 1, cv2.LINE_AA)

        # 5. Area Lights & 3D Transform Gizmo
        active_light = None
        for light in scene.lights:
            is_selected = (light.id == self.selected_object_id)
            if is_selected:
                active_light = light

            l_pos = np.array(light.position, dtype=np.float32)
            l_obj = RectangularAreaLight(
                position=light.position,
                rotation_euler=light.rotation_deg,
                width=light.width,
                height=light.height
            )
            hw = light.width / 2.0
            hh = light.height / 2.0
            corners_3d = [
                l_pos + (-hw) * l_obj.u_tangent + (-hh) * l_obj.v_bitangent,
                l_pos + ( hw) * l_obj.u_tangent + (-hh) * l_obj.v_bitangent,
                l_pos + ( hw) * l_obj.u_tangent + ( hh) * l_obj.v_bitangent,
                l_pos + (-hw) * l_obj.u_tangent + ( hh) * l_obj.v_bitangent
            ]
            c_screen = [to_screen(pt)[0] for pt in corners_3d]
            c_vis = [to_screen(pt)[1] for pt in corners_3d]

            if all(c_vis):
                pts_poly = np.array(c_screen, dtype=np.int32).reshape((-1, 1, 2))
                if not light.enabled:
                    cv2.polylines(canvas, [pts_poly], True, (70, 70, 70), 1, cv2.LINE_AA)
                elif is_selected:
                    cv2.fillPoly(canvas, [pts_poly], (30, 160, 255))
                    cv2.polylines(canvas, [pts_poly], True, (0, 230, 255), 2, cv2.LINE_AA)
                else:
                    cv2.fillPoly(canvas, [pts_poly], (35, 90, 180))
                    cv2.polylines(canvas, [pts_poly], True, (50, 140, 230), 1, cv2.LINE_AA)

                # Light normal vector arrow
                if light.enabled:
                    norm_tip = l_pos + l_obj.normal * 0.40
                    p_tip, v_tip = to_screen(norm_tip)
                    p_ctr, v_ctr = to_screen(l_pos)
                    if v_tip and v_ctr:
                        arrow_col = (0, 255, 255) if is_selected else (60, 150, 240)
                        cv2.arrowedLine(canvas, p_ctr, p_tip, arrow_col, 2 if is_selected else 1, cv2.LINE_AA, tipLength=0.3)

                p_label = c_screen[0]
                tag = "[SEL] " if is_selected else ""
                cv2.putText(canvas, f"{tag}{light.name}", (p_label[0], p_label[1] - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255) if is_selected else (180, 180, 180), 1)

        # 6. Interactive 3D Transform Gizmo on Selected Light
        if draw_gizmo and active_light is not None:
            g_pos = np.array(active_light.position, dtype=np.float32)
            p_ctr, v_ctr = to_screen(g_pos)
            if v_ctr:
                axis_len = 0.50
                # X-axis (Red)
                p_x, v_x = to_screen(g_pos + np.array([axis_len, 0.0, 0.0]))
                if v_x:
                    cv2.line(canvas, p_ctr, p_x, (0, 0, 240), 3, cv2.LINE_AA)
                    cv2.circle(canvas, p_x, 6, (0, 0, 255), -1, cv2.LINE_AA)
                    cv2.putText(canvas, "X", (p_x[0] + 6, p_x[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 240), 1)

                # Y-axis (Green)
                p_y, v_y = to_screen(g_pos + np.array([0.0, axis_len, 0.0]))
                if v_y:
                    cv2.line(canvas, p_ctr, p_y, (0, 220, 0), 3, cv2.LINE_AA)
                    cv2.circle(canvas, p_y, 6, (0, 255, 0), -1, cv2.LINE_AA)
                    cv2.putText(canvas, "Y", (p_y[0] + 6, p_y[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 220, 0), 1)

                # Z-axis (Blue)
                p_z, v_z = to_screen(g_pos + np.array([0.0, 0.0, axis_len]))
                if v_z:
                    cv2.line(canvas, p_ctr, p_z, (240, 60, 0), 3, cv2.LINE_AA)
                    cv2.circle(canvas, p_z, 6, (255, 80, 0), -1, cv2.LINE_AA)
                    cv2.putText(canvas, "Z", (p_z[0] + 6, p_z[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (240, 60, 0), 1)

                # Center handle
                cv2.circle(canvas, p_ctr, 5, (255, 255, 255), -1, cv2.LINE_AA)

        # 7. Interactive 3D Transform Gizmo on Selected Subject Proxy
        if draw_gizmo and is_subj_selected:
            g_pos = np.array(scene.subject.position, dtype=np.float32)
            p_ctr, v_ctr = to_screen(g_pos)
            if v_ctr:
                axis_len = 0.50
                # X-axis (Red)
                p_x, v_x = to_screen(g_pos + np.array([axis_len, 0.0, 0.0]))
                if v_x:
                    cv2.line(canvas, p_ctr, p_x, (0, 0, 240), 3, cv2.LINE_AA)
                    cv2.circle(canvas, p_x, 6, (0, 0, 255), -1, cv2.LINE_AA)
                    cv2.putText(canvas, "X", (p_x[0] + 6, p_x[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 240), 1)

                # Y-axis (Green)
                p_y, v_y = to_screen(g_pos + np.array([0.0, axis_len, 0.0]))
                if v_y:
                    cv2.line(canvas, p_ctr, p_y, (0, 220, 0), 3, cv2.LINE_AA)
                    cv2.circle(canvas, p_y, 6, (0, 255, 0), -1, cv2.LINE_AA)
                    cv2.putText(canvas, "Y", (p_y[0] + 6, p_y[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 220, 0), 1)

                # Z-axis (Blue)
                p_z, v_z = to_screen(g_pos + np.array([0.0, 0.0, axis_len]))
                if v_z:
                    cv2.line(canvas, p_ctr, p_z, (240, 60, 0), 3, cv2.LINE_AA)
                    cv2.circle(canvas, p_z, 6, (255, 80, 0), -1, cv2.LINE_AA)
                    cv2.putText(canvas, "Z", (p_z[0] + 6, p_z[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (240, 60, 0), 1)

                # Center handle
                cv2.circle(canvas, p_ctr, 5, (255, 255, 255), -1, cv2.LINE_AA)

                # Ground drop-line and contact marker
                pmeta = compute_proxy_geometry_meta(
                    proxy_type=scene.subject.proxy_type.value,
                    position=scene.subject.position,
                    dimensions=scene.subject.dimensions,
                    rotation_euler=scene.subject.rotation_deg,
                    scale=scene.subject.scale,
                    ground_y=scene.receiver.ground_y,
                    sq_exponents=scene.subject.sq_exponents
                )
                p_pt, v_pt = to_screen(np.array(pmeta["contact_point_world"], dtype=np.float32))
                p_mk, v_mk = to_screen(np.array(pmeta["ground_marker_world"], dtype=np.float32))
                if v_pt and v_mk:
                    cv2.line(canvas, p_pt, p_mk, (0, 255, 120), 1, cv2.LINE_AA)
                    cv2.circle(canvas, p_mk, 5, (0, 255, 120), 1, cv2.LINE_AA)

        # Studio Stage HUD overlay
        cv2.putText(canvas, "3D VIRTUAL STUDIO STAGE", (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 180, 180), 1)
        cv2.putText(canvas, f"Orbit: Yaw {self.stage_orbit_yaw_deg:.0f} deg | Pitch {self.stage_orbit_pitch_deg:.0f} deg | Dist {self.stage_orbit_dist:.1f}m",
                    (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (120, 120, 125), 1)

        return canvas

    # -----------------------------------------------------------------------
    # 4. CAMERA MATCHING & PHOTOGRAPHIC ALIGNMENT OVERLAYS
    # -----------------------------------------------------------------------

    def update_camera_params(
        self,
        pos: Optional[List[float]] = None,
        target: Optional[List[float]] = None,
        fov_deg: Optional[float] = None,
        focal_length_mm: Optional[float] = None,
        elevation: Optional[float] = None,
        distance: Optional[float] = None,
        pitch_deg: Optional[float] = None,
        yaw_deg: Optional[float] = None
    ) -> None:
        """
        Updates photograph perspective camera pose and lens parameters.
        Synchronizes vertical FOV (degrees) and 35mm full-frame focal length (mm).
        """
        scene = self.current_scene
        cam = scene.camera

        if focal_length_mm is not None:
            cam.focal_length_mm = float(focal_length_mm)
            cam.fov_deg = focal_length_to_fov_deg(cam.focal_length_mm)
        elif fov_deg is not None:
            cam.fov_deg = max(1.0, min(170.0, float(fov_deg)))
            cam.focal_length_mm = fov_to_focal_length_mm(cam.fov_deg)

        if pos is not None:
            cam.pos = [float(p) for p in pos]
        if target is not None:
            cam.target = [float(t) for t in target]

        if elevation is not None:
            cam.pos[1] = float(elevation)

        if distance is not None:
            cur_pos = np.array(cam.pos, dtype=np.float32)
            cur_tgt = np.array(cam.target, dtype=np.float32)
            diff = cur_pos - cur_tgt
            d = np.linalg.norm(diff)
            if d > 1e-4:
                new_pos = cur_tgt + (diff / d) * max(0.1, float(distance))
                cam.pos = [round(float(v), 3) for v in new_pos]

        if pitch_deg is not None or yaw_deg is not None:
            cur_pos = np.array(cam.pos, dtype=np.float32)
            cur_tgt = np.array(cam.target, dtype=np.float32)
            d = max(0.1, float(np.linalg.norm(cur_pos - cur_tgt)))
            p_rad = math.radians(float(pitch_deg if pitch_deg is not None else 15.0))
            y_rad = math.radians(float(yaw_deg if yaw_deg is not None else 0.0))
            new_pos = cur_tgt + d * np.array([
                math.sin(y_rad) * math.cos(p_rad),
                math.sin(p_rad),
                math.cos(y_rad) * math.cos(p_rad)
            ], dtype=np.float32)
            cam.pos = [round(float(v), 3) for v in new_pos]

        cam.validate()
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def apply_camera_preset(self, preset_name: str) -> float:
        """
        Applies a verified 35mm full-frame camera lens focal length preset:
        - 24mm (Ultra-wide / Environmental) -> FOV ~53.13 deg
        - 35mm (Standard wide / Editorial)   -> FOV ~37.85 deg
        - 50mm (Normal / Commercial default) -> FOV ~27.00 deg
        - 85mm (Portrait telephoto)          -> FOV ~16.08 deg
        - 105mm (Macro / Detail telephoto)   -> FOV ~13.04 deg
        """
        preset_clean = str(preset_name).lower().replace("mm", "").strip()
        preset_map = {
            "24": 24.0,
            "35": 35.0,
            "50": 50.0,
            "85": 85.0,
            "105": 105.0
        }
        fl = preset_map.get(preset_clean, 50.0)
        self.update_camera_params(focal_length_mm=fl)
        return fl

    def fit_camera_to_subject(self, frame_ratio: float = 0.65) -> float:
        """
        Positions camera along its current line of sight so the subject proxy bounding box
        occupies frame_ratio (default 65%) of the camera frame height.
        """
        scene = self.current_scene
        cam = scene.camera
        subj = scene.subject
        dims = np.array(subj.dimensions, dtype=np.float32) * np.array(subj.scale, dtype=np.float32)
        h = float(dims[1] * 2.0)

        fov_rad = math.radians(cam.fov_deg)
        dist = h / (2.0 * frame_ratio * math.tan(fov_rad / 2.0))
        dist = max(0.5, dist)

        cam.target = [round(float(v), 3) for v in subj.position]
        cur_pos = np.array(cam.pos, dtype=np.float32)
        diff = cur_pos - np.array(cam.target, dtype=np.float32)
        d_cur = np.linalg.norm(diff)
        if d_cur > 1e-4:
            new_pos = np.array(cam.target) + (diff / d_cur) * dist
        else:
            new_pos = np.array(cam.target) + np.array([0.0, 0.3 * dist, dist])

        cam.pos = [round(float(v), 3) for v in new_pos]
        cam.validate()
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)
        return round(dist, 3)

    def reset_camera_photo(self) -> None:
        """Resets camera to standard perspective photograph defaults."""
        scene = self.current_scene
        cam = scene.camera
        cam.pos = [0.0, 1.2, 2.5]
        cam.target = [0.0, 0.35, 0.0]
        cam.up = [0.0, 1.0, 0.0]
        cam.focal_length_mm = 50.0
        cam.fov_deg = focal_length_to_fov_deg(50.0)
        cam.validate()
        self.state_manager.push_state(scene)
        self.request_render(quality=RenderQuality.PREVIEW, async_mode=True)

    def get_alignment_projection_meta(
        self,
        canvas_w: Optional[int] = None,
        canvas_h: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Projects 3D scene elements directly into Photograph Viewport 2D coordinates:
        - 3D Proxy wireframe corners and edges
        - 2D silhouette polygon
        - Horizon vanishing line
        - Ground grid lines
        - Ground contact point & marker
        - Cyclorama cove fillet transition
        - Alignment diagnostics (IoU, coverage, bounding box deltas, ground gap)
        """
        scene = self.current_scene
        W = int(canvas_w or scene.camera.width or 1024)
        H = int(canvas_h or scene.camera.height or 768)

        cam = Camera3D(
            width=W,
            height=H,
            pos=scene.camera.pos,
            target=scene.camera.target,
            up=scene.camera.up,
            fov_deg=scene.camera.fov_deg
        )

        proxy_meta = compute_proxy_geometry_meta(
            proxy_type=scene.subject.proxy_type.value,
            position=scene.subject.position,
            dimensions=scene.subject.dimensions,
            rotation_euler=scene.subject.rotation_deg,
            scale=scene.subject.scale,
            ground_y=scene.receiver.ground_y,
            sq_exponents=scene.subject.sq_exponents
        )

        # 1. Project 8 bounding corners
        corners_screen = []
        corners_visible = []
        for pt in proxy_meta["corners_world"]:
            px, py, cam_z = cam.project_point(np.array(pt, dtype=np.float32))
            corners_screen.append([round(px, 1), round(py, 1)])
            corners_visible.append(cam_z > 1e-3 and -W <= px <= 2 * W and -H <= py <= 2 * H)

        # 2. Project silhouette sample points and compute 2D convex hull
        pts_2d = []
        for pt in proxy_meta["silhouette_samples_world"]:
            px, py, cam_z = cam.project_point(np.array(pt, dtype=np.float32))
            if cam_z > 1e-3:
                pts_2d.append([px, py])

        silhouette_polygon = []
        if len(pts_2d) >= 3:
            hull = cv2.convexHull(np.array(pts_2d, dtype=np.float32).reshape((-1, 1, 2)))
            silhouette_polygon = [[round(float(p[0][0]), 1), round(float(p[0][1]), 1)] for p in hull]

        # 3. Horizon vanishing line across photographic plate
        fwd_vec = cam.forward
        d_horiz = np.array([fwd_vec[0], 0.0, fwd_vec[2]], dtype=np.float32)
        norm_d = float(np.linalg.norm(d_horiz))
        horizon_line = []
        if norm_d > 1e-4:
            d_horiz /= norm_d
            r_horiz = np.array([-d_horiz[2], 0.0, d_horiz[0]], dtype=np.float32)
            p_ctr_inf = np.array(cam.pos, dtype=np.float32) + 10000.0 * d_horiz
            p_left = p_ctr_inf - 10000.0 * r_horiz
            p_right = p_ctr_inf + 10000.0 * r_horiz
            pl_x, pl_y, zl = cam.project_point(p_left)
            pr_x, pr_y, zr = cam.project_point(p_right)
            if zl > 1e-3 and zr > 1e-3 and abs(pr_x - pl_x) > 1e-3:
                slope = (pr_y - pl_y) / (pr_x - pl_x)
                y0 = pl_y - slope * pl_x
                yW = y0 + slope * float(W)
                horizon_line = [
                    [0.0, round(float(y0), 1)],
                    [float(W), round(float(yW), 1)]
                ]
            else:
                horizon_line = [[0.0, round(float(cam.cy), 1)], [float(W), round(float(cam.cy), 1)]]
        else:
            horizon_line = [[0.0, round(float(cam.cy), 1)], [float(W), round(float(cam.cy), 1)]]

        # 4. Ground Contact Marker
        g_marker_3d = np.array(proxy_meta["ground_marker_world"], dtype=np.float32)
        px_g, py_g, z_g = cam.project_point(g_marker_3d)
        ground_contact_screen = [round(px_g, 1), round(py_g, 1)] if z_g > 1e-3 else None

        # 5. Ground Grid Lines on Floor Plane
        g_y = float(scene.receiver.ground_y)
        ground_grid = []
        # Longitudinal lines (parallel to Z)
        for x_val in [-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5]:
            p1_x, p1_y, z1 = cam.project_point(np.array([x_val, g_y, -0.5], dtype=np.float32))
            p2_x, p2_y, z2 = cam.project_point(np.array([x_val, g_y, 2.5], dtype=np.float32))
            if z1 > 1e-3 and z2 > 1e-3:
                ground_grid.append([[round(p1_x, 1), round(p1_y, 1)], [round(p2_x, 1), round(p2_y, 1)]])

        # Latitudinal lines (parallel to X)
        for z_val in [-0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
            p1_x, p1_y, z1 = cam.project_point(np.array([-1.5, g_y, z_val], dtype=np.float32))
            p2_x, p2_y, z2 = cam.project_point(np.array([1.5, g_y, z_val], dtype=np.float32))
            if z1 > 1e-3 and z2 > 1e-3:
                ground_grid.append([[round(p1_x, 1), round(p1_y, 1)], [round(p2_x, 1), round(p2_y, 1)]])

        # 6. Cyclorama transition line
        cyclorama_transition = None
        if scene.receiver.receiver_type == ReceiverType.CYCLORAMA:
            cove_z = float(scene.receiver.wall_z + scene.receiver.cove_radius)
            cp1_x, cp1_y, cz1 = cam.project_point(np.array([-2.0, g_y, cove_z], dtype=np.float32))
            cp2_x, cp2_y, cz2 = cam.project_point(np.array([2.0, g_y, cove_z], dtype=np.float32))
            if cz1 > 1e-3 and cz2 > 1e-3:
                cyclorama_transition = [[round(cp1_x, 1), round(cp1_y, 1)], [round(cp2_x, 1), round(cp2_y, 1)]]

        # 7. Alignment Diagnostics (IoU, coverage, bounding box delta, ground gap)
        diagnostics = self.compute_alignment_diagnostics(
            W=W,
            H=H,
            silhouette_poly=silhouette_polygon,
            ground_gap_m=proxy_meta["ground_gap_m"]
        )

        return {
            "image_width": W,
            "image_height": H,
            "corners_screen": corners_screen,
            "corners_visible": corners_visible,
            "edges": proxy_meta["edges"],
            "silhouette_polygon": silhouette_polygon,
            "horizon_line": horizon_line,
            "ground_contact_screen": ground_contact_screen,
            "ground_grid": ground_grid,
            "cyclorama_transition": cyclorama_transition,
            "proxy_type": scene.subject.proxy_type.value,
            "ground_gap_m": proxy_meta["ground_gap_m"],
            "contact_state": proxy_meta["contact_state"],
            "lowest_y": proxy_meta["lowest_y"],
            "camera_focal_length_mm": getattr(scene.camera, "focal_length_mm", fov_to_focal_length_mm(scene.camera.fov_deg)),
            "camera_fov_deg": scene.camera.fov_deg,
            "diagnostics": diagnostics
        }

    def compute_alignment_diagnostics(
        self,
        W: int,
        H: int,
        silhouette_poly: List[List[float]],
        ground_gap_m: float
    ) -> Dict[str, Any]:
        """
        Computes quantitative alignment diagnostics between the projected proxy silhouette
        and the photograph foreground segmentation mask (fg_mask).
        """
        contact_state = "contact" if abs(ground_gap_m) <= 0.005 else ("hovering" if ground_gap_m > 0 else "penetrating")

        if len(silhouette_poly) < 3 or not self.project or self.project.fg_mask is None:
            return {
                "silhouette_iou": 1.0 if len(silhouette_poly) >= 3 else 0.0,
                "foreground_coverage": 1.0 if len(silhouette_poly) >= 3 else 0.0,
                "bbox_delta_px": [0, 0, 0, 0],
                "ground_gap_m": round(float(ground_gap_m), 4),
                "contact_state": contact_state,
                "has_fg_mask": False
            }

        poly_mask = np.zeros((H, W), dtype=np.uint8)
        pts = np.array(silhouette_poly, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(poly_mask, [pts], 255)

        fg = self.project.fg_mask
        if fg.shape[:2] != (H, W):
            fg = cv2.resize(fg.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
        else:
            fg = fg > 0

        poly_bool = (poly_mask > 0)
        intersection = np.logical_and(poly_bool, fg).sum()
        union = np.logical_or(poly_bool, fg).sum()
        fg_sum = fg.sum()

        iou = float(intersection / max(1, union))
        coverage = float(intersection / max(1, fg_sum))

        # Bounding box comparison
        y_poly, x_poly = np.where(poly_bool)
        y_fg, x_fg = np.where(fg)

        if len(x_poly) > 0 and len(x_fg) > 0:
            poly_box = [int(x_poly.min()), int(y_poly.min()), int(x_poly.max()), int(y_poly.max())]
            fg_box = [int(x_fg.min()), int(y_fg.min()), int(x_fg.max()), int(y_fg.max())]
            bbox_delta = [
                int(poly_box[0] - fg_box[0]),
                int(poly_box[1] - fg_box[1]),
                int(poly_box[2] - fg_box[2]),
                int(poly_box[3] - fg_box[3])
            ]
        else:
            bbox_delta = [0, 0, 0, 0]

        return {
            "silhouette_iou": round(iou, 4),
            "foreground_coverage": round(coverage, 4),
            "bbox_delta_px": bbox_delta,
            "ground_gap_m": round(float(ground_gap_m), 4),
            "contact_state": contact_state,
            "has_fg_mask": True
        }

    def render_photograph_with_overlay(
        self,
        mode: str = "relit",
        opacity: float = 0.5,
        width: Optional[int] = None,
        height: Optional[int] = None
    ) -> np.ndarray:
        """
        Renders photographic viewport image with chosen alignment overlay:
        - 'original': unmodified source photograph
        - 'relit': virtual lighting rendered composite
        - 'wireframe': 3D proxy edges projected on photo
        - 'silhouette': semi-transparent proxy polygon overlay
        - 'guides': horizon line, ground grid, and ground contact marker
        - 'mismatch': color-coded IoU diagnostic heatmap (Green=match, Red=under, Blue=over)
        """
        if not self.project or self.project.img_orig_srgb is None:
            return np.full((480, 640, 3), 40, dtype=np.uint8)

        orig_uint8 = np.clip(self.project.img_orig_srgb * 255.0, 0, 255).astype(np.uint8)
        bgr_base = cv2.cvtColor(orig_uint8, cv2.COLOR_RGB2BGR)
        H, W = bgr_base.shape[:2]

        if width and height and (W != width or H != height):
            bgr_base = cv2.resize(bgr_base, (width, height), interpolation=cv2.INTER_LINEAR)
            H, W = height, width

        m = str(mode).lower().strip()
        if m == "original":
            return cv2.cvtColor(bgr_base, cv2.COLOR_BGR2RGB)

        if m == "relit":
            out = self.project.last_render_output
            img_arr = out.get("composite") if out else None
            if img_arr is None and out and "relit_srgb" in out:
                img_arr = out["relit_srgb"]
            if img_arr is not None:
                img_relit = np.clip(img_arr * 255.0, 0, 255).astype(np.uint8)
                if img_relit.shape[:2] != (H, W):
                    img_relit = cv2.resize(img_relit, (W, H), interpolation=cv2.INTER_LINEAR)
                return img_relit
            return cv2.cvtColor(bgr_base, cv2.COLOR_BGR2RGB)

        meta = self.get_alignment_projection_meta(canvas_w=W, canvas_h=H)
        alpha = max(0.0, min(1.0, float(opacity)))

        if m == "wireframe":
            canvas = bgr_base.copy()
            c_screen = meta["corners_screen"]
            c_vis = meta["corners_visible"]
            edges = meta["edges"]
            for e1, e2 in edges:
                if c_vis[e1] or c_vis[e2]:
                    pt1 = (int(c_screen[e1][0]), int(c_screen[e1][1]))
                    pt2 = (int(c_screen[e2][0]), int(c_screen[e2][1]))
                    cv2.line(canvas, pt1, pt2, (0, 240, 255), 2, cv2.LINE_AA)
            for i, pt in enumerate(c_screen):
                if c_vis[i]:
                    cv2.circle(canvas, (int(pt[0]), int(pt[1])), 4, (0, 255, 255), -1, cv2.LINE_AA)
            result = cv2.addWeighted(canvas, alpha, bgr_base, 1.0 - alpha, 0)
            return cv2.cvtColor(result, cv2.COLOR_BGR2RGB)

        if m == "silhouette":
            canvas = bgr_base.copy()
            poly = meta["silhouette_polygon"]
            if len(poly) >= 3:
                pts = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
                overlay = bgr_base.copy()
                cv2.fillPoly(overlay, [pts], (255, 200, 0))
                cv2.polylines(overlay, [pts], True, (255, 240, 100), 2, cv2.LINE_AA)
                canvas = cv2.addWeighted(overlay, alpha, bgr_base, 1.0 - alpha, 0)
            return cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)

        if m == "guides":
            canvas = bgr_base.copy()
            # 1. Horizon line (Gold)
            h_line = meta["horizon_line"]
            if h_line:
                p1 = (int(h_line[0][0]), int(h_line[0][1]))
                p2 = (int(h_line[1][0]), int(h_line[1][1]))
                cv2.line(canvas, p1, p2, (0, 215, 255), 2, cv2.LINE_AA)
                cv2.putText(canvas, "HORIZON", (15, max(20, min(H - 10, p1[1] - 8))),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 215, 255), 1)

            # 2. Ground Grid
            for g_seg in meta["ground_grid"]:
                p1 = (int(g_seg[0][0]), int(g_seg[0][1]))
                p2 = (int(g_seg[1][0]), int(g_seg[1][1]))
                cv2.line(canvas, p1, p2, (180, 150, 40), 1, cv2.LINE_AA)

            # 3. Cyclorama transition
            if meta["cyclorama_transition"]:
                c1 = (int(meta["cyclorama_transition"][0][0]), int(meta["cyclorama_transition"][0][1]))
                c2 = (int(meta["cyclorama_transition"][1][0]), int(meta["cyclorama_transition"][1][1]))
                cv2.line(canvas, c1, c2, (200, 120, 255), 1, cv2.LINE_AA)
                cv2.putText(canvas, "COVE", (c1[0] + 10, c1[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 120, 255), 1)

            # 4. Ground Contact Marker
            gc = meta["ground_contact_screen"]
            if gc:
                pt_gc = (int(gc[0]), int(gc[1]))
                cv2.circle(canvas, pt_gc, 8, (0, 255, 0), 2, cv2.LINE_AA)
                cv2.drawMarker(canvas, pt_gc, (0, 255, 0), cv2.MARKER_CROSS, 16, 2)
                gap_text = f"Gap: {meta['ground_gap_m']:.3f}m ({meta['contact_state']})"
                cv2.putText(canvas, gap_text, (pt_gc[0] + 12, pt_gc[1] + 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 0), 1)

            result = cv2.addWeighted(canvas, alpha, bgr_base, 1.0 - alpha, 0)
            return cv2.cvtColor(result, cv2.COLOR_BGR2RGB)

        if m == "mismatch":
            poly = meta["silhouette_polygon"]
            mask_poly = np.zeros((H, W), dtype=np.uint8)
            if len(poly) >= 3:
                pts = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
                cv2.fillPoly(mask_poly, [pts], 255)

            fg = self.project.fg_mask
            if fg is not None:
                if fg.shape[:2] != (H, W):
                    mask_fg = (cv2.resize(fg.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0)
                else:
                    mask_fg = (fg > 0)
            else:
                mask_fg = (mask_poly > 0)

            p_bool = (mask_poly > 0)
            overlay = bgr_base.copy()
            # Match (both true): Green (0, 230, 0)
            match_mask = (p_bool & mask_fg)
            overlay[match_mask] = (overlay[match_mask] * 0.4 + np.array([0, 230, 0]) * 0.6).astype(np.uint8)
            # Under-coverage (fg true, poly false): Red (0, 0, 240)
            under_mask = (~p_bool & mask_fg)
            overlay[under_mask] = (overlay[under_mask] * 0.4 + np.array([0, 0, 240]) * 0.6).astype(np.uint8)
            # Over-coverage (poly true, fg false): Blue (240, 100, 0)
            over_mask = (p_bool & ~mask_fg)
            overlay[over_mask] = (overlay[over_mask] * 0.4 + np.array([240, 100, 0]) * 0.6).astype(np.uint8)

            result = cv2.addWeighted(overlay, alpha, bgr_base, 1.0 - alpha, 0)
            diag = meta["diagnostics"]
            cv2.putText(result, f"IoU: {diag['silhouette_iou']:.2f} | Coverage: {diag['foreground_coverage']:.2f}",
                        (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            return cv2.cvtColor(result, cv2.COLOR_BGR2RGB)

        return cv2.cvtColor(bgr_base, cv2.COLOR_BGR2RGB)
