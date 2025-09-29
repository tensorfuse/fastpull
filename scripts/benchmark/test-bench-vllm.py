#!/usr/bin/env python3
"""
vLLM Startup Timing Benchmark
Measures container startup and vLLM readiness times with different snapshotters.

LOG PATTERN DETECTION & PHASES:
===============================

This benchmark monitors vLLM inference server logs and detects the following phases:

1. ENGINE_INIT (vLLM Engine Initialization)
   - Patterns: "initializing a v1 llm engine", "waiting for init message", "v1 llm engine"
   - Detects: vLLM V1 engine initialization start

2. MODEL_LOADING (Model Loading Start)
   - Patterns: "starting to load model", "loading model from scratch"
   - Detects: Beginning of model loading process

3. WEIGHTS_DOWNLOAD (Weight Download)
   - Patterns: "time spent downloading weights", "downloading weights"
   - Detects: Model weight download completion (if needed)

4. WEIGHTS_LOADED (Weight Loading Complete)
   - Patterns: "loading weights took", "loading safetensors checkpoint shards: 100%"
   - Detects: Model weights fully loaded into memory

5. MODEL_LOADED (Model Fully Loaded)
   - Patterns: "model loading took", "init engine", "engine.*took.*seconds"
   - Detects: Complete model initialization and engine setup

6. GRAPH_CAPTURE (CUDA Graph Optimization)
   - Patterns: "graph capturing finished", "capturing cuda graph shapes: 100%"
   - Detects: CUDA graph capture completion for optimization

7. SERVER_LOG_READY (Server Log Ready)
   - Patterns: "started server process"
   - Detects: FastAPI/Uvicorn server process started (log-based)

8. SERVER_READY (Server Ready)
   - Tested via HTTP requests to /health endpoint with 0.1s polling
   - Detects: API actually responding with valid HTTP 200 responses

MONITORING BEHAVIOR:
===================
- Timeout: 20 minutes (model loading can be slow)
- Container Status: Monitors container health during startup
- Health Polling: Polls /health endpoint every 0.1 seconds after first log
- Success Criteria: HTTP 200 response from health endpoint
- Port: Maps container port 8000 to specified local port
- Stop Condition: Immediately after health endpoint returns 200

EXAMPLE LOG FLOW:
================
[15.230s] initializing a v1 llm engine → engine_init
[45.120s] starting to load model → model_loading
[67.340s] downloading weights → weights_download
[156.780s] loading weights took 89.44s → weights_loaded
[198.450s] model loading took 153.33s → model_loaded
[245.670s] graph capturing finished → graph_capture
[318.429s] started server process → server_log_ready
[318.435s] HTTP 200 /health → server_ready
"""

import requests
import json
import time
from typing import Dict, Optional
from benchmark_base import BenchmarkBase


class VLLMBenchmark(BenchmarkBase):
    def __init__(self, image: str = "", container_name: str = "vllm-timing-test", 
                 snapshotter: str = "nydus", port: int = 8080):
        super().__init__(image, container_name, snapshotter, port)
    
    def get_health_endpoint(self) -> str:
        """Get health endpoint for vLLM application."""
        return "health"
    
    def supports_health_polling(self) -> bool:
        """vLLM application supports health endpoint polling."""
        return True
    
    def _should_stop_monitoring(self, elapsed: float) -> bool:
        """Custom stop monitoring logic for vLLM."""
        # Use base class logic for health polling apps
        return super()._should_stop_monitoring(elapsed)
    
    def _is_successful(self, results: Dict[str, Optional[float]]) -> bool:
        """Determine if benchmark was successful."""
        return results.get("server_ready") is not None
    
    def _init_phases(self) -> None:
        """Initialize the phases dictionary for vLLM."""
        self.phases = {
            "first_log": None,
            "engine_init": None,
            "weights_download": None,
            "weights_download_complete": None,
            "weights_loaded": None,
            "graph_capture": None,
            "server_log_ready": None,
            "server_ready": None
        }

    def analyze_log_line(self, line: str, timestamp: float) -> Optional[str]:
        """Analyze a log line and return detected phase."""
        elapsed = timestamp - self.start_time
        line_lower = line.lower()
        
        # Engine initialization (vLLM V1 engine)
        if self.phases["engine_init"] is None:
            if any(pattern in line_lower for pattern in [
                "initializing a v1 llm engine", "waiting for init message", "v1 llm engine"
            ]):
                self.phases["engine_init"] = elapsed
                return "engine_init"
        
        # Weights download start (was model loading start)
        if self.phases["weights_download"] is None:
            if any(pattern in line_lower for pattern in [
                "starting to load model", "loading model from scratch"
            ]):
                self.phases["weights_download"] = elapsed
                return "weights_download"
        
        # Weights download complete
        if self.phases["weights_download_complete"] is None:
            if any(pattern in line_lower for pattern in [
                "time spent downloading weights", "downloading weights"
            ]):
                self.phases["weights_download_complete"] = elapsed
                return "weights_download_complete"
        
        # Weights loaded patterns
        if self.phases["weights_loaded"] is None:
            if any(pattern in line_lower for pattern in [
                "loading weights took", "loading safetensors checkpoint shards: 100%"
            ]):
                self.phases["weights_loaded"] = elapsed
                return "weights_loaded"
        
        # CUDA graph capture
        if self.phases["graph_capture"] is None:
            if any(pattern in line_lower for pattern in [
                "graph capturing finished", "capturing cuda graph shapes: 100%"
            ]):
                self.phases["graph_capture"] = elapsed
                return "graph_capture"
        
        # Server log ready pattern (vLLM/FastAPI specific)
        if self.phases["server_log_ready"] is None:
            if "started server process" in line_lower:
                self.phases["server_log_ready"] = elapsed
                return "server_log_ready"
        
        return None

    def test_api_readiness(self, timeout: int = 120) -> bool:
        """vLLM benchmark uses health polling instead of direct API test."""
        print("Using health polling instead of direct API test")
        return True

    def get_default_image(self, snapshotter: str) -> str:
        """Get default image for the snapshotter. Users should now use --repo parameter instead."""
        raise ValueError(
            "No default image configured. Please specify either:\n"
            "  --repo <ecr-repo-name> (e.g., --repo my-vllm-app)\n"
            "  --image <full-image-url> (e.g., --image registry.com/repo:tag)\n"
            "\nExample: python test-bench-vllm.py --repo saurabh-vllm-test --tag latest --snapshotter nydus"
        )

    def _get_summary_items(self, total_time):
        """Get summary items for the timing summary."""
        items = [
            ("Container Startup Time:", self.container_startup_duration),
            ("Container to First Log:", self.phases["first_log"]),
            ("Engine Initialization:", self.phases["engine_init"]),
            ("Weights Download Start:", self.phases["weights_download"]),
            ("Weights Download Complete:", self.phases["weights_download_complete"]),
            ("Weights Loaded:", self.phases["weights_loaded"]),
            ("Graph Capture Complete:", self.phases["graph_capture"]),
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


if __name__ == "__main__":
    import sys
    
    benchmark = VLLMBenchmark()
    sys.exit(benchmark.main("vLLM Container Startup Benchmark"))