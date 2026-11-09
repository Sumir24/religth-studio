"""
RS-METAL-2: Phase 1 Infrastructure Tests
========================================
Validates Metal device initialization, device diagnostics,
shader compilation, buffer dispatch, and actual GPU execution.
"""

import numpy as np
import pytest
from metal2.bridge import Metal2Bridge


def test_metal_device_initialization_and_info():
    bridge = Metal2Bridge.get_instance()
    info = bridge.get_device_info()
    
    print("\n--- Apple Silicon GPU Diagnostics ---")
    for k, v in info.items():
        print(f"  {k}: {v}")
        
    assert "Apple" in info["device_name"], f"Expected Apple GPU, got {info['device_name']}"
    assert info["has_unified_memory"] is True, "Apple Silicon must support unified memory (UMA)"
    assert info["max_buffer_gb"] > 1.0, "Expected at least 1 GB max buffer allocation"


def test_metal_basic_compute_dispatch():
    bridge = Metal2Bridge.get_instance()
    
    N = 1_000_000
    a = np.random.uniform(0.0, 10.0, N).astype(np.float32)
    b = np.random.uniform(0.0, 10.0, N).astype(np.float32)
    scalar = 3.5
    
    # Execute on GPU
    out_gpu, gpu_time_ms = bridge.dispatch_vector_add(a, b, scalar)
    
    # Reference CPU
    out_cpu = a * scalar + b
    
    max_err = float(np.max(np.abs(out_gpu - out_cpu)))
    print(f"\n[GPU EXECUTION] Vector Add ({N:,} floats): GPU time = {gpu_time_ms:.3f}ms, Max Err = {max_err:.8f}")
    
    assert max_err < 1e-5, f"GPU computation diverged from CPU: max error {max_err}"
    assert gpu_time_ms >= 0.0, "GPU execution timer must be non-negative"


def test_metal_custom_shader_compilation():
    bridge = Metal2Bridge.get_instance()
    
    custom_msl = """
    #include <metal_stdlib>
    using namespace metal;
    
    kernel void custom_noop(device float* buf [[buffer(0)]], uint id [[thread_position_in_grid]]) {
        buf[id] = buf[id] * 2.0;
    }
    """
    # Should compile without error
    bridge.compile_shaders_from_source(custom_msl)

