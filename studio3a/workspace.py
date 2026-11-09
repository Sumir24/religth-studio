"""
RELIGHT STUDIO — RS-SPIKE-3A: ARTIST STUDIO WORKSPACE & INTERACTIVE UI
=======================================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Implements the three logical workspace regions:
  1. Photograph Viewport (original, relit, before/after, overlays)
  2. Virtual 3D Studio Viewport (camera frustum, proxy, receiver, area light quad)
  3. Context Inspector (precise 3D controls for light, proxy, receiver, undo/redo)
"""

from __future__ import annotations

import os
import json
import math
import time
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import cv2
from PIL import Image

from studio3a.scene import (
    StudioScene, ProxyType, ReceiverType, EnergyConvention, RenderQuality,
    SceneStateManager
)
from studio3a.camera import Camera3D
from studio3a.lighting import RectangularAreaLight
from studio3a.renderer import RenderBackend


# ---------------------------------------------------------------------------
# 1. VIRTUAL 3D STUDIO STAGE RENDERER (STAGE VIEWPORT)
# ---------------------------------------------------------------------------

def render_virtual_studio_viewport(
    scene: StudioScene,
    width: int = 512,
    height: int = 384,
    camera_orbit_yaw_deg: float = 35.0,
    camera_orbit_pitch_deg: float = 25.0
) -> np.ndarray:
    """
    Renders an isometric / 3/4 perspective view of the 3D Virtual Studio:
      • Ground grid and cyclorama cove boundary
      • Virtual camera representation with frustum pyramid
      • Subject proxy 3D geometry
      • Rectangular area light emitter quad with surface normal indicator
    """
    canvas = np.ones((height, width, 3), dtype=np.uint8) * 28  # Dark studio gray
    
    # 3D Studio Camera looking at origin [0, 0.35, 0]
    stage_dist = 4.5
    rad_yaw = math.radians(camera_orbit_yaw_deg)
    rad_pitch = math.radians(camera_orbit_pitch_deg)
    
    cam_x = stage_dist * math.cos(rad_pitch) * math.sin(rad_yaw)
    cam_y = stage_dist * math.sin(rad_pitch) + 0.35
    cam_z = stage_dist * math.cos(rad_pitch) * math.cos(rad_yaw)
    
    stage_cam = Camera3D(
        pos=(cam_x, cam_y, cam_z),
        target=(0.0, 0.35, 0.0),
        up=(0.0, 1.0, 0.0),
        fov_deg=40.0,
        width=width,
        height=height
    )
    
    def to_screen(pt_3d):
        px, py, cz = stage_cam.project_point(np.array(pt_3d, dtype=np.float32))
        return (int(round(px)), int(round(py))), (cz > 0.1)

    # 1. Draw Ground Plane Grid (Y = 0)
    grid_size = 2.0
    n_lines = 9
    coords = np.linspace(-grid_size, grid_size, n_lines)
    for c in coords:
        # Lines parallel to Z
        p1, v1 = to_screen([c, 0.0, -grid_size])
        p2, v2 = to_screen([c, 0.0, grid_size])
        if v1 and v2:
            cv2.line(canvas, p1, p2, (45, 45, 45), 1, cv2.LINE_AA)
            
        # Lines parallel to X
        p3, v3 = to_screen([-grid_size, 0.0, c])
        p4, v4 = to_screen([grid_size, 0.0, c])
        if v3 and v4:
            cv2.line(canvas, p3, p4, (45, 45, 45), 1, cv2.LINE_AA)
            
    # 2. Draw Cyclorama Cove Fillet Boundary (if active)
    if scene.receiver.receiver_type == ReceiverType.CYCLORAMA:
        rec = scene.receiver
        cz = rec.cove_center_yz[1]
        cy = rec.cove_center_yz[0]
        # Start of cove on floor
        p_c1, v_c1 = to_screen([-grid_size, 0.0, cz])
        p_c2, v_c2 = to_screen([grid_size, 0.0, cz])
        if v_c1 and v_c2:
            cv2.line(canvas, p_c1, p_c2, (80, 80, 120), 1, cv2.LINE_AA)
        # End of cove / start of vertical wall
        p_w1, v_w1 = to_screen([-grid_size, cy, rec.wall_z])
        p_w2, v_w2 = to_screen([grid_size, cy, rec.wall_z])
        if v_w1 and v_w2:
            cv2.line(canvas, p_w1, p_w2, (100, 100, 150), 2, cv2.LINE_AA)
            
    # 3. Draw Subject Proxy (Green / Cyan)
    subj = scene.subject
    backend = RenderBackend()
    proxy = backend.instantiate_proxy_geometry(scene)
    
    if hasattr(proxy, 'half_extents'):
        hx, hy, hz = proxy.half_extents
    elif hasattr(proxy, 'radii'):
        hx, hy, hz = proxy.radii
    else:
        hx, hy, hz = 0.35, 0.35, 0.35
        
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
    for e1, e2 in edges:
        if box_vis[e1] and box_vis[e2]:
            cv2.line(canvas, box_pts[e1], box_pts[e2], (0, 255, 180), 2, cv2.LINE_AA)
            
    # 4. Draw Main Photograph Camera Frustum (Yellow / White)
    cam_pos = np.array(scene.camera.pos, dtype=np.float32)
    cam_tgt = np.array(scene.camera.target, dtype=np.float32)
    p_cam, v_cam = to_screen(cam_pos)
    p_tgt, v_tgt = to_screen(cam_tgt)
    
    if v_cam:
        cv2.circle(canvas, p_cam, 5, (255, 255, 0), -1, cv2.LINE_AA)
        cv2.putText(canvas, "Camera", (p_cam[0] + 8, p_cam[1] - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
    if v_cam and v_tgt:
        cv2.line(canvas, p_cam, p_tgt, (120, 120, 0), 1, cv2.LINE_AA)
        
    # 5. Draw Rectangular Area Light Emitter (Bright Orange / Yellow Quad)
    for light in scene.lights:
        if not light.enabled:
            continue
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
            cv2.fillPoly(canvas, [pts_poly], (40, 140, 255))
            cv2.polylines(canvas, [pts_poly], True, (0, 220, 255), 2, cv2.LINE_AA)
            
            # Normal pointer arrow pointing away from front emitter face
            norm_tip = l_pos + l_obj.normal * 0.40
            p_tip, v_tip = to_screen(norm_tip)
            p_ctr, v_ctr = to_screen(l_pos)
            if v_tip and v_ctr:
                cv2.arrowedLine(canvas, p_ctr, p_tip, (0, 255, 255), 2, cv2.LINE_AA, tipLength=0.3)
                
            p_label = c_screen[0]
            cv2.putText(canvas, f"{light.name} ({light.width:.1f}x{light.height:.1f}m)",
                        (p_label[0], p_label[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 220, 255), 1)

    # Add overlay legend
    cv2.putText(canvas, "3D VIRTUAL STUDIO STAGE", (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    cv2.putText(canvas, f"Proxy: {scene.subject.proxy_type.value} | Receiver: {scene.receiver.receiver_type.value}",
                (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 150, 150), 1)
    return canvas


# ---------------------------------------------------------------------------
# 2. STUDIO WORKSPACE SESSION CONTROLLER
# ---------------------------------------------------------------------------

class StudioWorkspaceSession:
    """
    Session Controller orchestrating:
      • Active photograph, depth map, normal map, and mask
      • Authoritative SceneStateManager
      • High-performance RenderBackend
      • Viewport image generation and split comparisons
    """
    def __init__(self, sample_image_path: Optional[str] = None):
        self.backend = RenderBackend()
        self.state_manager = SceneStateManager(StudioScene())
        
        # Load default or sample photograph
        self.image_path = sample_image_path or "demo_output/nike_sample.jpg"
        self.depth_path = "demo_output/nike_test/depth.png"
        self.normals_path = "demo_output/nike_test/normals.png"
        
        self.load_assets(self.image_path, self.depth_path, self.normals_path)

    def load_assets(self, img_path: str, depth_path: str, normals_path: str) -> None:
        """Loads and pre-processes input photograph, depth, and normal maps."""
        if not os.path.exists(img_path):
            raise FileNotFoundError(f"Image asset missing: {img_path}")
            
        im = Image.open(img_path).convert("RGB")
        self.img_orig_srgb = np.array(im, dtype=np.float32) / 255.0
        H, W = self.img_orig_srgb.shape[:2]
        
        if os.path.exists(depth_path):
            d_im = Image.open(depth_path)
            d_arr = np.array(d_im, dtype=np.float32) / 255.0
            if d_arr.ndim == 3: d_arr = d_arr[..., 0]
            self.depth_map = cv2.resize(d_arr, (W, H), interpolation=cv2.INTER_LINEAR)
        else:
            self.depth_map = np.ones((H, W), dtype=np.float32) * 0.5
            
        if os.path.exists(normals_path):
            n_im = Image.open(normals_path)
            n_arr = (np.array(n_im, dtype=np.float32) / 255.0) * 2.0 - 1.0
            n_arr = n_arr / np.clip(np.linalg.norm(n_arr, axis=-1, keepdims=True), 1e-6, None)
            self.normals_map = cv2.resize(n_arr, (W, H), interpolation=cv2.INTER_LINEAR)
        else:
            self.normals_map = np.zeros((H, W, 3), dtype=np.float32)
            self.normals_map[..., 2] = -1.0 # Facing camera
            
        # Ground estimation and segmentation mask
        ground_y = int(H * 0.85)
        self.fg_mask = (self.depth_map > 0.45) & (np.arange(H)[:, None] <= ground_y)
        
        # Update scene camera dimensions
        scene = copy_scene = self.state_manager.current_scene
        scene.camera.width = W
        scene.camera.height = H
        self.state_manager.push_state(scene)

    def execute_render(self, quality: RenderQuality = RenderQuality.PREVIEW) -> Dict[str, Any]:
        """Executes full render pass using current authoritative scene state."""
        scene = self.state_manager.current_scene
        render_output = self.backend.render(
            scene=scene,
            image_orig_srgb=self.img_orig_srgb,
            depth_map=self.depth_map,
            normals_map=self.normals_map,
            fg_mask=self.fg_mask,
            quality=quality
        )
        
        # Stage viewport
        stage_view = render_virtual_studio_viewport(scene, width=480, height=360)
        render_output["stage_viewport_srgb"] = stage_view.astype(np.float32) / 255.0
        
        # Split comparison image (Left: Original, Right: Relit)
        H, W = self.img_orig_srgb.shape[:2]
        split_x = W // 2
        split_img = np.zeros_like(self.img_orig_srgb)
        split_img[:, :split_x] = self.img_orig_srgb[:, :split_x]
        split_img[:, split_x:] = render_output["relit_srgb"][:, split_x:]
        cv2.line(split_img, (split_x, 0), (split_x, H), (1.0, 1.0, 1.0), 2)
        render_output["split_comparison_srgb"] = split_img
        
        return render_output

    def update_light_params(
        self,
        pos_x: float, pos_y: float, pos_z: float,
        pitch: float, yaw: float, roll: float,
        width: float, height: float,
        intensity: float, temp_k: float,
        convention: str
    ) -> Dict[str, Any]:
        """Artist manipulation action: updates area light parameters."""
        scene = self.state_manager.current_scene
        light = scene.lights[0]
        light.position = [float(pos_x), float(pos_y), float(pos_z)]
        light.rotation_deg = [float(pitch), float(yaw), float(roll)]
        light.width = max(0.05, float(width))
        light.height = max(0.05, float(height))
        light.intensity = max(0.0, float(intensity))
        light.temperature_kelvin = float(temp_k)
        light.energy_convention = EnergyConvention(convention)
        
        self.state_manager.push_state(scene)
        return self.execute_render(quality=RenderQuality.PREVIEW)

    def update_proxy_params(
        self,
        proxy_type_str: str,
        dim_x: float, dim_y: float, dim_z: float,
        sq_e1: float, sq_e2: float,
        pos_y: float
    ) -> Dict[str, Any]:
        """Artist manipulation action: updates subject proxy parameters."""
        scene = self.state_manager.current_scene
        scene.subject.proxy_type = ProxyType(proxy_type_str)
        scene.subject.dimensions = [float(dim_x), float(dim_y), float(dim_z)]
        scene.subject.sq_exponents = [float(sq_e1), float(sq_e2)]
        scene.subject.position[1] = float(pos_y)
        
        self.state_manager.push_state(scene)
        return self.execute_render(quality=RenderQuality.PREVIEW)

    def undo_action(self) -> Dict[str, Any]:
        """Reverts last artist modification."""
        self.state_manager.undo()
        return self.execute_render(quality=RenderQuality.PREVIEW)

    def redo_action(self) -> Dict[str, Any]:
        """Re-applies next undone artist modification."""
        self.state_manager.redo()
        return self.execute_render(quality=RenderQuality.PREVIEW)

    def save_scene(self, file_path: str) -> str:
        """Saves current scene state to JSON."""
        json_data = self.state_manager.current_scene.to_json(indent=2)
        with open(file_path, "w") as f:
            f.write(json_data)
        return file_path

    def load_scene(self, file_path: str, quality: Optional[RenderQuality] = None) -> Dict[str, Any]:
        """Loads scene state from JSON and re-renders."""
        with open(file_path, "r") as f:
            scene = StudioScene.from_json(f.read())
        self.state_manager.push_state(scene)
        return self.execute_render(quality=quality or scene.render_settings.quality)


# ---------------------------------------------------------------------------
# 3. INTERACTIVE GRADIO WORKSPACE APPLICATION BUILDER
# ---------------------------------------------------------------------------

def build_gradio_workspace(session: Optional[StudioWorkspaceSession] = None):
    """
    Constructs the high-fidelity Gradio 6 workspace application.
    """
    import gradio as gr
    sess = session or StudioWorkspaceSession()
    
    with gr.Blocks(title="Relight Studio — Virtual 3D Lighting Studio (RS-SPIKE-3A)") as app:
        gr.Markdown("# 💡 Relight Studio — Virtual 3D Lighting Studio (RS-SPIKE-3A)")
        gr.Markdown("*Artist-Controlled Virtual 3D Studio Foundation for Photographic Relighting*")
        
        with gr.Row():
            # LEFT VIEWPORT: Original & Relit Photograph
            with gr.Column(scale=5):
                gr.Subheader("1. Photograph Viewport")
                viewport_mode = gr.Radio(
                    choices=["Relit Output", "Side-by-Side Split", "Proxy Wireframe Overlay", "Direct Visibility Heatmap", "Original Photograph"],
                    value="Relit Output",
                    label="Viewport Display Mode"
                )
                photo_display = gr.Image(label="Photograph Canvas", type="numpy")
                
            # CENTER VIEWPORT: Virtual 3D Studio Stage
            with gr.Column(scale=4):
                gr.Subheader("2. Virtual 3D Studio Viewport")
                stage_display = gr.Image(label="3D Studio Stage (Frustum, Proxies, Area Light)", type="numpy")
                with gr.Row():
                    btn_undo = gr.Button("↩ Undo")
                    btn_redo = gr.Button("↪ Redo")
                    btn_final = gr.Button("⭐ Render Final Quality")
                diag_box = gr.JSON(label="Live Engine Diagnostics")

        # RIGHT / BOTTOM: Context Inspector Controls
        gr.Markdown("---")
        with gr.Row():
            with gr.Column(scale=1):
                gr.Subheader("3. Light Inspector (3D Area Light)")
                light_pos_x = gr.Slider(-3.0, 3.0, value=1.2, step=0.1, label="Position X (m)")
                light_pos_y = gr.Slider(0.0, 4.0, value=1.8, step=0.1, label="Position Y (m)")
                light_pos_z = gr.Slider(-2.0, 4.0, value=1.5, step=0.1, label="Position Z (m)")
                light_pitch = gr.Slider(-90.0, 90.0, value=-35.0, step=5.0, label="Pitch (deg)")
                light_yaw = gr.Slider(-180.0, 180.0, value=30.0, step=5.0, label="Yaw (deg)")
                light_width = gr.Slider(0.1, 2.0, value=0.6, step=0.05, label="Emitter Width (m)")
                light_height = gr.Slider(0.1, 2.0, value=0.6, step=0.05, label="Emitter Height (m)")
                light_intensity = gr.Slider(0.0, 5.0, value=1.2, step=0.1, label="Intensity")
                light_temp = gr.Slider(2000.0, 9000.0, value=5600.0, step=100.0, label="Temperature (K)")
                light_conv = gr.Dropdown(choices=["FIXED_RADIANCE", "FIXED_POWER"], value="FIXED_RADIANCE", label="Energy Convention")

            with gr.Column(scale=1):
                gr.Subheader("4. Proxy & Receiver Inspector")
                proxy_type = gr.Dropdown(choices=["OBB", "SUPERQUADRIC", "MESH"], value="OBB", label="Proxy Geometry")
                dim_x = gr.Slider(0.05, 1.5, value=0.35, step=0.05, label="Dimension X")
                dim_y = gr.Slider(0.05, 1.5, value=0.35, step=0.05, label="Dimension Y")
                dim_z = gr.Slider(0.05, 1.5, value=0.35, step=0.05, label="Dimension Z")
                sq_e1 = gr.Slider(0.1, 2.0, value=1.0, step=0.1, label="SQ Exponent 1 (Vertical)")
                sq_e2 = gr.Slider(0.1, 2.0, value=1.0, step=0.1, label="SQ Exponent 2 (Horizontal)")
                proxy_pos_y = gr.Slider(0.0, 1.5, value=0.35, step=0.05, label="Proxy Ground Elevation Y")
                receiver_type = gr.Dropdown(choices=["CYCLORAMA", "PLANE"], value="CYCLORAMA", label="Receiver Geometry")

            with gr.Column(scale=1):
                gr.Subheader("5. Scene State & Serialization")
                save_filename = gr.Textbox(value="studio_scene_preset.json", label="Scene File")
                btn_save = gr.Button("💾 Save Scene JSON")
                btn_load = gr.Button("📂 Load Scene JSON")
                status_box = gr.Textbox(label="Status", value="Ready")

        def update_ui(mode, light_res=None):
            if light_res is None:
                light_res = sess.execute_render(quality=RenderQuality.PREVIEW)
                
            if mode == "Relit Output":
                disp = (light_res["relit_srgb"] * 255).astype(np.uint8)
            elif mode == "Side-by-Side Split":
                disp = (light_res["split_comparison_srgb"] * 255).astype(np.uint8)
            elif mode == "Proxy Wireframe Overlay":
                disp = (light_res["proxy_overlay"] * 255).astype(np.uint8)
            elif mode == "Direct Visibility Heatmap":
                vis = light_res["direct_visibility"]
                vis_heat = cv2.applyColorMap((np.clip(vis, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)
                disp = cv2.cvtColor(vis_heat, cv2.COLOR_BGR2RGB)
            else:
                disp = (sess.img_orig_srgb * 255).astype(np.uint8)
                
            stage = (light_res["stage_viewport_srgb"] * 255).astype(np.uint8)
            return disp, stage, light_res["diagnostics"]

        # Connect reactive slider callbacks
        light_inputs = [
            light_pos_x, light_pos_y, light_pos_z,
            light_pitch, light_yaw, gr.State(0.0),
            light_width, light_height,
            light_intensity, light_temp, light_conv
        ]
        
        def on_light_change(*args):
            res = sess.update_light_params(*args)
            return update_ui("Relit Output", res)
            
        for ctrl in [light_pos_x, light_pos_y, light_pos_z, light_pitch, light_yaw, light_width, light_height, light_intensity, light_temp, light_conv]:
            ctrl.change(on_light_change, inputs=light_inputs, outputs=[photo_display, stage_display, diag_box])

        proxy_inputs = [proxy_type, dim_x, dim_y, dim_z, sq_e1, sq_e2, proxy_pos_y]
        def on_proxy_change(*args):
            res = sess.update_proxy_params(*args)
            return update_ui("Relit Output", res)
            
        for ctrl in proxy_inputs:
            ctrl.change(on_proxy_change, inputs=proxy_inputs, outputs=[photo_display, stage_display, diag_box])

        viewport_mode.change(lambda m: update_ui(m), inputs=[viewport_mode], outputs=[photo_display, stage_display, diag_box])
        
        btn_undo.click(lambda: update_ui("Relit Output", sess.undo_action()), outputs=[photo_display, stage_display, diag_box])
        btn_redo.click(lambda: update_ui("Relit Output", sess.redo_action()), outputs=[photo_display, stage_display, diag_box])
        btn_final.click(lambda: update_ui("Relit Output", sess.execute_render(quality=RenderQuality.FINAL)), outputs=[photo_display, stage_display, diag_box])
        
        def on_save(fpath):
            sess.save_scene(fpath)
            return f"Saved scene to {fpath}"
        btn_save.click(on_save, inputs=[save_filename], outputs=[status_box])
        
        def on_load(fpath):
            res = sess.load_scene(fpath)
            disp, stage, diag = update_ui("Relit Output", res)
            return disp, stage, diag, f"Loaded {fpath}"
        btn_load.click(on_load, inputs=[save_filename], outputs=[photo_display, stage_display, diag_box, status_box])

    return app
