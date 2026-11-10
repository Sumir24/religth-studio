"""
RELIGHT STUDIO — RS-METAL-2: PYTHON CTYPES BRIDGE
=================================================
Exposes libmetal2.dylib to Python with full type annotations,
error checking, and zero-copy NumPy buffer management.
"""

from __future__ import annotations
import os
import ctypes
from ctypes import (
    c_int, c_uint8, c_uint32, c_uint64, c_float, c_char, c_char_p,
    c_bool, c_void_p, Structure, POINTER
)
from typing import Dict, Any, Tuple, Optional
import numpy as np


class MetalDeviceInfo(Structure):
    _fields_ = [
        ("device_name", c_char * 256),
        ("max_buffer_length", c_uint64),
        ("recommended_working_set_size", c_uint64),
        ("max_threads_per_threadgroup_x", c_uint32),
        ("max_threads_per_threadgroup_y", c_uint32),
        ("max_threads_per_threadgroup_z", c_uint32),
        ("has_unified_memory", c_bool),
        ("supports_ray_tracing", c_bool),
    ]


class CCameraParams(Structure):
    _fields_ = [
        ("position", c_float * 3),
        ("forward", c_float * 3),
        ("right", c_float * 3),
        ("up", c_float * 3),
        ("fov_rad", c_float),
        ("width", c_uint32),
        ("height", c_uint32),
    ]


class CLightParams(Structure):
    _fields_ = [
        ("position", c_float * 3),
        ("normal", c_float * 3),
        ("u_tangent", c_float * 3),
        ("v_bitangent", c_float * 3),
        ("dimensions", c_float * 2),
        ("color_rgb", c_float * 3),
        ("intensity", c_float),
        ("energy_convention", c_uint32),
        ("n_samples", c_uint32),
        ("seed", c_uint32),
    ]


class CProxyParams(Structure):
    _fields_ = [
        ("proxy_type", c_uint32),
        ("position", c_float * 3),
        ("half_extents", c_float * 3),
        ("rot_matrix", c_float * 9),
        ("sq_exponents", c_float * 2),
        ("num_triangles", c_uint32),
    ]


class CReceiverParams(Structure):
    _fields_ = [
        ("receiver_type", c_uint32),
        ("ground_y", c_float),
        ("cove_center_yz", c_float * 2),
        ("cove_radius", c_float),
        ("wall_z", c_float),
    ]


class CTriangleMesh(Structure):
    _fields_ = [
        ("v0", c_float * 3),
        ("v1", c_float * 3),
        ("v2", c_float * 3),
        ("normal", c_float * 3),
    ]


class Metal2Bridge:
    _instance: Optional[Metal2Bridge] = None

    def __init__(self, lib_path: Optional[str] = None):
        if lib_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            lib_path = os.path.join(base_dir, "libmetal2.dylib")

        if not os.path.exists(lib_path):
            raise FileNotFoundError(f"Native Metal library not found: {lib_path}. Run 'make -C metal2'.")

        self.lib = ctypes.CDLL(lib_path)

        # Function prototypes
        self.lib.metal2_init_device.restype = c_int

        self.lib.metal2_get_device_info.argtypes = [POINTER(MetalDeviceInfo)]
        self.lib.metal2_get_device_info.restype = c_int

        self.lib.metal2_compile_shaders_from_source.argtypes = [c_char_p]
        self.lib.metal2_compile_shaders_from_source.restype = c_int

        self.lib.metal2_dispatch_vector_add.argtypes = [
            POINTER(c_float), POINTER(c_float), c_float,
            POINTER(c_float), c_uint32, POINTER(c_float)
        ]
        self.lib.metal2_dispatch_vector_add.restype = c_int

        self.lib.metal2_dispatch_oklab_gamut_map.argtypes = [
            POINTER(c_float), POINTER(c_float), c_uint32, POINTER(c_float)
        ]
        self.lib.metal2_dispatch_oklab_gamut_map.restype = c_int

        self.lib.metal2_render_frame.argtypes = [
            POINTER(CCameraParams),
            POINTER(CProxyParams),
            POINTER(CReceiverParams),
            POINTER(CLightParams),
            POINTER(CTriangleMesh),
            c_uint32,
            POINTER(c_float),
            POINTER(c_float),
            POINTER(c_uint8),
            POINTER(c_uint8),
            POINTER(c_float),
            POINTER(c_float),
            POINTER(c_float),
            POINTER(c_float),
            POINTER(c_float)
        ]
        self.lib.metal2_render_frame.restype = c_int

        self.lib.metal2_get_buffer_pool_stats.argtypes = [POINTER(c_uint32), POINTER(c_uint32)]
        self.lib.metal2_get_buffer_pool_stats.restype = c_int

        self.lib.metal2_reset_buffer_pool.restype = c_int

        self.lib.metal2_shutdown.restype = None

        # Initialize device
        status = self.lib.metal2_init_device()
        if status != 0:
            raise RuntimeError(f"Failed to initialize Metal device (code: {status})")

    @classmethod
    def get_instance(cls) -> Metal2Bridge:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_device_info(self) -> Dict[str, Any]:
        info = MetalDeviceInfo()
        status = self.lib.metal2_get_device_info(ctypes.byref(info))
        if status != 0:
            raise RuntimeError(f"metal2_get_device_info failed (code: {status})")

        return {
            "device_name": info.device_name.decode("utf-8"),
            "max_buffer_gb": round(info.max_buffer_length / (1024**3), 2),
            "working_set_gb": round(info.recommended_working_set_size / (1024**3), 2),
            "max_threads_per_threadgroup": (
                info.max_threads_per_threadgroup_x,
                info.max_threads_per_threadgroup_y,
                info.max_threads_per_threadgroup_z,
            ),
            "has_unified_memory": bool(info.has_unified_memory),
            "supports_ray_tracing": bool(info.supports_ray_tracing),
        }

    def compile_shaders_from_source(self, msl_source: str) -> None:
        c_src = msl_source.encode("utf-8")
        status = self.lib.metal2_compile_shaders_from_source(c_src)
        if status != 0:
            raise RuntimeError(f"Metal shader compilation failed (code: {status})")

    def dispatch_vector_add(
        self,
        a: np.ndarray,
        b: np.ndarray,
        scalar: float
    ) -> Tuple[np.ndarray, float]:
        """Dispatches test compute kernel on Metal GPU: out = a * scalar + b."""
        assert a.dtype == np.float32 and b.dtype == np.float32
        assert a.shape == b.shape
        count = a.size
        out = np.empty_like(a, dtype=np.float32)

        a_ptr = a.ctypes.data_as(POINTER(c_float))
        b_ptr = b.ctypes.data_as(POINTER(c_float))
        out_ptr = out.ctypes.data_as(POINTER(c_float))
        gpu_time = c_float(0.0)

        status = self.lib.metal2_dispatch_vector_add(
            a_ptr, b_ptr, c_float(scalar), out_ptr, c_uint32(count), ctypes.byref(gpu_time)
        )
        if status != 0:
            raise RuntimeError(f"metal2_dispatch_vector_add failed (code: {status})")

        return out, float(gpu_time.value)

    def dispatch_oklab_gamut_map(
        self,
        in_rgb: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """
        Dispatches C3 Oklab constant-hue chroma bisection kernel on Metal GPU.
        Input: (N, 3) or (H, W, 3) linear RGB array.
        Returns: (out_rgb, gpu_time_ms)
        """
        orig_shape = in_rgb.shape
        in_flat = np.ascontiguousarray(in_rgb.reshape(-1, 3), dtype=np.float32)
        count = len(in_flat)
        out_flat = np.empty_like(in_flat)

        in_ptr = in_flat.ctypes.data_as(POINTER(c_float))
        out_ptr = out_flat.ctypes.data_as(POINTER(c_float))
        gpu_time = c_float(0.0)

        status = self.lib.metal2_dispatch_oklab_gamut_map(
            in_ptr, out_ptr, c_uint32(count), ctypes.byref(gpu_time)
        )
        if status != 0:
            raise RuntimeError(f"metal2_dispatch_oklab_gamut_map failed (code: {status})")

        return out_flat.reshape(orig_shape), float(gpu_time.value)

    def render_frame(
        self,
        cam_params: CCameraParams,
        proxy_params: CProxyParams,
        rec_params: CReceiverParams,
        light_params: CLightParams,
        triangles: Optional[np.ndarray],
        depth_map: np.ndarray,
        normals_map: np.ndarray,
        fg_mask: Optional[np.ndarray],
        protected_mask: Optional[np.ndarray],
        image_orig_srgb: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        """
        Executes full 3D rendering pass on Metal GPU.
        Returns: (relit_srgb, visibility, irradiance, gpu_time_ms)
        """
        H, W = image_orig_srgb.shape[:2]
        assert depth_map.shape == (H, W)
        assert normals_map.shape == (H, W, 3)

        # Prepare outputs
        out_relit = np.empty((H, W, 3), dtype=np.float32)
        out_vis = np.empty((H, W), dtype=np.float32)
        out_irr = np.empty((H, W, 3), dtype=np.float32)
        gpu_time = c_float(0.0)

        # Ensure C-contiguous
        depth_c = np.ascontiguousarray(depth_map, dtype=np.float32)
        norm_c = np.ascontiguousarray(normals_map, dtype=np.float32)
        img_c = np.ascontiguousarray(image_orig_srgb, dtype=np.float32)

        depth_ptr = depth_c.ctypes.data_as(POINTER(c_float))
        norm_ptr = norm_c.ctypes.data_as(POINTER(c_float))
        img_ptr = img_c.ctypes.data_as(POINTER(c_float))

        fg_ptr = None
        if fg_mask is not None:
            fg_c = np.ascontiguousarray(fg_mask.astype(np.uint8))
            fg_ptr = fg_c.ctypes.data_as(POINTER(c_uint8))

        prot_ptr = None
        if protected_mask is not None:
            prot_c = np.ascontiguousarray(protected_mask.astype(np.uint8))
            prot_ptr = prot_c.ctypes.data_as(POINTER(c_uint8))

        tri_ptr = None
        num_tri = 0
        if triangles is not None and len(triangles) > 0:
            num_tri = len(triangles)
            if hasattr(triangles, "ctypes"):
                tri_ptr = triangles.ctypes.data_as(POINTER(CTriangleMesh))
            else:
                tri_ptr = ctypes.cast(triangles, POINTER(CTriangleMesh))

        out_relit_ptr = out_relit.ctypes.data_as(POINTER(c_float))
        out_vis_ptr = out_vis.ctypes.data_as(POINTER(c_float))
        out_irr_ptr = out_irr.ctypes.data_as(POINTER(c_float))

        status = self.lib.metal2_render_frame(
            ctypes.byref(cam_params),
            ctypes.byref(proxy_params),
            ctypes.byref(rec_params),
            ctypes.byref(light_params),
            tri_ptr,
            c_uint32(num_tri),
            depth_ptr,
            norm_ptr,
            fg_ptr,
            prot_ptr,
            img_ptr,
            out_relit_ptr,
            out_vis_ptr,
            out_irr_ptr,
            ctypes.byref(gpu_time)
        )

        if status != 0:
            raise RuntimeError(f"metal2_render_frame failed on Metal GPU (code: {status})")

        return out_relit, out_vis, out_irr, float(gpu_time.value)

    def get_buffer_pool_stats(self) -> Dict[str, int]:
        """Returns statistics from the persistent UMA buffer pool."""
        alloc_count = c_uint32(0)
        steady_frames = c_uint32(0)
        status = self.lib.metal2_get_buffer_pool_stats(
            ctypes.byref(alloc_count), ctypes.byref(steady_frames)
        )
        if status != 0:
            raise RuntimeError(f"metal2_get_buffer_pool_stats failed (code: {status})")
        return {
            "alloc_count": int(alloc_count.value),
            "steady_frames": int(steady_frames.value),
        }

    def reset_buffer_pool(self) -> None:
        """Frees all cached buffers in the UMA buffer pool."""
        status = self.lib.metal2_reset_buffer_pool()
        if status != 0:
            raise RuntimeError(f"metal2_reset_buffer_pool failed (code: {status})")

    def shutdown(self) -> None:
        self.lib.metal2_shutdown()
