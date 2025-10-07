"""
Benchmarking utilities for fastpull run command.

Tracks container lifecycle events and readiness checks.
"""

import json
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional, Dict
from urllib.request import urlopen
from urllib.error import URLError, HTTPError


class ContainerBenchmark:
    """Track container startup and readiness metrics."""

    def __init__(self, container_id: str, benchmark_mode: str = 'none',
                 readiness_endpoint: Optional[str] = None, mode: str = 'normal'):
        """
        Initialize benchmark tracker.

        Args:
            container_id: Container ID to track
            benchmark_mode: 'none', 'completion', or 'readiness'
            readiness_endpoint: HTTP endpoint for readiness checks
            mode: 'nydus' or 'normal' (for display purposes)
        """
        self.container_id = container_id
        self.benchmark_mode = benchmark_mode
        self.readiness_endpoint = readiness_endpoint
        self.mode = mode
        self.metrics: Dict[str, float] = {}
        self.start_time = time.time()
        self._event_thread: Optional[threading.Thread] = None
        self._container_started = False

    def start_event_monitoring(self):
        """Start monitoring containerd events in background thread."""
        if self.benchmark_mode == 'none':
            return

        def monitor_events():
            """Monitor ctr events for container lifecycle."""
            try:
                # Run sudo ctr events and parse for our container
                proc = subprocess.Popen(
                    ['sudo', 'ctr', 'events'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

                for line in proc.stdout:
                    # Look for /tasks/start event (check any task since we're the only one running)
                    if '/tasks/start' in line and self.metrics.get('container_start_time') is None:
                        elapsed = time.time() - self.start_time
                        self.metrics['container_start_time'] = elapsed
                        self._container_started = True
                        print(f"[{elapsed:.3f}s] ✓ CONTAINER START")

                    # Look for our specific container's exit event
                    if self.container_id in line and '/tasks/exit' in line and self.benchmark_mode == 'completion':
                        elapsed = time.time() - self.start_time
                        self.metrics['completion_time'] = elapsed
                        print(f"[{elapsed:.3f}s] ✓ CONTAINER EXIT")
                        break

            except Exception as e:
                print(f"Event monitoring error: {e}")

        self._event_thread = threading.Thread(target=monitor_events, daemon=True)
        self._event_thread.start()

    def wait_for_readiness(self, timeout: int = 600, poll_interval: int = 2):
        """
        Poll readiness endpoint until HTTP 200 response.

        Args:
            timeout: Maximum time to wait in seconds
            poll_interval: Time between polls in seconds

        Returns:
            True if endpoint became ready, False if timeout
        """
        if self.benchmark_mode != 'readiness' or not self.readiness_endpoint:
            return True

        # Ensure endpoint has protocol prefix
        endpoint = self.readiness_endpoint
        if not endpoint.startswith(('http://', 'https://')):
            endpoint = f'http://{endpoint}'

        print(f"Polling {endpoint} for readiness...")
        end_time = time.time() + timeout

        while time.time() < end_time:
            try:
                response = urlopen(endpoint, timeout=5)
                if response.getcode() == 200:
                    elapsed = time.time() - self.start_time
                    self.metrics['readiness_time'] = elapsed
                    print(f"Container ready (HTTP 200): {elapsed:.2f}s")
                    return True
            except (URLError, HTTPError):
                pass

            time.sleep(poll_interval)

        print(f"Readiness check timeout after {timeout}s")
        return False

    def wait_for_completion(self, timeout: int = 3600):
        """
        Wait for container to exit.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if container exited, False if timeout
        """
        if self.benchmark_mode != 'completion':
            return True

        print(f"Waiting for container completion...")
        end_time = time.time() + timeout

        while time.time() < end_time:
            # Check if container is still running
            result = subprocess.run(
                ['nerdctl', 'ps', '-q', '-f', f'id={self.container_id}'],
                capture_output=True,
                text=True
            )

            if not result.stdout.strip():
                # Container has exited
                if 'completion_time' not in self.metrics:
                    elapsed = time.time() - self.start_time
                    self.metrics['completion_time'] = elapsed
                print(f"Container completed")
                return True

            time.sleep(1)

        print(f"Completion timeout after {timeout}s")
        return False

    def print_summary(self):
        """Print benchmark results summary."""
        if self.benchmark_mode == 'none':
            return

        mode_label = "FASTPULL" if self.mode == 'nydus' else "NORMAL"
        print("\n" + "="*50)
        print(f"{mode_label} BENCHMARK SUMMARY")
        print("="*50)

        if 'container_start_time' in self.metrics:
            print(f"Time to Container Start: {self.metrics['container_start_time']:.3f}s")

        if 'readiness_time' in self.metrics:
            print(f"Time to Readiness:       {self.metrics['readiness_time']:.3f}s")

        if 'completion_time' in self.metrics:
            print(f"Time to Completion:      {self.metrics['completion_time']:.3f}s")

        total_time = time.time() - self.start_time
        print(f"Total Elapsed Time:      {total_time:.3f}s")
        print("="*50 + "\n")

    def export_json(self, filepath: str):
        """
        Export metrics to JSON file.

        Args:
            filepath: Path to output JSON file
        """
        output = {
            'container_id': self.container_id,
            'benchmark_mode': self.benchmark_mode,
            'metrics': self.metrics,
            'timestamp': datetime.now().isoformat()
        }

        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"Metrics exported to {filepath}")
