#!/usr/bin/env python3
"""
SGLang Inference Server Benchmark
Measures container startup and SGLang readiness times with different snapshotters.

LOG PATTERN DETECTION & PHASES:
===============================

This benchmark monitors SGLang inference server logs and detects the following phases:

1. SGLANG_INIT (SGLang Framework Initialization)
   - Patterns: "starting sglang", "sglang server", "initializing sglang", "launch_server"
   - Detects: SGLang framework startup and server initialization

2. WEIGHTS_DOWNLOAD (Weight Download Start)
   - Patterns: "load weight begin"
   - Detects: Beginning of model weight loading process

3. WEIGHTS_DOWNLOAD_COMPLETE (Weight Download Complete)
   - Patterns: "loading safetensors checkpoint shards: 0%"
   - Detects: First safetensors checkpoint loading starts

4. WEIGHTS_LOADED (Weights Loaded)
   - Patterns: "load weight end"
   - Detects: Completion of weight loading phase

5. KV_CACHE_ALLOCATED (KV Cache Setup)
   - Patterns: "kv cache is allocated", "kv cache allocated"
   - Detects: Key-value cache memory allocation for inference

6. GRAPH_CAPTURE_BEGIN (CUDA Graph Start)
   - Patterns: "capture cuda graph begin", "capturing cuda graph"
   - Detects: Beginning of CUDA graph capture for optimization

7. GRAPH_CAPTURE_END (CUDA Graph Complete)
   - Patterns: "capture cuda graph end", "cuda graph capture complete"
   - Detects: CUDA graph capture completion

8. SERVER_LOG_READY (Server Log Ready)
   - Patterns: "starting server", "server starting", "uvicorn", "listening on"
   - Detects: HTTP/API server initialization (log-based)

9. SERVER_READY (Server Ready)
   - Tested via HTTP requests to /health_generate endpoint with 0.1s polling
   - Detects: API actually responding with valid HTTP 200 responses

MONITORING BEHAVIOR:
===================
- Timeout: 20 minutes (model loading and optimization can be slow)
- Container Status: Monitors container health during startup
- Health Polling: Polls /health_generate endpoint every 0.1 seconds after first log
- Success Criteria: HTTP 200 response from health endpoint
- Port: Maps container port 8000 to specified local port
- Stop Condition: Immediately after health endpoint returns 200

EXAMPLE LOG FLOW:
================
[20.145s] starting sglang → sglang_init
[119.058s] load weight begin → weights_download
[200.525s] loading safetensors checkpoint shards: 0% → weights_download_complete
[233.778s] load weight end → weights_loaded
[233.828s] kv cache is allocated → kv_cache_allocated
[245.123s] capture cuda graph begin → graph_capture_begin
[267.890s] capture cuda graph end → graph_capture_end
[289.456s] starting server → server_log_ready
[291.789s] HTTP 200 /health_generate → server_ready
"""

import requests
import json
import time
from typing import Dict, Optional
from benchmark_base import BenchmarkBase


class SGLangBenchmark(BenchmarkBase):
    def __init__(self, image: str = "", container_name: str = "sglang-timing-test", 
                 snapshotter: str = "nydus", port: int = 8000):
        super().__init__(image, container_name, snapshotter, port)
    
    def get_health_endpoint(self) -> str:
        """Get health endpoint for SGLang application."""
        return "health_generate"
    
    def supports_health_polling(self) -> bool:
        """SGLang application supports health endpoint polling."""
        return True
    
    def _should_stop_monitoring(self, elapsed: float) -> bool:
        """Custom stop monitoring logic for SGLang."""
        # Use base class logic for health polling apps
        return super()._should_stop_monitoring(elapsed)
    
    def _init_phases(self) -> None:
        """Initialize the phases dictionary for SGLang."""
        self.phases = {
            "first_log": None,
            "sglang_init": None,
            "model_loading": None,
            "weights_download": None,
            "weights_download_complete": None,
            "weights_loaded": None,
            "kv_cache_allocated": None,
            "graph_capture_begin": None,
            "graph_capture_end": None,
            "model_loaded": None,
            "server_log_ready": None,
            "server_ready": None
        }
    
    def analyze_log_line(self, line: str, timestamp: float) -> Optional[str]:
        """Analyze a log line and return detected phase."""
        elapsed = timestamp - self.start_time
        line_lower = line.lower()
        
        # SGLang initialization
        if self.phases["sglang_init"] is None:
            if any(pattern in line_lower for pattern in [
                "starting sglang", "sglang server", "initializing sglang", "launch_server"
            ]):
                self.phases["sglang_init"] = elapsed
                return "sglang_init"
        
        # Weight download start (was "load weight begin")
        if self.phases["weights_download"] is None:
            if "load weight begin" in line_lower:
                self.phases["weights_download"] = elapsed
                return "weights_download"
        
        # Weight download complete (first loading safetensors)
        if self.phases["weights_download_complete"] is None:
            if "loading safetensors checkpoint shards:" in line_lower and "0%" in line_lower:
                self.phases["weights_download_complete"] = elapsed
                return "weights_download_complete"
        
        # Weights loaded (was "load weight end")
        if self.phases["weights_loaded"] is None:
            if "load weight end" in line_lower:
                self.phases["weights_loaded"] = elapsed
                return "weights_loaded"
        
        # KV cache allocation
        if self.phases["kv_cache_allocated"] is None:
            if any(pattern in line_lower for pattern in [
                "kv cache is allocated", "kv cache allocated"
            ]):
                self.phases["kv_cache_allocated"] = elapsed
                return "kv_cache_allocated"
        
        # CUDA graph capture begin
        if self.phases["graph_capture_begin"] is None:
            if any(pattern in line_lower for pattern in [
                "capture cuda graph begin", "capturing cuda graph"
            ]):
                self.phases["graph_capture_begin"] = elapsed
                return "graph_capture_begin"
        
        # CUDA graph capture end
        if self.phases["graph_capture_end"] is None:
            if any(pattern in line_lower for pattern in [
                "capture cuda graph end", "cuda graph capture complete"
            ]):
                self.phases["graph_capture_end"] = elapsed
                return "graph_capture_end"
        
        # Server log ready pattern
        if self.phases["server_log_ready"] is None:
            if any(pattern in line_lower for pattern in [
                "starting server", "server starting", "uvicorn", "listening on"
            ]):
                self.phases["server_log_ready"] = elapsed
                return "server_log_ready"
        
        return None
    
    def test_api_readiness(self, timeout: int = 120) -> bool:
        """SGLang benchmark doesn't test API readiness - stops after server ready."""
        print("Skipping API readiness test - stopping after server ready detection")
        return True
    
    def get_default_image(self, snapshotter: str) -> str:
        """Get default image for the snapshotter. Users should now use --repo parameter instead."""
        raise ValueError(
            "No default image configured. Please specify either:\n"
            "  --repo <ecr-repo-name> (e.g., --repo my-sglang-app)\n"
            "  --image <full-image-url> (e.g., --image registry.com/repo:tag)\n"
            "\nExample: python test-bench-sglang.py --repo saurabh-sglang-test --tag latest --snapshotter nydus"
        )
    
    
    
    def _get_summary_items(self, total_time):
        """Get summary items for printing."""
        items = [
            ("Container Startup Time:", self.container_startup_duration),
            ("Container to First Log:", self.phases["first_log"]),
            ("SGLang Initialization:", self.phases["sglang_init"]),
            ("Weight Download Start:", self.phases["weights_download"]),
            ("Weight Download Complete:", self.phases["weights_download_complete"]),
            ("Weights Loaded:", self.phases["weights_loaded"]),
            ("KV Cache Allocated:", self.phases["kv_cache_allocated"]),
            ("Graph Capture Begin:", self.phases["graph_capture_begin"]),
            ("Graph Capture End:", self.phases["graph_capture_end"]),
            ("Server Log Ready:", self.phases["server_log_ready"]),
            ("Server Ready:", self.phases["server_ready"]),
            ("Total Test Time:", total_time)
        ]
        
        # Add breakdown section
        items.append(("", None))  # Empty line separator
        items.append(("BREAKDOWN:", None))
        
        # Calculate breakdowns
        if self.phases["first_log"] is not None:
            items.append(("Container to First Log:", self.phases["first_log"]))
        
        if self.phases["first_log"] is not None and self.phases["weights_download"] is not None:
            first_to_download = self.phases["weights_download"] - self.phases["first_log"]
            items.append(("First Log to Weight Download Start:", first_to_download))
        
        if self.phases["weights_download"] is not None and self.phases["weights_download_complete"] is not None:
            download_duration = self.phases["weights_download_complete"] - self.phases["weights_download"]
            items.append(("Weight Download Start to Complete:", download_duration))
        
        if self.phases["weights_download_complete"] is not None and self.phases["weights_loaded"] is not None:
            download_to_loaded = self.phases["weights_loaded"] - self.phases["weights_download_complete"]
            items.append(("Weight Download Complete to Weights Loaded:", download_to_loaded))
        
        if self.phases["weights_loaded"] is not None and self.phases["server_ready"] is not None:
            loaded_to_ready = self.phases["server_ready"] - self.phases["weights_loaded"]
            items.append(("Weights Loaded to Server Ready:", loaded_to_ready))
        
        return items
    
    def _is_successful(self, results: Dict[str, Optional[float]]) -> bool:
        """Determine if benchmark was successful."""
        return results.get("server_ready") is not None


def main():
    benchmark = SGLangBenchmark()
    return benchmark.main("SGLang Container Startup Benchmark")


if __name__ == "__main__":
    import sys
    import subprocess
    sys.exit(main())