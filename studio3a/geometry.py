"""
RELIGHT STUDIO — RS-SPIKE-3A: 3D GEOMETRY ENGINE
================================================
Document Reference: RS-SPEC-HYBRID-RELIGHTING-ARCHITECTURE.md
Implements analytical 3D proxy geometries and parametric receivers:
  1. Oriented Bounding Box (OBB) via Kay-Kajiya slab intersection
  2. Superquadric Ellipsoid via robust interval-bracketed numerical root finding
  3. Low-Poly Triangular Mesh via Möller-Trumbore intersection
  4. Ground Plane & Curved Cyclorama Fillet Receivers
"""

from __future__ import annotations

import math
from typing import Tuple, Optional, List
import numpy as np


def euler_to_rotation_matrix(pitch_deg: float, yaw_deg: float, roll_deg: float) -> np.ndarray:
    """Computes a 3x3 orthonormal rotation matrix from Euler angles (in degrees)."""
    p, y, r = math.radians(pitch_deg), math.radians(yaw_deg), math.radians(roll_deg)
    
    # Rx (pitch)
    Rx = np.array([
        [1.0, 0.0, 0.0],
        [0.0, math.cos(p), -math.sin(p)],
        [0.0, math.sin(p), math.cos(p)]
    ], dtype=np.float32)
    
    # Ry (yaw)
    Ry = np.array([
        [math.cos(y), 0.0, math.sin(y)],
        [0.0, 1.0, 0.0],
        [-math.sin(y), 0.0, math.cos(y)]
    ], dtype=np.float32)
    
    # Rz (roll)
    Rz = np.array([
        [math.cos(r), -math.sin(r), 0.0],
        [math.sin(r), math.cos(r), 0.0],
        [0.0, 0.0, 1.0]
    ], dtype=np.float32)
    
    return (Ry @ Rx @ Rz).astype(np.float32)


# ---------------------------------------------------------------------------
# 1. ORIENTED BOUNDING BOX (OBB)
# ---------------------------------------------------------------------------

class OrientedBoundingBox:
    def __init__(self, position=(0.0, 0.35, 0.0), half_extents=(0.35, 0.35, 0.35),
                 rotation_euler=(0.0, 0.0, 0.0)):
        self.center = np.array(position, dtype=np.float32)
        self.half_extents = np.array(half_extents, dtype=np.float32)
        self.rot_euler = tuple(rotation_euler)
        self.R = euler_to_rotation_matrix(*self.rot_euler)
        self.R_inv = self.R.T  # Orthonormal inverse is transpose

    def intersect_rays(self, ray_o: np.ndarray, ray_d: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Vectorized ray-OBB intersection using slab method in local coordinates.
        Args:
            ray_o: (..., 3) array of ray origins in world coordinates.
            ray_d: (..., 3) array of ray directions in world coordinates.
        Returns:
            hit: (...,) boolean array of hits.
            t: (...,) float array of hit distances along ray.
            norm_world: (..., 3) array of outward surface normals in world space.
        """
        # Transform rays to local canonical frame centered at (0, 0, 0)
        oc = ray_o - self.center
        ro_local = oc @ self.R  # oc @ (R_inv.T) = oc @ R
        rd_local = ray_d @ self.R
        
        bmin = -self.half_extents
        bmax = self.half_extents
        
        inv_d = 1.0 / np.where(np.abs(rd_local) < 1e-6, 1e-6 * np.sign(rd_local + 1e-9), rd_local)
        t0 = (bmin - ro_local) * inv_d
        t1 = (bmax - ro_local) * inv_d
        
        tmin_xyz = np.minimum(t0, t1)
        tmax_xyz = np.maximum(t0, t1)
        
        t_near = np.maximum(np.maximum(tmin_xyz[..., 0], tmin_xyz[..., 1]), tmin_xyz[..., 2])
        t_far = np.minimum(np.minimum(tmax_xyz[..., 0], tmax_xyz[..., 1]), tmax_xyz[..., 2])
        
        hit = (t_near <= t_far) & (t_far > 1e-4)
        t = np.where(hit & (t_near > 1e-4), t_near, np.where(hit & (t_far > 1e-4), t_far, 1e9))
        hit = hit & (t < 1e8)
        
        # Local hit position
        p_local = ro_local + t[..., None] * rd_local
        eps = 1e-3
        norm_local = np.zeros_like(rd_local)
        norm_local = np.where(np.abs(p_local - bmin)[..., 0:1] < eps, np.array([-1.0, 0.0, 0.0]), norm_local)
        norm_local = np.where(np.abs(p_local - bmax)[..., 0:1] < eps, np.array([1.0, 0.0, 0.0]), norm_local)
        norm_local = np.where(np.abs(p_local - bmin)[..., 1:2] < eps, np.array([0.0, -1.0, 0.0]), norm_local)
        norm_local = np.where(np.abs(p_local - bmax)[..., 1:2] < eps, np.array([0.0, 1.0, 0.0]), norm_local)
        norm_local = np.where(np.abs(p_local - bmin)[..., 2:3] < eps, np.array([0.0, 0.0, -1.0]), norm_local)
        norm_local = np.where(np.abs(p_local - bmax)[..., 2:3] < eps, np.array([0.0, 0.0, 1.0]), norm_local)
        
        # Transform local normal back to world coordinates: n_world = R @ n_local
        norm_world = norm_local @ self.R_inv
        norm_len = np.linalg.norm(norm_world, axis=-1, keepdims=True)
        norm_world = np.where(norm_len > 1e-6, norm_world / np.maximum(norm_len, 1e-6), np.array([0.0, 1.0, 0.0]))
        norm_world = np.where(hit[..., None], norm_world, np.zeros_like(norm_world))
        
        return hit, t.astype(np.float32), norm_world.astype(np.float32)


# ---------------------------------------------------------------------------
# 2. SUPERQUADRIC ELLIPSOID
# ---------------------------------------------------------------------------

class SuperquadricEllipsoid:
    """
    Parametric Superquadric Ellipsoid:
      F(x, y, z) = (|x/rx|^(2/e2) + |y/ry|^(2/e2))^(e2/e1) + |z/rz|^(2/e1) - 1 = 0
    e1: vertical squareness (0.1 = cylinder/box, 1.0 = round, 2.0 = diamond)
    e2: horizontal squareness (0.1 = square cross-section, 1.0 = circular cross-section)
    """
    def __init__(self, position=(0.0, 0.35, 0.0), radii=(0.30, 0.40, 0.30),
                 sq_exponents=(1.0, 1.0), rotation_euler=(0.0, 0.0, 0.0)):
        self.center = np.array(position, dtype=np.float32)
        self.radii = np.array(radii, dtype=np.float32)
        self.e1 = float(np.clip(sq_exponents[0], 0.05, 10.0))
        self.e2 = float(np.clip(sq_exponents[1], 0.05, 10.0))
        self.rot_euler = tuple(rotation_euler)
        self.R = euler_to_rotation_matrix(*self.rot_euler)
        self.R_inv = self.R.T

        # Bounding sphere radius
        self.bounding_radius = float(np.max(self.radii) * 1.5)

    def eval_inside_outside(self, p_local: np.ndarray) -> np.ndarray:
        """Evaluates normalized radial distance metric G(p) = rho(p) - 1.0. < 0 inside, > 0 outside."""
        rx, ry, rz = self.radii[0], self.radii[1], self.radii[2]
        nx = np.abs(p_local[..., 0]) / max(rx, 1e-4)
        ny = np.abs(p_local[..., 1]) / max(ry, 1e-4)
        nz = np.abs(p_local[..., 2]) / max(rz, 1e-4)
        
        p_xy = nx**(2.0 / self.e2) + ny**(2.0 / self.e2)
        val = p_xy**(self.e2 / self.e1) + nz**(2.0 / self.e1)
        rho = np.maximum(val, 1e-12)**(self.e1 / 2.0)
        return rho - 1.0

    def eval_gradient(self, p_local: np.ndarray) -> np.ndarray:
        """Computes exact analytical gradient dF/dp in local space."""
        rx, ry, rz = self.radii[0], self.radii[1], self.radii[2]
        x, y, z = p_local[..., 0], p_local[..., 1], p_local[..., 2]
        nx = np.abs(x) / rx
        ny = np.abs(y) / ry
        nz = np.abs(z) / rz
        
        p_xy = np.maximum(nx**(2.0 / self.e2) + ny**(2.0 / self.e2), 1e-6)
        
        # dF/dx
        gx = (2.0 / (self.e1 * rx)) * (p_xy**(self.e2 / self.e1 - 1.0)) * (nx**(2.0 / self.e2 - 1.0)) * np.sign(x)
        # dF/dy
        gy = (2.0 / (self.e1 * ry)) * (p_xy**(self.e2 / self.e1 - 1.0)) * (ny**(2.0 / self.e2 - 1.0)) * np.sign(y)
        # dF/dz
        gz = (2.0 / (self.e1 * rz)) * (nz**(2.0 / self.e1 - 1.0)) * np.sign(z)
        
        grad = np.stack([gx, gy, gz], axis=-1)
        return grad

    def intersect_rays(self, ray_o: np.ndarray, ray_d: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Ray-Superquadric intersection via normalized metric G(p), 32-step interval bracketing + 4-iteration bisection.
        """
        # Local transformation
        oc = ray_o - self.center
        ro_local = oc @ self.R
        rd_local = ray_d @ self.R
        
        # Bounding sphere culling
        b = np.sum(ro_local * rd_local, axis=-1)
        c = np.sum(ro_local * ro_local, axis=-1) - self.bounding_radius**2
        disc = b * b - c
        hit_sphere = disc >= 0.0
        disc_sqrt = np.sqrt(np.maximum(0.0, disc))
        t_enter = np.maximum(1e-4, -b - disc_sqrt)
        t_exit = -b + disc_sqrt
        valid_range = hit_sphere & (t_exit > 1e-4) & (t_enter < t_exit)
        
        flat_shape = ro_local.shape[:-1]
        t_out = np.ones(flat_shape, dtype=np.float32) * 1e9
        hit_out = np.zeros(flat_shape, dtype=bool)
        norm_world = np.zeros(flat_shape + (3,), dtype=np.float32)
        
        if not np.any(valid_range):
            return hit_out, t_out, norm_world

        # March 32 intervals (33 sample points) matching Metal shader grid
        n_steps = 33
        t_steps = np.linspace(0.0, 1.0, n_steps, dtype=np.float32)
        
        # Vectorized search along rays
        ro_v = ro_local[valid_range]
        rd_v = rd_local[valid_range]
        t0_v = t_enter[valid_range][:, None]
        t1_v = t_exit[valid_range][:, None]
        
        t_samples = t0_v + t_steps[None, :] * (t1_v - t0_v)  # (M, n_steps)
        p_samples = ro_v[:, None, :] + t_samples[..., None] * rd_v[:, None, :] # (M, n_steps, 3)
        
        g_samples = self.eval_inside_outside(p_samples) # (M, n_steps)
        
        # Detect zero crossing (from outside positive to inside negative)
        sign_change = (g_samples[:, :-1] > 0.0) & (g_samples[:, 1:] <= 0.0)
        has_hit = np.any(sign_change, axis=-1)
        
        # Index of first hit step
        first_step = np.argmax(sign_change, axis=-1)
        
        # Bracket between step k and step k+1
        idx_m = np.arange(len(ro_v))
        ta = t_samples[idx_m, first_step]
        tb = t_samples[idx_m, first_step + 1]
        
        # 4 bisection steps for guaranteed interval reduction (factor of 16)
        for _ in range(4):
            t_mid = 0.5 * (ta + tb)
            p_mid = ro_v + t_mid[:, None] * rd_v
            g_mid = self.eval_inside_outside(p_mid)
            cond = g_mid > 0.0
            ta = np.where(cond, t_mid, ta)
            tb = np.where(cond, tb, t_mid)
            
        # 1 safe secant refinement step on well-conditioned G
        ga = self.eval_inside_outside(ro_v + ta[:, None] * rd_v)
        gb = self.eval_inside_outside(ro_v + tb[:, None] * rd_v)
        denom = np.where(np.abs(gb - ga) < 1e-6, 1e-6, gb - ga)
        t_root = ta - ga * (tb - ta) / denom
        t_root = np.clip(t_root, np.minimum(ta, tb), np.maximum(ta, tb))
            
        p_hit_local = ro_v + t_root[:, None] * rd_v
        grad_local = self.eval_gradient(p_hit_local)
        g_max = np.maximum(np.max(np.abs(grad_local), axis=-1, keepdims=True), 1e-12)
        grad_scaled = grad_local / g_max
        grad_norm = grad_scaled / np.maximum(np.linalg.norm(grad_scaled, axis=-1, keepdims=True), 1e-6)
        grad_world = grad_norm @ self.R_inv
        
        # Write back results
        t_valid = np.where(has_hit, t_root, 1e9)
        hit_mask_valid = has_hit & (t_root > 1e-4) & (t_root < 1e8)
        
        t_out[valid_range] = t_valid
        hit_out[valid_range] = hit_mask_valid
        norm_world[valid_range] = np.where(hit_mask_valid[:, None], grad_world, 0.0)
        
        return hit_out, t_out.astype(np.float32), norm_world.astype(np.float32)


# ---------------------------------------------------------------------------
# 3. LOW-POLY MESH PROXY
# ---------------------------------------------------------------------------

class LowPolyMesh:
    """
    Watertight Low-Poly Triangular Mesh for Footwear & Irregular Products.
    Möller-Trumbore ray-triangle intersection with bounding AABB culling.
    """
    def __init__(self, vertices: np.ndarray, faces: np.ndarray,
                 position=(0.0, 0.35, 0.0), scale=(1.0, 1.0, 1.0),
                 rotation_euler=(0.0, 0.0, 0.0)):
        self.center = np.array(position, dtype=np.float32)
        self.scale = np.array(scale, dtype=np.float32)
        self.rot_euler = tuple(rotation_euler)
        self.R = euler_to_rotation_matrix(*self.rot_euler)
        self.R_inv = self.R.T

        # Transform vertices into world space
        v_scaled = vertices * self.scale[None, :]
        self.v_world = (v_scaled @ self.R_inv) + self.center
        self.faces = faces.astype(np.int32)
        
        # Precompute face vertices: v0, v1, v2
        self.v0 = self.v_world[self.faces[:, 0]]
        self.v1 = self.v_world[self.faces[:, 1]]
        self.v2 = self.v_world[self.faces[:, 2]]
        
        # Edge vectors
        self.e1 = self.v1 - self.v0
        self.e2 = self.v2 - self.v0
        
        # Face normals
        fn = np.cross(self.e1, self.e2)
        fn_len = np.linalg.norm(fn, axis=-1, keepdims=True)
        self.face_normals = fn / np.maximum(fn_len, 1e-6)
        
        # World AABB
        self.aabb_min = np.min(self.v_world, axis=0) - 0.01
        self.aabb_max = np.max(self.v_world, axis=0) + 0.01

    @classmethod
    def create_footwear_hull(cls, position=(0.0, 0.15, 0.0), scale=(1.0, 1.0, 1.0)) -> LowPolyMesh:
        """
        Procedural generator for a realistic ~280-triangle footwear hull proxy
        featuring curved toe spring, arched midsole, and heel cup.
        """
        n_rings = 14
        n_segments = 10
        vertices = []
        
        for i in range(n_rings):
            u = i / float(n_rings - 1)  # Heel (0) to Toe (1)
            # Profile parameters
            z = -0.45 + 0.90 * u
            # Sole curvature: toe spring curves upward for u > 0.7
            y_base = 0.05 * (u**3) if u > 0.6 else (0.02 * (1.0 - u) if u < 0.2 else 0.0)
            height = 0.22 * math.sin(u * math.pi * 0.9 + 0.1)
            width = 0.25 * math.sin(u * math.pi) + 0.05
            
            for j in range(n_segments):
                theta = j * (2.0 * math.pi / n_segments)
                vx = (width / 2.0) * math.cos(theta)
                vy = y_base + (height / 2.0) * (1.0 + math.sin(theta))
                vz = z
                vertices.append([vx, vy, vz])
                
        # Front and rear tip caps
        vertices.append([0.0, 0.05, -0.47])  # Heel tip
        vertices.append([0.0, 0.10, 0.47])   # Toe tip
        
        verts_np = np.array(vertices, dtype=np.float32)
        faces = []
        
        # Body quads split into triangles
        for i in range(n_rings - 1):
            for j in range(n_segments):
                next_j = (j + 1) % n_segments
                p0 = i * n_segments + j
                p1 = i * n_segments + next_j
                p2 = (i + 1) * n_segments + next_j
                p3 = (i + 1) * n_segments + j
                faces.append([p0, p1, p2])
                faces.append([p0, p2, p3])
                
        # End caps
        heel_idx = len(verts_np) - 2
        toe_idx = len(verts_np) - 1
        for j in range(n_segments):
            next_j = (j + 1) % n_segments
            faces.append([heel_idx, j, next_j])
            faces.append([toe_idx, (n_rings - 1) * n_segments + next_j, (n_rings - 1) * n_segments + j])
            
        faces_np = np.array(faces, dtype=np.int32)
        return cls(vertices=verts_np, faces=faces_np, position=position, scale=scale)

    def intersect_rays(self, ray_o: np.ndarray, ray_d: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Vectorized Möller-Trumbore ray-triangle intersection.
        """
        flat_shape = ray_o.shape[:-1]
        best_t = np.ones(flat_shape, dtype=np.float32) * 1e9
        best_norm = np.zeros(flat_shape + (3,), dtype=np.float32)
        hit_mask = np.zeros(flat_shape, dtype=bool)
        
        # AABB Culling
        inv_d = 1.0 / np.where(np.abs(ray_d) < 1e-6, 1e-6 * np.sign(ray_d + 1e-9), ray_d)
        t0 = (self.aabb_min - ray_o) * inv_d
        t1 = (self.aabb_max - ray_o) * inv_d
        tmin_xyz = np.minimum(t0, t1)
        tmax_xyz = np.maximum(t0, t1)
        t_near = np.maximum(np.maximum(tmin_xyz[..., 0], tmin_xyz[..., 1]), tmin_xyz[..., 2])
        t_far = np.minimum(np.minimum(tmax_xyz[..., 0], tmax_xyz[..., 1]), tmax_xyz[..., 2])
        hit_aabb = (t_near <= t_far) & (t_far > 1e-4)
        
        if not np.any(hit_aabb):
            return hit_mask, best_t, best_norm

        # Filter active rays hitting AABB
        ray_o_active = ray_o[hit_aabb]
        ray_d_active = ray_d[hit_aabb]
        
        # Iterate over triangles in chunks to optimize memory
        n_faces = len(self.faces)
        chunk_size = 64
        
        best_t_active = np.ones(len(ray_o_active), dtype=np.float32) * 1e9
        best_n_active = np.zeros((len(ray_o_active), 3), dtype=np.float32)
        
        for c_start in range(0, n_faces, chunk_size):
            c_end = min(c_start + chunk_size, n_faces)
            v0_c = self.v0[c_start:c_end] # (F_c, 3)
            e1_c = self.e1[c_start:c_end]
            e2_c = self.e2[c_start:c_end]
            norm_c = self.face_normals[c_start:c_end]
            
            # Broadcast against active rays: (M, 1, 3) vs (1, F_c, 3)
            # pvec = ray_d x e2
            pvec = np.cross(ray_d_active[:, None, :], e2_c[None, :, :]) # (M, F_c, 3)
            det = np.sum(e1_c[None, :, :] * pvec, axis=-1)              # (M, F_c)
            
            valid_det = np.abs(det) > 1e-6
            inv_det = 1.0 / np.where(valid_det, det, 1.0)
            
            tvec = ray_o_active[:, None, :] - v0_c[None, :, :]          # (M, F_c, 3)
            u = np.sum(tvec * pvec, axis=-1) * inv_det
            valid_u = valid_det & (u >= 0.0) & (u <= 1.0)
            
            qvec = np.cross(tvec, e1_c[None, :, :])
            v = np.sum(ray_d_active[:, None, :] * qvec, axis=-1) * inv_det
            valid_v = valid_u & (v >= 0.0) & (u + v <= 1.0)
            
            t = np.sum(e2_c[None, :, :] * qvec, axis=-1) * inv_det
            hit_tri = valid_v & (t > 1e-4) & (t < best_t_active[:, None])
            
            for m in range(len(ray_o_active)):
                if np.any(hit_tri[m]):
                    f_best = np.argmin(np.where(hit_tri[m], t[m], 1e9))
                    best_t_active[m] = t[m, f_best]
                    best_n_active[m] = norm_c[f_best]
                    
        has_hit_active = best_t_active < 1e8
        best_t[hit_aabb] = np.where(has_hit_active, best_t_active, 1e9)
        best_norm[hit_aabb] = np.where(has_hit_active[:, None], best_n_active, 0.0)
        hit_mask[hit_aabb] = has_hit_active
        
        return hit_mask, best_t, best_norm


# ---------------------------------------------------------------------------
# 4. PARAMETRIC RECEIVER SURFACES
# ---------------------------------------------------------------------------

class GroundPlaneReceiver:
    def __init__(self, ground_y: float = 0.0):
        self.ground_y = float(ground_y)

    def intersect_rays(self, ray_o: np.ndarray, ray_d: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        denom = ray_d[..., 1]
        hit = np.abs(denom) > 1e-5
        t = (self.ground_y - ray_o[..., 1]) / np.where(hit, denom, 1.0)
        hit = hit & (t > 1e-4)
        t = np.where(hit, t, 1e9)
        norm = np.zeros_like(ray_d)
        norm[..., 1] = 1.0
        return hit, t.astype(np.float32), norm.astype(np.float32)


class CycloramaReceiver:
    """
    Curved Studio Cyclorama Cove (Floor + Fillet Cove + Vertical Wall).
    Fillet connects floor Y=0 at Z=-0.80 to vertical wall at Z=-1.20, Y=0.40 with radius 0.40.
    """
    def __init__(self, ground_y: float = 0.0, cove_center_yz=(0.40, -0.80), cove_radius: float = 0.40, wall_z: float = -1.20):
        self.ground_y = float(ground_y)
        self.cy = float(cove_center_yz[0])
        self.cz = float(cove_center_yz[1])
        self.radius = float(cove_radius)
        self.wall_z = float(wall_z)

    def intersect_rays(self, ray_o: np.ndarray, ray_d: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        shape = ray_o.shape[:-1]
        best_t = np.ones(shape, dtype=np.float32) * 1e9
        best_norm = np.zeros(shape + (3,), dtype=np.float32)
        hit_any = np.zeros(shape, dtype=bool)
        
        # 1. Floor section (Z >= cz, Y = 0)
        denom_y = ray_d[..., 1]
        hit_fl = np.abs(denom_y) > 1e-5
        t_fl = (self.ground_y - ray_o[..., 1]) / np.where(hit_fl, denom_y, 1.0)
        pz_fl = ray_o[..., 2] + t_fl * ray_d[..., 2]
        valid_fl = hit_fl & (t_fl > 1e-4) & (pz_fl >= self.cz)
        
        closer = valid_fl & (t_fl < best_t)
        best_t = np.where(closer, t_fl, best_t)
        best_norm = np.where(closer[..., None], np.array([0.0, 1.0, 0.0], dtype=np.float32), best_norm)
        hit_any = hit_any | closer
        
        # 2. Circular Fillet Cove
        # (Y - cy)^2 + (Z - cz)^2 = r^2
        oy = ray_o[..., 1] - self.cy
        oz = ray_o[..., 2] - self.cz
        dy = ray_d[..., 1]
        dz = ray_d[..., 2]
        
        a = dy**2 + dz**2
        b = 2.0 * (oy * dy + oz * dz)
        c = oy**2 + oz**2 - self.radius**2
        disc = b**2 - 4.0 * a * c
        hit_cyl = (disc >= 0.0) & (a > 1e-6)
        disc_sqrt = np.sqrt(np.maximum(0.0, disc))
        t1 = (-b - disc_sqrt) / np.maximum(2.0 * a, 1e-6)
        t2 = (-b + disc_sqrt) / np.maximum(2.0 * a, 1e-6)
        # Check both cylinder intersection roots (t1 near, t2 far)
        py1 = ray_o[..., 1] + t1 * dy
        pz1 = ray_o[..., 2] + t1 * dz
        valid1 = hit_cyl & (t1 > 1e-4) & (py1 >= self.ground_y - 1e-4) & (py1 <= self.cy + 1e-4) & (pz1 >= self.wall_z - 1e-4) & (pz1 <= self.cz + 1e-4)
        
        py2 = ray_o[..., 1] + t2 * dy
        pz2 = ray_o[..., 2] + t2 * dz
        valid2 = hit_cyl & (t2 > 1e-4) & (py2 >= self.ground_y - 1e-4) & (py2 <= self.cy + 1e-4) & (pz2 >= self.wall_z - 1e-4) & (pz2 <= self.cz + 1e-4)
        
        valid_cove = valid1 | valid2
        t_cove = np.where(valid1, t1, np.where(valid2, t2, 1e9))
        py = np.where(valid1, py1, py2)
        pz = np.where(valid1, pz1, pz2)
        
        closer_cove = valid_cove & (t_cove < best_t)
        best_t = np.where(closer_cove, t_cove, best_t)
        
        ny = -(py - self.cy) / self.radius
        nz = -(pz - self.cz) / self.radius
        norm_cove = np.stack([np.zeros_like(ny), ny, nz], axis=-1)
        best_norm = np.where(closer_cove[..., None], norm_cove, best_norm)
        hit_any = hit_any | closer_cove
        
        # 3. Vertical Wall (Z = wall_z, Y >= cy)
        denom_z = ray_d[..., 2]
        hit_wl = np.abs(denom_z) > 1e-5
        t_wl = (self.wall_z - ray_o[..., 2]) / np.where(hit_wl, denom_z, 1.0)
        py_wl = ray_o[..., 1] + t_wl * ray_d[..., 1]
        valid_wl = hit_wl & (t_wl > 1e-4) & (py_wl >= self.cy)
        
        closer_wl = valid_wl & (t_wl < best_t)
        best_t = np.where(closer_wl, t_wl, best_t)
        best_norm = np.where(closer_wl[..., None], np.array([0.0, 0.0, 1.0], dtype=np.float32), best_norm)
        hit_any = hit_any | closer_wl
        
        best_norm = np.where(hit_any[..., None], best_norm, np.zeros_like(best_norm))
        return hit_any, best_t.astype(np.float32), best_norm.astype(np.float32)
