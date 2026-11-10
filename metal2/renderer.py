"""
RELIGHT STUDIO — RS-METAL-2: NATIVE METAL RENDER BACKEND
========================================================
High-performance Apple Silicon GPU rendering backend.
Conforms to the authoritative studio3a.renderer.RenderBackend interface:
  • Accepts StudioScene and NumPy photographic buffers
  • Automatically packs parameters into Metal uniform structs
  • Dispatches GPU compute shader with zero-copy shared memory
  • Preserves exact mathematical formulations of the CPU reference renderer
"""

from __future__ import annotations
import math
import time
from typing import Dict, Any, Optional, Tuple, List
import numpy as np

from studio3a.scene import (
    StudioScene, ProxyType, ReceiverType, EnergyConvention, RenderQuality
)
from studio3a.camera import Camera3D
from studio3a.geometry import LowPolyMesh, euler_to_rotation_matrix
from studio3a.lighting import kelvin_to_linear_rgb, RectangularAreaLight
from metal2.bridge import (
    Metal2Bridge, CCameraParams, CProxyParams, CReceiverParams,
    CLightParams, CTriangleMesh, CMaterialParams
)


class MetalRenderBackend:
    """
    Drop-in native Metal GPU replacement for studio3a.renderer.RenderBackend.
    """
    def __init__(self):
        self.bridge = Metal2Bridge.get_instance()
        self._last_diagnostics: Dict[str, Any] = {}

    def render(
        self,
        scene: StudioScene,
        image_orig_srgb: np.ndarray,
        depth_map: np.ndarray,
        normals_map: np.ndarray,
        fg_mask: np.ndarray,
        quality: Optional[RenderQuality] = None,
        protected_mask: Optional[np.ndarray] = None,
        generate_overlay: bool = False
    ) -> Dict[str, Any]:
        """
        Executes scene-driven relighting pass on Apple Silicon GPU.
        """
        t0 = time.time()
        H, W = image_orig_srgb.shape[:2]

        effective_quality = quality or scene.render_settings.quality
        n_samples = (
            scene.render_settings.preview_samples
            if effective_quality == RenderQuality.PREVIEW
            else scene.render_settings.final_samples
        )

        # 1. Pack Camera Parameters
        cam = Camera3D(
            pos=scene.camera.pos,
            target=scene.camera.target,
            up=scene.camera.up,
            fov_deg=scene.camera.fov_deg,
            width=W,
            height=H
        )

        c_cam = CCameraParams()
        c_cam.position[0] = float(cam.pos[0])
        c_cam.position[1] = float(cam.pos[1])
        c_cam.position[2] = float(cam.pos[2])
        c_cam.forward[0] = float(cam.forward[0])
        c_cam.forward[1] = float(cam.forward[1])
        c_cam.forward[2] = float(cam.forward[2])
        c_cam.right[0] = float(cam.right[0])
        c_cam.right[1] = float(cam.right[1])
        c_cam.right[2] = float(cam.right[2])
        c_cam.up[0] = float(cam.up_cam[0])
        c_cam.up[1] = float(cam.up_cam[1])
        c_cam.up[2] = float(cam.up_cam[2])
        c_cam.fov_rad = float(math.radians(scene.camera.fov_deg))
        c_cam.width = int(W)
        c_cam.height = int(H)

        # 2. Pack Proxy Parameters
        c_proxy = CProxyParams()
        subj = scene.subject
        if subj.proxy_type == ProxyType.OBB:
            c_proxy.proxy_type = 0
            c_proxy.half_extents[0] = float(subj.dimensions[0])
            c_proxy.half_extents[1] = float(subj.dimensions[1])
            c_proxy.half_extents[2] = float(subj.dimensions[2])
        elif subj.proxy_type == ProxyType.SUPERQUADRIC:
            c_proxy.proxy_type = 1
            c_proxy.half_extents[0] = float(subj.dimensions[0])
            c_proxy.half_extents[1] = float(subj.dimensions[1])
            c_proxy.half_extents[2] = float(subj.dimensions[2])
            c_proxy.sq_exponents[0] = float(subj.sq_exponents[0])
            c_proxy.sq_exponents[1] = float(subj.sq_exponents[1])
        elif subj.proxy_type == ProxyType.SPHERE:
            c_proxy.proxy_type = 3
            radius = float(subj.dimensions[0])
            c_proxy.half_extents[0] = radius
            c_proxy.half_extents[1] = radius
            c_proxy.half_extents[2] = radius
        elif subj.proxy_type == ProxyType.MESH:
            c_proxy.proxy_type = 2
            c_proxy.half_extents[0] = float(subj.dimensions[0] * 0.5)
            c_proxy.half_extents[1] = float(subj.dimensions[1] * 0.5)
            c_proxy.half_extents[2] = float(subj.dimensions[2] * 0.5)
            # Store mesh AABB vertical offset and Z half-extent in sq_exponents for GPU culling
            c_proxy.sq_exponents[0] = 0.11
            c_proxy.sq_exponents[1] = 0.48

        c_proxy.position[0] = float(subj.position[0])
        c_proxy.position[1] = float(subj.position[1])
        c_proxy.position[2] = float(subj.position[2])

        # Rotation matrix (Euler to 3x3 using canonical Ry @ Rx @ Rz)
        R = euler_to_rotation_matrix(subj.rotation_deg[0], subj.rotation_deg[1], subj.rotation_deg[2])
        for i in range(9):
            c_proxy.rot_matrix[i] = float(R.flat[i])

        # Triangles if mesh
        triangles_arr = None
        if subj.proxy_type == ProxyType.MESH:
            mesh = LowPolyMesh.create_footwear_hull(position=subj.position, scale=subj.scale)
            c_proxy.num_triangles = len(mesh.v0)
            c_tri_list = []
            for i in range(len(mesh.v0)):
                ct = CTriangleMesh()
                v0, v1, v2 = mesh.v0[i], mesh.v1[i], mesh.v2[i]
                norm = mesh.face_normals[i]
                ct.v0[0], ct.v0[1], ct.v0[2] = float(v0[0]), float(v0[1]), float(v0[2])
                ct.v1[0], ct.v1[1], ct.v1[2] = float(v1[0]), float(v1[1]), float(v1[2])
                ct.v2[0], ct.v2[1], ct.v2[2] = float(v2[0]), float(v2[1]), float(v2[2])
                ct.normal[0], ct.normal[1], ct.normal[2] = float(norm[0]), float(norm[1]), float(norm[2])
                c_tri_list.append(ct)
            triangles_arr = (CTriangleMesh * len(c_tri_list))(*c_tri_list)
        else:
            c_proxy.num_triangles = 0

        # 3. Pack Receiver Parameters
        c_rec = CReceiverParams()
        rec = scene.receiver
        c_rec.receiver_type = 1 if rec.receiver_type == ReceiverType.CYCLORAMA else 0
        c_rec.ground_y = float(rec.ground_y)
        c_rec.cove_center_yz[0] = float(rec.cove_center_yz[0])
        c_rec.cove_center_yz[1] = float(rec.cove_center_yz[1])
        c_rec.cove_radius = float(rec.cove_radius)
        c_rec.wall_z = float(rec.wall_z)

        # 4. Pack Multi-Light Parameters (up to 8 lights)
        c_lights = []
        num_active_lights = 0
        for l_idx, light_data in enumerate(scene.lights[:8]):
            c_light = CLightParams()
            c_light.position[0] = float(light_data.position[0])
            c_light.position[1] = float(light_data.position[1])
            c_light.position[2] = float(light_data.position[2])

            light_obj = RectangularAreaLight(
                position=light_data.position,
                rotation_euler=light_data.rotation_deg,
                width=light_data.width,
                height=light_data.height,
                intensity=light_data.intensity,
                color_rgb=light_data.color_rgb,
                temperature_kelvin=light_data.temperature_kelvin,
                energy_convention=light_data.energy_convention,
                enabled=light_data.enabled
            )
            u_tan = light_obj.u_tangent
            v_bit = light_obj.v_bitangent
            n_light = light_obj.normal

            c_light.u_tangent[0], c_light.u_tangent[1], c_light.u_tangent[2] = float(u_tan[0]), float(u_tan[1]), float(u_tan[2])
            c_light.v_bitangent[0], c_light.v_bitangent[1], c_light.v_bitangent[2] = float(v_bit[0]), float(v_bit[1]), float(v_bit[2])
            c_light.normal[0], c_light.normal[1], c_light.normal[2] = float(n_light[0]), float(n_light[1]), float(n_light[2])

            c_light.dimensions[0] = float(light_data.width)
            c_light.dimensions[1] = float(light_data.height)

            rgb_k = kelvin_to_linear_rgb(light_data.temperature_kelvin)
            rgb_final = rgb_k * np.array(light_data.color_rgb, dtype=np.float32)
            c_light.color_rgb[0] = float(rgb_final[0])
            c_light.color_rgb[1] = float(rgb_final[1])
            c_light.color_rgb[2] = float(rgb_final[2])
            c_light.intensity = float(light_data.intensity)
            c_light.energy_convention = 1 if light_data.energy_convention == EnergyConvention.FIXED_POWER else 0
            c_light.n_samples = int(n_samples)
            c_light.seed = 42 + l_idx * 17
            c_light.cast_shadows = 1 if (scene.render_settings.enable_cast_shadows and getattr(light_data, "cast_shadows", True)) else 0
            c_light.enabled = 1 if light_data.enabled else 0
            c_light.padding = 0.0
            c_lights.append(c_light)
            if light_data.enabled:
                num_active_lights += 1

        # 5. Pack Material Parameters
        c_mat = CMaterialParams()
        subj_mat = getattr(subj, "material", None)
        if subj_mat is not None:
            c_mat.base_color[0] = float(subj_mat.base_color[0])
            c_mat.base_color[1] = float(subj_mat.base_color[1])
            c_mat.base_color[2] = float(subj_mat.base_color[2])
            c_mat.roughness = float(subj_mat.roughness)
            c_mat.metallic = float(subj_mat.metallic)
            c_mat.specular_f0 = float(subj_mat.specular_f0)
            c_mat.specular_intensity = float(subj_mat.specular_intensity)
        else:
            c_mat.base_color[0] = 0.8
            c_mat.base_color[1] = 0.8
            c_mat.base_color[2] = 0.8
            c_mat.roughness = 0.5
            c_mat.metallic = 0.0
            c_mat.specular_f0 = 0.04
            c_mat.specular_intensity = 1.0

        c_mat.enable_specular = 1 if getattr(scene.render_settings, "enable_specular", True) else 0
        c_mat.specular_only = 1 if getattr(scene.render_settings, "specular_only", False) else 0

        # 6. Execute on Metal GPU
        out_relit, out_vis, out_irr, out_spec, gpu_time_ms = self.bridge.render_frame(
            cam_params=c_cam,
            proxy_params=c_proxy,
            rec_params=c_rec,
            light_params=c_lights,
            triangles=triangles_arr,
            depth_map=depth_map,
            normals_map=normals_map,
            fg_mask=fg_mask,
            protected_mask=protected_mask,
            image_orig_srgb=image_orig_srgb,
            material_params=c_mat
        )

        total_wall_ms = (time.time() - t0) * 1000.0

        pool_stats = self.bridge.get_buffer_pool_stats()
        self._last_diagnostics = {
            "gpu_time_ms": round(gpu_time_ms, 2),
            "total_wall_ms": round(total_wall_ms, 2),
            "quality_mode": effective_quality.value,
            "sample_count": n_samples,
            "num_lights": len(c_lights),
            "num_active_lights": num_active_lights,
            "proxy_type": scene.subject.proxy_type.value,
            "receiver_type": scene.receiver.receiver_type.value,
            "device": "Apple Silicon (Metal)",
            "buffer_pool_alloc_count": pool_stats["alloc_count"],
            "buffer_pool_steady_frames": pool_stats["steady_frames"],
        }

        # Wireframe overlay (optional, avoided on hot interactive loop)
        proxy_overlay = self._generate_proxy_overlay(cam, subj, image_orig_srgb) if generate_overlay else None

        return {
            "relit_srgb": out_relit,
            "image_orig_srgb": image_orig_srgb,
            "direct_visibility": out_vis,
            "contact_occlusion": np.ones_like(out_vis),
            "direct_irradiance": out_irr,
            "specular_radiance": out_spec,
            "shading_ratio": np.ones_like(out_vis),
            "proxy_overlay": proxy_overlay,
            "diagnostics": self._last_diagnostics
        }

    def render_interactive_frame(self, *args, **kwargs) -> Dict[str, Any]:
        """Alias for render matching CPURenderBackend contract."""
        return self.render(*args, **kwargs)

    def _generate_proxy_overlay(self, cam: Camera3D, subj, image_srgb: np.ndarray) -> np.ndarray:
        import cv2
        H, W = image_srgb.shape[:2]
        canvas = (image_srgb * 255.0).astype(np.uint8).copy()
        
        hx, hy, hz = subj.dimensions
        local_corners = np.array([
            [-hx, -hy, -hz], [hx, -hy, -hz], [hx, hy, -hz], [-hx, hy, -hz],
            [-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz]
        ], dtype=np.float32)
        
        # Transform corners to world coordinates
        rad_x, rad_y, rad_z = [math.radians(a) for a in subj.rotation_deg]
        cx, sx = math.cos(rad_x), math.sin(rad_x)
        cy, sy = math.cos(rad_y), math.sin(rad_y)
        cz, sz = math.cos(rad_z), math.sin(rad_z)
        R = np.array([
            [cy * cz, sx * sy * cz - cx * sz, cx * sy * cz + sx * sz],
            [cy * sz, sx * sy * sz + cx * cz, cx * sy * sz - sx * cz],
            [-sy, sx * cy, cx * cy]
        ], dtype=np.float32)
        
        world_corners = local_corners @ R.T + np.array(subj.position, dtype=np.float32)
        
        # Project to screen
        screen_pts = []
        for pt in world_corners:
            u, v, in_frustum = cam.project_point(pt)
            screen_pts.append((int(u), int(v), in_frustum))
            
        edges = [
            (0,1), (1,2), (2,3), (3,0),
            (4,5), (5,6), (6,7), (7,4),
            (0,4), (1,5), (2,6), (3,7)
        ]
        
        for e0, e1 in edges:
            p0, p1 = screen_pts[e0], screen_pts[e1]
            if p0[2] and p1[2]:
                cv2.line(canvas, (p0[0], p0[1]), (p1[0], p1[1]), (0, 255, 120), 1, cv2.LINE_AA)
                
        return canvas.astype(np.float32) / 255.0
