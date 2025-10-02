#!/usr/bin/env python3
"""
TensorRT-LLM Startup Timing Benchmark
Measures container startup and TensorRT-LLM readiness times with different snapshotters.

LOG PATTERN DETECTION & PHASES:
===============================

This benchmark monitors TensorRT-LLM server logs and detects the following phases:

1. ENGINE_INIT (TensorRT-LLM Engine Initialization)
   - Patterns: "PyTorchConfig(", "TensorRT-LLM version", "KV cache quantization"
   - Detects: TensorRT-LLM engine initialization and configuration

2. WEIGHT_DOWNLOAD_START (Weight Download Start)
   - Patterns: "Prefetching", "checkpoint files", "Use.*GB for model weights"
   - Detects: Beginning of model weight download/prefetching to memory

3. WEIGHT_DOWNLOAD_COMPLETE (Weight Download Complete)
   - Patterns: "Loading /workspace/huggingface", first model loading line
   - Detects: All model weights downloaded and loading starts

4. WEIGHTS_LOADED (Weight Loading Complete)
   - Patterns: "Loading weights: 100%", "Model init total"
   - Detects: Model weights fully loaded into memory

5. MODEL_LOADED (Model Fully Loaded)
   - Patterns: "Autotuning process ends", "Autotuner Cache size", memory configuration
   - Detects: Complete model initialization with autotuning and optimization

6. SERVER_LOG_READY (Server Log Ready)
   - Patterns: "Started server process", "Waiting for application startup"
   - Detects: Uvicorn/FastAPI server initialization (log-based)

7. SERVER_READY (Server Ready)
   - Tested via HTTP requests to /health endpoint with 0.1s polling
   - Detects: API actually responding with valid HTTP 200 responses

MONITORING BEHAVIOR:
===================
- Timeout: 25 minutes (model loading and autotuning can be very slow)
- Container Status: Monitors container health during startup
- Health Polling: Polls /health endpoint every 0.1 seconds after first log
- Success Criteria: HTTP 200 response from health endpoint
- Port: Maps container port 8000 to specified local port
- Stop Condition: Immediately after health endpoint returns 200

EXAMPLE LOG FLOW:
================
[10.230s] Starting TensorRT-LLM server → first_log
[73.120s] PyTorchConfig( → engine_init
[76.780s] Prefetching 15.26GB checkpoint → weight_download_start
[130.450s] Loading /workspace/huggingface → weight_download_complete
[156.670s] Loading weights: 100% → weights_loaded
[324.456s] Autotuning process ends → model_loaded
[325.789s] Started server process → server_log_ready
[326.012s] HTTP 200 /health → server_ready
"""

import requests
import json
import time
from typing import Dict, Optional
from benchmark_base import BenchmarkBase


class TensorRTBenchmark(BenchmarkBase):
    def __init__(self, image: str = "", container_name: str = "tensorrt-timing-test", 
                 snapshotter: str = "nydus", port: int = 8080):
        super().__init__(image, container_name, snapshotter, port)
    
    def get_health_endpoint(self) -> str:
        """Get health endpoint for TensorRT application."""
        return "health"
    
    def supports_health_polling(self) -> bool:
        """TensorRT application supports health endpoint polling."""
        return True
    
    def _should_stop_monitoring(self, elapsed: float) -> bool:
        """Custom stop monitoring logic for TensorRT-LLM."""
        # Use base class logic for health polling apps
        return super()._should_stop_monitoring(elapsed)
    
    def _is_successful(self, results: Dict[str, Optional[float]]) -> bool:
        """Determine if benchmark was successful."""
        return results.get("server_ready") is not None
    
    def _init_phases(self) -> None:
        """Initialize the phases dictionary for TensorRT-LLM."""
        self.phases = {
            "first_log": None,
            "engine_init": None,
            "weight_download_start": None,
            "weight_download_complete": None,
            "weights_loaded": None,
            "model_loaded": None,
            "server_log_ready": None,
            "server_ready": None
        }

    def analyze_log_line(self, line: str, timestamp: float) -> Optional[str]:
        """Analyze a log line and return detected phase."""
        elapsed = timestamp - self.start_time
        line_lower = line.lower()
        
        # TensorRT-LLM engine initialization
        if self.phases["engine_init"] is None:
            if any(pattern in line_lower for pattern in [
                "pytorchconfig(", "tensorrt-llm version", "kv cache quantization"
            ]):
                self.phases["engine_init"] = elapsed
                return "engine_init"
        
        # Weight download start
        if self.phases["weight_download_start"] is None:
            if any(pattern in line_lower for pattern in [
                "prefetching", "checkpoint files", "gb for model weights"
            ]):
                self.phases["weight_download_start"] = elapsed
                return "weight_download_start"
        
        # Weight download complete and loading starts
        if self.phases["weight_download_complete"] is None:
            if any(pattern in line_lower for pattern in [
                "loading /workspace/huggingface"
            ]):
                self.phases["weight_download_complete"] = elapsed
                return "weight_download_complete"
        
        # Weights loading complete
        if self.phases["weights_loaded"] is None:
            if any(pattern in line_lower for pattern in [
                "loading weights: 100%", "model init total"
            ]):
                self.phases["weights_loaded"] = elapsed
                return "weights_loaded"
        
        # Model fully loaded (autotuning complete, memory configured)
        if self.phases["model_loaded"] is None:
            if any(pattern in line_lower for pattern in [
                "autotuning process ends", "autotuner cache size", 
                "max_seq_len=", "max_num_requests=", "allocated.*gib for max tokens"
            ]):
                self.phases["model_loaded"] = elapsed
                return "model_loaded"
        
        # Server log ready pattern
        if self.phases["server_log_ready"] is None:
            if any(pattern in line_lower for pattern in [
                "started server process", "waiting for application startup"
            ]):
                self.phases["server_log_ready"] = elapsed
                return "server_log_ready"
        
        return None

    def test_api_readiness(self, timeout: int = 120) -> bool:
        """TensorRT benchmark doesn't test API readiness - stops after server ready."""
        print("Skipping API readiness test - stopping after server ready detection")
        return True

    def get_default_image(self, snapshotter: str) -> str:
        """Get default image for the snapshotter. Users should now use --repo parameter instead."""
        raise ValueError(
            "No default image configured. Please specify either:\n"
            "  --repo <ecr-repo-name> (e.g., --repo my-tensorrt-app)\n"
            "  --image <full-image-url> (e.g., --image registry.com/repo:tag)\n"
            "\nExample: python test-bench-tensorrt.py --repo my-tensorrt-app --tag latest --snapshotter nydus"
        )

    def _get_summary_items(self, total_time):
        """Get summary items for the timing summary."""
        items = [
            ("Container Startup Time:", self.container_startup_duration),
            ("Container to First Log:", self.phases["first_log"]),
            ("Engine Initialization:", self.phases["engine_init"]),
            ("Weight Download Start:", self.phases["weight_download_start"]),
            ("Weight Download Complete:", self.phases["weight_download_complete"]),
            ("Weights Loaded:", self.phases["weights_loaded"]),
            ("Model Loaded:", self.phases["model_loaded"]),
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
        
        if self.phases["first_log"] is not None and self.phases["weight_download_start"] is not None:
            first_to_download = self.phases["weight_download_start"] - self.phases["first_log"]
            items.append(("First Log to Weight Download Start:", first_to_download))
        
        if self.phases["weight_download_start"] is not None and self.phases["weight_download_complete"] is not None:
            download_duration = self.phases["weight_download_complete"] - self.phases["weight_download_start"]
            items.append(("Weight Download Start to Complete:", download_duration))
        
        if self.phases["weight_download_complete"] is not None and self.phases["weights_loaded"] is not None:
            download_to_loaded = self.phases["weights_loaded"] - self.phases["weight_download_complete"]
            items.append(("Weight Download Complete to Weights Loaded:", download_to_loaded))
        
        if self.phases["weights_loaded"] is not None and self.phases["server_ready"] is not None:
            loaded_to_ready = self.phases["server_ready"] - self.phases["weights_loaded"]
            items.append(("Weights Loaded to Server Ready:", loaded_to_ready))
        
        return items


if __name__ == "__main__":
    import sys
    
    benchmark = TensorRTBenchmark()
    sys.exit(benchmark.main("TensorRT-LLM Container Startup Benchmark"))