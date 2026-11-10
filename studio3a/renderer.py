"""
RELIGHT STUDIO — RS-SPIKE-3A: RENDER BACKEND CONTRACT & ENGINE PIPELINE
========================================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Strict Invariant: Scene-driven deterministic rendering contract.
The renderer operates purely on StudioScene parameters and input image data,
preserving the original photograph non-destructively.
"""

from __future__ import annotations

import time
import math
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import cv2

from studio3a.scene import (
    StudioScene, ProxyType, ReceiverType, EnergyConvention, RenderQuality
)
from studio3a.camera import Camera3D
from studio3a.geometry import (
    OrientedBoundingBox, SuperquadricEllipsoid, SphereProxy, LowPolyMesh,
    GroundPlaneReceiver, CycloramaReceiver
)
from studio3a.lighting import RectangularAreaLight
from studio3a.shadows import ShadowEngine
from studio3a.uncertainty import UncertaintySupervisor
from studio3a.reconstruction import (
    ReconstructionEngine, srgb_to_linear, linear_to_srgb, linear_to_luminance
)


def _bilinear_sample_equirect(map_arr: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    H, W = map_arr.shape[:2]
    px = u * float(W) - 0.5
    py = v * float(H) - 0.5

    x0 = np.floor(px).astype(np.int32)
    y0 = np.floor(py).astype(np.int32)
    x1 = x0 + 1
    y1 = y0 + 1

    fx = (px - x0)[..., None]
    fy = (py - y0)[..., None]

    x0_w = np.mod(x0, W)
    x1_w = np.mod(x1, W)
    y0_c = np.clip(y0, 0, H - 1)
    y1_c = np.clip(y1, 0, H - 1)

    c00 = map_arr[y0_c, x0_w]
    c10 = map_arr[y0_c, x1_w]
    c01 = map_arr[y1_c, x0_w]
    c11 = map_arr[y1_c, x1_w]

    c0 = (1.0 - fx) * c00 + fx * c10
    c1 = (1.0 - fx) * c01 + fx * c11
    return (1.0 - fy) * c0 + fy * c1


def _bilinear_sample_lut(lut_arr: np.ndarray, nv: np.ndarray, r: np.ndarray) -> np.ndarray:
    size = lut_arr.shape[0]
    px = np.clip(nv, 0.0, 1.0) * float(size) - 0.5
    py = np.clip(r, 0.0, 1.0) * float(size) - 0.5

    x0 = np.clip(np.floor(px).astype(np.int32), 0, size - 1)
    y0 = np.clip(np.floor(py).astype(np.int32), 0, size - 1)
    x1 = np.clip(x0 + 1, 0, size - 1)
    y1 = np.clip(y0 + 1, 0, size - 1)

    fx = (px - np.floor(px))[..., None]
    fy = (py - np.floor(py))[..., None]

    c00 = lut_arr[y0, x0]
    c10 = lut_arr[y0, x1]
    c01 = lut_arr[y1, x0]
    c11 = lut_arr[y1, x1]

    c0 = (1.0 - fx) * c00 + fx * c10
    c1 = (1.0 - fx) * c01 + fx * c11
    return (1.0 - fy) * c0 + fy * c1


class RenderBackend:
    """
    Authoritative Rendering Backend Contract.
    Orchestrates analytical 3D proxy geometry, area-light transport,
    and non-destructive image reconstruction.
    """
    def __init__(self):
        self._current_scene: Optional[StudioScene] = None
        self._is_cancelled: bool = False
        self._last_diagnostics: Dict[str, Any] = {}
        self._recon_engine = ReconstructionEngine(r_filter=16, eps_filter=0.02**2)
        self._uncertainty_supervisor = UncertaintySupervisor(tau_cliff=0.04)

    def updateScene(self, scene: StudioScene) -> None:
        """Validates and updates the active scene configuration."""
        scene.validate()
        self._current_scene = scene

    def cancelRender(self) -> None:
        """Signals active rendering job to abort cleanly."""
        self._is_cancelled = True

    def collectDiagnostics(self) -> Dict[str, Any]:
        """Returns profiling and quality diagnostics from the last frame."""
        return self._last_diagnostics.copy()

    def instantiate_proxy_geometry(self, scene: StudioScene):
        """Constructs the analytical 3D proxy instance from scene parameters."""
        subj = scene.subject
        if subj.proxy_type == ProxyType.OBB:
            return OrientedBoundingBox(
                position=subj.position,
                half_extents=subj.dimensions,
                rotation_euler=subj.rotation_deg
            )
        elif subj.proxy_type == ProxyType.SUPERQUADRIC:
            return SuperquadricEllipsoid(
                position=subj.position,
                radii=subj.dimensions,
                sq_exponents=subj.sq_exponents,
                rotation_euler=subj.rotation_deg
            )
        elif subj.proxy_type == ProxyType.SPHERE:
            return SphereProxy(
                position=subj.position,
                radius=subj.dimensions[0]
            )
        elif subj.proxy_type == ProxyType.MESH:
            return LowPolyMesh.create_footwear_hull(
                position=subj.position,
                scale=subj.scale
            )
        else:
            return OrientedBoundingBox(position=subj.position, half_extents=subj.dimensions)

    def instantiate_receiver(self, scene: StudioScene):
        """Constructs the receiver surface from scene parameters."""
        rec = scene.receiver
        if rec.receiver_type == ReceiverType.PLANE:
            return GroundPlaneReceiver(ground_y=rec.ground_y)
        elif rec.receiver_type == ReceiverType.CYCLORAMA:
            return CycloramaReceiver(
                ground_y=rec.ground_y,
                cove_center_yz=rec.cove_center_yz,
                cove_radius=rec.cove_radius,
                wall_z=rec.wall_z
            )
        else:
            return GroundPlaneReceiver(ground_y=rec.ground_y)

    def render(
        self,
        scene: StudioScene,
        image_orig_srgb: np.ndarray,
        depth_map: np.ndarray,
        normals_map: np.ndarray,
        fg_mask: np.ndarray,
        quality: Optional[RenderQuality] = None,
        protected_mask: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Executes complete scene-driven relighting pass.
        Args:
            scene: Authoritative StudioScene parameters.
            image_orig_srgb: (H, W, 3) original photograph in display sRGB [0, 1].
            depth_map: (H, W) estimated monocular depth map in camera space.
            normals_map: (H, W, 3) normalized surface normals in world space.
            fg_mask: (H, W) boolean segmentation mask of subject.
            quality: Optional override for PREVIEW vs FINAL quality.
        Returns:
            Dictionary containing rendered images, masks, and diagnostics.
        """
        t0 = time.time()
        self._is_cancelled = False
        self.updateScene(scene)

        H, W = image_orig_srgb.shape[:2]
        effective_quality = quality or scene.render_settings.quality
        n_samples = (
            scene.render_settings.preview_samples
            if effective_quality == RenderQuality.PREVIEW
            else scene.render_settings.final_samples
        )

        # 1. Establish Camera & Ray Coordinates
        cam = Camera3D(
            pos=scene.camera.pos,
            target=scene.camera.target,
            up=scene.camera.up,
            fov_deg=scene.camera.fov_deg,
            width=W,
            height=H
        )
        ray_o, ray_d = cam.generate_camera_rays()
        fg_mask = (fg_mask > 0).astype(bool)

        # 2. Instantiate Analytical 3D Proxy & Receiver
        proxy = self.instantiate_proxy_geometry(scene)
        receiver = self.instantiate_receiver(scene)
        shadow_engine = ShadowEngine(proxy=proxy, receiver=receiver)

        # 3. Compute 3D Surface Hit Positions
        # For foreground: unproject using camera rays and depth map
        # For receiver: ray intersect receiver geometry
        rec_hit, rec_t, rec_norm = receiver.intersect_rays(ray_o, ray_d)
        
        # Camera ray depth to world position
        # Depth map is distance along camera forward axis (-Z)
        cos_ray_forward = np.maximum(0.1, np.sum(ray_d * cam.forward, axis=-1))
        t_camera_depth = (depth_map * 2.5 + 0.5) / cos_ray_forward # metric scale
        
        surface_pos = np.zeros((H, W, 3), dtype=np.float32)
        surface_norm = np.zeros((H, W, 3), dtype=np.float32)
        is_receiver = (~fg_mask) & rec_hit
        is_sky = (~fg_mask) & (~rec_hit)
        
        # Foreground points
        surface_pos[fg_mask] = ray_o[fg_mask] + t_camera_depth[fg_mask, None] * ray_d[fg_mask]
        surface_norm[fg_mask] = normals_map[fg_mask]
        
        # Receiver points
        surface_pos[is_receiver] = ray_o[is_receiver] + rec_t[is_receiver, None] * ray_d[is_receiver]
        surface_norm[is_receiver] = rec_norm[is_receiver]

        # Explicit sky points (far projection to eliminate [0, 0, 0] coordinate collapse)
        surface_pos[is_sky] = ray_o[is_sky] + 50.0 * ray_d[is_sky]
        surface_norm[is_sky] = -ray_d[is_sky]
        
        # Normalize normals
        n_len = np.linalg.norm(surface_norm, axis=-1, keepdims=True)
        surface_norm = np.where(n_len > 1e-4, surface_norm / np.maximum(n_len, 1e-4), np.array([0.0, 1.0, 0.0]))

        # 4. Multi-Channel Uncertainty Supervisor
        view_dir = cam.forward
        image_lin = srgb_to_linear(image_orig_srgb)
        unc = self._uncertainty_supervisor.evaluate_uncertainty(
            depth=depth_map,
            normals=surface_norm,
            view_dir=view_dir,
            image_lin=image_lin,
            fg_mask=fg_mask
        )

        # 5. Multi-Light Direct Additive Irradiance & Shadow Transport
        cam_pos = np.array(scene.camera.pos, dtype=np.float32)
        v_diff = cam_pos - surface_pos
        v_dist = np.linalg.norm(v_diff, axis=-1, keepdims=True)
        view_dir_per_pixel = np.where(v_dist > 1e-4, v_diff / np.maximum(v_dist, 1e-4), np.array([0.0, 0.0, 1.0], dtype=np.float32))

        mat_subj = getattr(scene.subject, "material", None)
        if mat_subj is None:
            from studio3a.material import MaterialData
            mat_subj = MaterialData()

        mat_rec = getattr(scene.receiver, "material", None)
        if mat_rec is None:
            from studio3a.material import MaterialData
            mat_rec = MaterialData(id="mat_receiver", name="Cyclorama Matte", roughness=0.90, metallic=0.0, specular_intensity=0.20)

        f0_subj = mat_subj.get_effective_f0()
        f0_rec = mat_rec.get_effective_f0()
        kd_subj = 1.0 - mat_subj.metallic
        kd_rec = 1.0 - mat_rec.metallic
        kd_map = np.full((H, W, 1), kd_rec, dtype=np.float32)
        kd_map[fg_mask] = kd_subj

        total_unshadowed_irradiance = np.zeros((H, W, 3), dtype=np.float32)
        total_illuminated_irradiance = np.zeros((H, W, 3), dtype=np.float32)
        total_specular_radiance = np.zeros((H, W, 3), dtype=np.float32)
        active_surface_mask = fg_mask | is_receiver
        num_active_lights = 0
        
        t_light_start = time.time()
        enable_spec = getattr(scene.render_settings, "enable_specular", True)

        for l_idx, light_data in enumerate(scene.lights):
            if not light_data.enabled:
                continue
            num_active_lights += 1
                
            light = RectangularAreaLight(
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
            
            # Direct unshadowed irradiance on active surfaces
            irr_i = light.evaluate_unshadowed_irradiance(
                surface_pos=surface_pos,
                surface_norm=surface_norm,
                n_samples=n_samples,
                seed=42 + l_idx * 17
            )
            irr_i[is_sky] = 0.0
            # Scale diffuse irradiance by (1 - metallic)
            irr_i *= kd_map
            total_unshadowed_irradiance += irr_i

            # Specular radiance from rectangular area light
            if enable_spec:
                spec_subj = light.evaluate_specular_radiance(
                    surface_pos=surface_pos,
                    surface_norm=surface_norm,
                    view_dir=view_dir_per_pixel,
                    roughness=mat_subj.roughness,
                    f0=f0_subj,
                    n_samples=n_samples,
                    seed=42 + l_idx * 17
                )
                spec_rec = light.evaluate_specular_radiance(
                    surface_pos=surface_pos,
                    surface_norm=surface_norm,
                    view_dir=view_dir_per_pixel,
                    roughness=mat_rec.roughness,
                    f0=f0_rec,
                    n_samples=n_samples,
                    seed=42 + l_idx * 17
                )
                spec_i = np.where(fg_mask[..., None], spec_subj, spec_rec)
                spec_i[is_sky] = 0.0
            else:
                spec_i = np.zeros((H, W, 3), dtype=np.float32)
            
            # Geometric Direct Visibility for this specific light
            if scene.render_settings.enable_cast_shadows and getattr(light_data, "cast_shadows", True):
                vis_i = shadow_engine.compute_direct_visibility(
                    surface_pos=surface_pos,
                    surface_norm=surface_norm,
                    light=light,
                    n_samples=n_samples,
                    seed=42 + l_idx * 17,
                    active_mask=active_surface_mask
                )
                vis_i[is_sky] = 1.0
            else:
                vis_i = np.ones((H, W), dtype=np.float32)
            
            # Additive illumination: each light's visibility modulates only its own irradiance and specular
            total_illuminated_irradiance += irr_i * vis_i[..., None]
            if enable_spec:
                total_specular_radiance += spec_i * vis_i[..., None]

        # 5.1 Image-Based Lighting (IBL) Environment Transport
        env_data = getattr(scene, "environment", None)
        if env_data is not None and env_data.enabled and env_data.intensity > 1e-4:
            from studio3a.environment import PreintegratedBRDFLUT, EnvironmentMapProcessor
            from benchmarks.reference_ibl.synthetic_studio_env import SyntheticStudioEnvironment

            env_key = f"{env_data.id}_{env_data.asset_path}"
            if not hasattr(self, "_cached_env_key") or self._cached_env_key != env_key:
                if env_data.asset_path and os.path.exists(env_data.asset_path):
                    import cv2
                    hdr_img = cv2.imread(env_data.asset_path, cv2.IMREAD_UNCHANGED)
                    if hdr_img is not None:
                        if hdr_img.dtype == np.uint8:
                            env_map = (hdr_img.astype(np.float32) / 255.0) ** 2.2
                        else:
                            env_map = hdr_img.astype(np.float32)
                        if len(env_map.shape) == 3 and env_map.shape[2] == 3:
                            env_map = cv2.cvtColor(env_map, cv2.COLOR_BGR2RGB)
                    else:
                        env_map = SyntheticStudioEnvironment(width=512, height=256).data
                else:
                    env_map = SyntheticStudioEnvironment(width=512, height=256).data

                self._cached_env_irr = EnvironmentMapProcessor.compute_diffuse_irradiance_map(
                    env_map, out_width=128, out_height=64, n_samples=128
                )
                self._cached_env_spec_04 = EnvironmentMapProcessor.compute_specular_prefiltered_map(
                    env_map, roughness=0.04, out_width=128, out_height=64, n_samples=128
                )
                self._cached_env_spec_50 = EnvironmentMapProcessor.compute_specular_prefiltered_map(
                    env_map, roughness=0.50, out_width=128, out_height=64, n_samples=128
                )
                self._cached_lut = PreintegratedBRDFLUT.get_lut(size=256, n_samples=256)
                self._cached_env_key = env_key

            rot_rad = -math.radians(env_data.rotation_deg)
            cos_rot, sin_rot = math.cos(rot_rad), math.sin(rot_rad)

            # Normal rotated
            n_rot = np.zeros_like(surface_norm)
            n_rot[..., 0] = cos_rot * surface_norm[..., 0] - sin_rot * surface_norm[..., 2]
            n_rot[..., 1] = surface_norm[..., 1]
            n_rot[..., 2] = sin_rot * surface_norm[..., 0] + cos_rot * surface_norm[..., 2]

            th_n = np.arccos(np.clip(n_rot[..., 1], -1.0, 1.0))
            ph_n = np.arctan2(n_rot[..., 2], n_rot[..., 0])
            u_n = (ph_n + math.pi) / (2.0 * math.pi)
            v_n = th_n / math.pi

            irr_env = _bilinear_sample_equirect(self._cached_env_irr, u_n, v_n)

            tint = np.array(env_data.tint_rgb, dtype=np.float32)
            env_diff_contrib = irr_env * (env_data.intensity * env_data.diffuse_weight) * tint * kd_map
            env_diff_contrib[~active_surface_mask] = 0.0

            total_unshadowed_irradiance += env_diff_contrib
            total_illuminated_irradiance += env_diff_contrib

            if enable_spec and env_data.specular_weight > 1e-4:
                n_dot_v = np.clip(np.sum(surface_norm * view_dir_per_pixel, axis=-1, keepdims=True), 0.0, 1.0)
                r_vec = 2.0 * n_dot_v * surface_norm - view_dir_per_pixel
                r_norm = np.maximum(np.linalg.norm(r_vec, axis=-1, keepdims=True), 1e-7)
                r_vec = r_vec / r_norm

                r_rot = np.zeros_like(r_vec)
                r_rot[..., 0] = cos_rot * r_vec[..., 0] - sin_rot * r_vec[..., 2]
                r_rot[..., 1] = r_vec[..., 1]
                r_rot[..., 2] = sin_rot * r_vec[..., 0] + cos_rot * r_vec[..., 2]

                th_r = np.arccos(np.clip(r_rot[..., 1], -1.0, 1.0))
                ph_r = np.arctan2(r_rot[..., 2], r_rot[..., 0])
                u_r = (ph_r + math.pi) / (2.0 * math.pi)
                v_r = th_r / math.pi

                r_subj = mat_subj.roughness
                r_rec = mat_rec.roughness
                r_map = np.full((H, W), r_rec, dtype=np.float32)
                r_map[fg_mask] = r_subj

                t_rough = np.clip((r_map - 0.04) / (0.50 - 0.04), 0.0, 1.0)[..., None]
                spec_env_04 = _bilinear_sample_equirect(self._cached_env_spec_04, u_r, v_r)
                spec_env_50 = _bilinear_sample_equirect(self._cached_env_spec_50, u_r, v_r)
                spec_env_prefiltered = (1.0 - t_rough) * spec_env_04 + t_rough * spec_env_50

                brdf_scale_bias = _bilinear_sample_lut(self._cached_lut, n_dot_v[..., 0], r_map)

                scale = brdf_scale_bias[..., 0:1]
                bias = brdf_scale_bias[..., 1:2]

                f0_map = np.full((H, W, 3), f0_rec, dtype=np.float32)
                f0_map[fg_mask] = f0_subj

                fresnel_split = f0_map * scale + bias
                spec_env_contrib = fresnel_split * spec_env_prefiltered * (env_data.intensity * env_data.specular_weight) * tint
                spec_env_contrib[~active_surface_mask] = 0.0

                total_specular_radiance += spec_env_contrib
                
        # 6. Contact Grounding Term
        if scene.render_settings.enable_contact_grounding:
            c_contact = shadow_engine.compute_contact_occlusion(
                surface_pos=surface_pos,
                is_receiver=is_receiver,
                ground_y=scene.receiver.ground_y,
                r_contact=0.08
            )
            # Modulate direct illuminated irradiance at contact interface on receiver
            total_illuminated_irradiance[is_receiver] *= c_contact[is_receiver, None]
        else:
            c_contact = np.ones((H, W), dtype=np.float32)

        # Composite radiometric visibility for diagnostics / metrics
        unshadowed_luma = linear_to_luminance(total_unshadowed_irradiance)
        illuminated_luma = linear_to_luminance(total_illuminated_irradiance)
        composite_visibility = np.where(
            unshadowed_luma > 1e-5,
            np.clip(illuminated_luma / np.maximum(unshadowed_luma, 1e-5), 0.0, 1.0),
            1.0
        ).astype(np.float32)
        composite_visibility[is_sky] = 1.0

        t_shadow_ms = (time.time() - t_light_start) * 1000.0

        # 7. Non-Destructive Image Reconstruction (Single Unified E.1 + C3 pass with Two-Scale Specular)
        t_recon_start = time.time()
        recon_res = self._recon_engine.reconstruct_relit_image(
            image_orig_srgb=image_orig_srgb,
            direct_irradiance=total_illuminated_irradiance * scene.render_settings.exposure,
            direct_visibility=None,  # Illumination and contact occlusion are fully integrated into direct_irradiance
            ambient_fill=scene.render_settings.ambient_fill,
            protected_mask=protected_mask,
            specular_radiance=total_specular_radiance * scene.render_settings.exposure if enable_spec else None,
            specular_only=getattr(scene.render_settings, "specular_only", False)
        )
        t_recon_ms = (time.time() - t_recon_start) * 1000.0
        
        total_time_ms = (time.time() - t0) * 1000.0

        # 8. Wireframe Proxy Overlay for Photograph Viewport
        proxy_overlay = self.generate_proxy_overlay(cam, proxy, image_orig_srgb)
        
        # 9. Collect Diagnostics
        self._last_diagnostics = {
            "total_latency_ms": round(total_time_ms, 2),
            "shadow_latency_ms": round(t_shadow_ms, 2),
            "recon_latency_ms": round(t_recon_ms, 2),
            "quality_mode": effective_quality.value,
            "sample_count": n_samples,
            "num_lights": len(scene.lights),
            "num_active_lights": num_active_lights,
            "min_visibility": round(float(np.min(composite_visibility)), 4),
            "mean_visibility": round(float(np.mean(composite_visibility)), 4),
            "max_irradiance": round(float(np.max(total_unshadowed_irradiance)), 4),
            "max_illuminated_irradiance": round(float(np.max(total_illuminated_irradiance)), 4),
            "proxy_type": scene.subject.proxy_type.value,
            "receiver_type": scene.receiver.receiver_type.value
        }

        return {
            "relit_srgb": recon_res["relit_srgb"],
            "image_orig_srgb": image_orig_srgb,
            "direct_visibility": composite_visibility,
            "contact_occlusion": c_contact,
            "direct_irradiance": total_unshadowed_irradiance,
            "illuminated_irradiance": total_illuminated_irradiance,
            "specular_radiance": total_specular_radiance,
            "shading_ratio": recon_res["R_eff"],
            "err_rgb": recon_res["err_rgb"],
            "proxy_overlay": proxy_overlay,
            "uncertainty": unc,
            "diagnostics": self._last_diagnostics
        }

    def generate_proxy_overlay(self, cam: Camera3D, proxy, image_srgb: np.ndarray) -> np.ndarray:
        """Projects 3D proxy wireframe edges onto the original photograph."""
        H, W = image_srgb.shape[:2]
        canvas = (image_srgb * 255.0).astype(np.uint8).copy()
        
        # Get bounding box vertices in local space
        if hasattr(proxy, 'half_extents'):
            hx, hy, hz = proxy.half_extents
        elif hasattr(proxy, 'radii'):
            hx, hy, hz = proxy.radii
        else:
            hx, hy, hz = 0.35, 0.35, 0.35
            
        local_corners = np.array([
            [-hx, -hy, -hz], [hx, -hy, -hz], [hx, hy, -hz], [-hx, hy, -hz],
            [-hx, -hy,  hz], [hx, -hy,  hz], [hx, hy,  hz], [-hx, hy,  hz]
        ], dtype=np.float32)
        
        # Transform corners to world space
        world_corners = (local_corners @ proxy.R_inv) + proxy.center
        
        # Project corners to 2D image coordinates
        proj_pts = []
        for c in world_corners:
            px, py, cz = cam.project_point(c)
            proj_pts.append((int(round(px)), int(round(py)), cz > 0))
            
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),  # bottom ring
            (4, 5), (5, 6), (6, 7), (7, 4),  # top ring
            (0, 4), (1, 5), (2, 6), (3, 7)   # vertical pillars
        ]
        
        for p1_idx, p2_idx in edges:
            x1, y1, v1 = proj_pts[p1_idx]
            x2, y2, v2 = proj_pts[p2_idx]
            if v1 and v2 and 0 <= x1 < W and 0 <= y1 < H and 0 <= x2 < W and 0 <= y2 < H:
                cv2.line(canvas, (x1, y1), (x2, y2), (0, 255, 255), 2, cv2.LINE_AA)
                
        return canvas.astype(np.float32) / 255.0
