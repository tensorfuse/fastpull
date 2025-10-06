#!/usr/bin/env python3
"""
Generic Benchmark Framework Base Class
Provides common functionality for all ML application benchmarks.
"""

import argparse
import json
import os
import queue
import re
import requests
import signal
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


def run_command(cmd, check=True, capture_output=False):
    """Run a shell command and handle errors."""
    try:
        if capture_output:
            result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, shell=True, check=check)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        print(f"Error: {e}")
        if capture_output and e.stdout:
            print(f"Stdout: {e.stdout}")
        if capture_output and e.stderr:
            print(f"Stderr: {e.stderr}")
        raise


def check_aws_credentials():
    """Check if AWS credentials are configured."""
    try:
        run_command("aws sts get-caller-identity", capture_output=True)
        print("✓ AWS credentials are configured")
        return True
    except:
        print("Warning: AWS credentials not configured. Please run 'aws configure' first.")
        return False


def docker_login_ecr(account=None, region="us-east-1"):
    """Login to ECR using both docker and nerdctl."""
    print("Checking AWS credentials and logging into ECR...")

    if not check_aws_credentials():
        print("Skipping ECR login due to missing AWS credentials")
        return False

    if not account:
        # Try to get account from AWS STS
        try:
            account_info = run_command("aws sts get-caller-identity --query Account --output text", capture_output=True)
            account = account_info.strip()
            print(f"Auto-detected AWS account: {account}")
        except:
            print("Could not auto-detect AWS account ID")
            return False

    try:
        password = run_command(f"aws ecr get-login-password --region {region}", capture_output=True)
        registry = f"{account}.dkr.ecr.{region}.amazonaws.com"

        # Login with nerdctl
        login_cmd = f"echo '{password}' | nerdctl login -u AWS --password-stdin {registry}"
        run_command(login_cmd, check=False)

        # Login with sudo nerdctl
        login_cmd = f"echo '{password}' | sudo nerdctl login -u AWS --password-stdin {registry}"
        run_command(login_cmd, check=False)

        print("✓ Successfully logged into ECR")
        return True

    except Exception as e:
        print(f"Warning: Could not login to ECR: {e}")
        return False


def docker_login_gar(location="us-central1"):
    """Login to Google Artifact Registry using both docker and nerdctl."""
    print("Checking gcloud credentials and logging into Google Artifact Registry...")

    try:
        # Check if gcloud is configured
        run_command("gcloud config get-value project", capture_output=True)
    except:
        print("Warning: gcloud not configured. Please run 'gcloud auth login' first.")
        return False

    try:
        registry = f"{location}-docker.pkg.dev"

        # Get access token from gcloud
        password = run_command("gcloud auth print-access-token", capture_output=True)

        # Login with nerdctl
        login_cmd = f"echo '{password}' | nerdctl login -u oauth2accesstoken --password-stdin https://{registry}"
        run_command(login_cmd, check=False)

        # Login with sudo nerdctl
        login_cmd = f"echo '{password}' | sudo nerdctl login -u oauth2accesstoken --password-stdin https://{registry}"
        run_command(login_cmd, check=False)

        print("✓ Successfully logged into Google Artifact Registry")
        return True

    except Exception as e:
        print(f"Warning: Could not login to Google Artifact Registry: {e}")
        return False


def construct_ecr_image(repo: str, tag: str, snapshotter: str, region: str = "us-east-1") -> str:
    """Construct ECR image URL from repo, tag, and snapshotter."""
    try:
        # Get AWS account ID
        account_info = run_command("aws sts get-caller-identity --query Account --output text", capture_output=True)
        account = account_info.strip()
        
        # Add snapshotter suffix to tag (except for overlayfs/native which use base tag)
        if snapshotter in ["overlayfs", "native"]:
            final_tag = tag
        else:
            final_tag = f"{tag}-{snapshotter}"
        
        return f"{account}.dkr.ecr.{region}.amazonaws.com/{repo}:{final_tag}"
        
    except Exception as e:
        raise ValueError(f"Could not construct ECR image URL: {e}. Ensure AWS credentials are configured.")


class BenchmarkBase(ABC):
    """Abstract base class for all benchmarks."""
    
    def __init__(self, image: str, container_name: str, snapshotter: str = "nydus", port: int = 8080, model_mount_path: str = None):
        self.image = image
        self.container_name = container_name
        self.snapshotter = snapshotter
        self.port = port
        self.model_mount_path = model_mount_path
        self.start_time = None
        self.phases = {}
        self.log_queue = queue.Queue()
        self.should_stop = threading.Event()
        
        # Container events monitoring
        self.ctr_events_queue = queue.Queue()
        self.ctr_events_thread = None
        self.container_create_time = None
        self.container_start_time = None
        self.container_startup_duration = None
        
        # Health endpoint polling
        self.health_thread = None
        self.health_ready_time = None
        self.health_ready_event = threading.Event()
        self.interrupted = False
        
        # Initialize phases from subclass
        self._init_phases()
    
    @abstractmethod
    def _init_phases(self) -> None:
        """Initialize the phases dictionary for the specific application."""
        pass
    
    @abstractmethod
    def analyze_log_line(self, line: str, timestamp: float) -> Optional[str]:
        """Analyze a log line and return detected phase. Must be implemented by subclass."""
        pass
    
    
    @abstractmethod
    def get_default_image(self, snapshotter: str) -> str:
        """Get default image for the snapshotter. Must be implemented by subclass."""
        pass
    
    def get_health_endpoint(self) -> Optional[str]:
        """Get health endpoint for the application. Override in subclasses."""
        return None
    
    def supports_health_polling(self) -> bool:
        """Check if this application supports health endpoint polling. Override in subclasses."""
        return False
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time since start in seconds."""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time
    
    def start_ctr_events_monitor(self):
        """Start monitoring containerd events in a separate thread."""
        def monitor_events():
            try:
                cmd = ["sudo", "ctr", "events"]
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                while not self.should_stop.is_set():
                    line = process.stdout.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        time.sleep(0.1)
                        continue
                    
                    self.ctr_events_queue.put((time.time(), line.strip()))
                
                process.terminate()
                process.wait()
                
            except Exception as e:
                print(f"Error monitoring ctr events: {e}")
        
        self.ctr_events_thread = threading.Thread(target=monitor_events, daemon=True)
        self.ctr_events_thread.start()
        return self.ctr_events_thread
    
    def process_ctr_events(self):
        """Process containerd events to track container lifecycle timing."""
        while not self.should_stop.is_set():
            try:
                timestamp, line = self.ctr_events_queue.get(timeout=1.0)
                
                # Parse containerd event line
                # Format: TIMESTAMP NAMESPACE EVENT_TYPE DATA
                parts = line.split(' ', 3)
                if len(parts) < 4:
                    continue
                
                event_timestamp_str = f"{parts[0]} {parts[1]}"
                namespace = parts[2]
                event_type = parts[3]
                
                # Parse the event timestamp
                try:
                    # Remove timezone info for parsing, then add it back
                    ts_clean = event_timestamp_str.replace(" +0000 UTC", "")
                    event_time = datetime.fromisoformat(ts_clean.replace(' ', 'T'))
                    event_time = event_time.replace(tzinfo=timezone.utc)
                    event_timestamp = event_time.timestamp()
                except:
                    event_timestamp = timestamp  # Fallback to capture time
                
                # Look for task start event (any task since only one container is running)
                if "/tasks/start" in event_type and self.container_start_time is None:
                    self.container_start_time = event_timestamp
                    if self.container_create_time:
                        self.container_startup_duration = self.container_start_time - self.container_create_time
                        elapsed = event_timestamp - self.start_time if self.start_time else 0
                        print(f"[{elapsed:.3f}s] ✓ CONTAINER START (startup: {self.container_startup_duration:.3f}s)")
                        break  # We found what we needed - stop monitoring
                        
            except queue.Empty:
                continue
            except KeyboardInterrupt:
                break
    
    def cleanup_container(self):
        """Remove any existing container with the same name."""
        try:
            nerdctl_snapshotter = self.get_nerdctl_snapshotter()
            cmd = ["sudo", "nerdctl", "--snapshotter", nerdctl_snapshotter, "rm", "-f", self.container_name]
            subprocess.run(cmd, capture_output=True, check=False)
        except Exception as e:
            print(f"Warning: Could not cleanup container: {e}")
    
    def start_container(self) -> bool:
        """Start the container and return success status."""
        try:
            # Start ctr events monitoring before container creation
            print("Starting containerd events monitoring...")
            self.start_ctr_events_monitor()
            
            # Start processing events in background
            events_thread = threading.Thread(target=self.process_ctr_events, daemon=True)
            events_thread.start()
            
            # Small delay to ensure events monitoring is ready
            time.sleep(0.5)
            
            nerdctl_snapshotter = self.get_nerdctl_snapshotter()
            cmd = [
                "sudo", "nerdctl", "--snapshotter", nerdctl_snapshotter, "run",
                "--name", self.container_name,
                "--gpus", "all",
                "--detach",
                "--publish", f"{self.port}:8000"
            ]
            
            # Add volume mounts if model mount path is provided
            if self.model_mount_path:
                cmd.extend([
                    "--volume", f"{self.model_mount_path}/huggingface:/workspace/huggingface",
                    "--volume", f"{self.model_mount_path}/hf-xet-cache:/workspace/hf-xet-cache"
                ])
            
            cmd.append(self.image)
            
            print(f"Running command: {' '.join(cmd)}")
            # Set container creation time just before running nerdctl command
            self.container_create_time = time.time()
            if self.start_time is not None:
                elapsed = self.container_create_time - self.start_time
                print(f"[{elapsed:.3f}s] ✓ CONTAINER CREATE (nerdctl run started)")
            else:
                print("No start time is set")
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Error starting container: {e}")
            print(f"STDERR: {e.stderr}")
            return False
    
    def monitor_logs(self):
        """Monitor container logs in a separate thread."""
        def log_reader():
            try:
                cmd = ["sudo", "nerdctl", "--snapshotter", self.snapshotter, "logs", "-f", self.container_name]
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                while not self.should_stop.is_set():
                    line = process.stdout.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        time.sleep(0.1)
                        continue
                    
                    self.log_queue.put((time.time(), line.strip()))
                
                process.terminate()
                
            except Exception as e:
                print(f"Error monitoring logs: {e}")
        
        log_thread = threading.Thread(target=log_reader, daemon=True)
        log_thread.start()
        return log_thread
    
    def start_health_polling(self):
        """Start health endpoint polling in a separate thread."""
        if not self.supports_health_polling():
            return None
            
        def health_poller():
            endpoint = self.get_health_endpoint()
            if not endpoint:
                return
                
            url = f"http://localhost:{self.port}/{endpoint}"
            print(f"Starting health polling for endpoint: {url}")
            
            # Poll with 0.1 second intervals, timeout after 20 minutes
            start_time = time.time()
            timeout = 20 * 60  # 20 minutes
            
            while not self.should_stop.is_set() and not self.health_ready_event.is_set():
                if time.time() - start_time > timeout:
                    print(f"Health polling timed out after {timeout}s")
                    break
                    
                # Check for interrupt
                if self.interrupted:
                    print("Health polling interrupted by user")
                    break
                    
                try:
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        self.health_ready_time = time.time() - self.start_time
                        elapsed = self.health_ready_time
                        print(f"[{elapsed:.3f}s] ✓ SERVER READY (HTTP 200)")
                        
                        # Set server ready time from health check
                        self.phases["server_ready"] = self.health_ready_time
                        self.health_ready_event.set()
                        break
                        
                except requests.exceptions.RequestException:
                    # Connection failed, server not ready yet
                    pass
                
                time.sleep(0.1)  # Wait 0.1 seconds before next poll
        
        self.health_thread = threading.Thread(target=health_poller, daemon=True)
        self.health_thread.start()
        return self.health_thread
    
    def process_logs(self, timeout: int = 1200):
        """Process logs and detect phases."""
        print("Monitoring container logs...")
        log_thread = self.monitor_logs()
        
        # Start health polling if supported
        health_thread = None
        
        start_monitoring = time.time()
        
        while time.time() - start_monitoring < timeout:
            try:
                timestamp, line = self.log_queue.get(timeout=1.0)
                elapsed = timestamp - self.start_time
                
                # Detect first log
                if "first_log" in self.phases and self.phases["first_log"] is None:
                    self.phases["first_log"] = elapsed
                    print(f"[{elapsed:.3f}s] ✓ FIRST LOG")
                    
                    # Start health polling after first log if supported
                    if self.supports_health_polling() and not health_thread:
                        health_thread = self.start_health_polling()
                
                phase = self.analyze_log_line(line, timestamp)
                
                if phase:
                    print(f"[{elapsed:.3f}s] ✓ {phase.upper().replace('_', ' ')}")
                
                print(f"[{elapsed:.3f}s] {line}")
                
                # Check if we should stop monitoring
                if self._should_stop_monitoring(elapsed):
                    break
                    
            except queue.Empty:
                # Check if we should stop monitoring even when no new logs
                elapsed = time.time() - self.start_time
                if self._should_stop_monitoring(elapsed):
                    break
                continue
            except KeyboardInterrupt:
                print("\nReceived interrupt signal...")
                break
        
        self.should_stop.set()
    
    def _should_stop_monitoring(self, elapsed: float) -> bool:
        """Determine if we should stop monitoring logs. Should be overridden by subclasses."""
        # For applications that support health polling, stop only after health check succeeds
        if self.supports_health_polling():
            return self.health_ready_event.is_set()
        return False
    
    
    def stop_container(self):
        """Stop and remove the container. Wait for health check or timeout first."""
        try:
            # For applications that support health polling, wait for health check or timeout
            # But skip waiting if interrupted by user
            if (self.supports_health_polling() and not self.health_ready_event.is_set() 
                and not self.interrupted):
                print("Waiting for health check success or timeout before stopping container...")
                timeout = 20 * 60  # 20 minutes
                if self.health_ready_event.wait(timeout):
                    if not self.interrupted:
                        print("Health check succeeded, proceeding with container stop")
                    else:
                        print("Interrupted during health check, proceeding with container stop")
                else:
                    print("Health check timed out, proceeding with container stop")
            elif self.interrupted:
                print("Skipping health check wait due to interrupt, proceeding with container stop")
            
            self.should_stop.set()
            # Stop the container
            cmd_stop = ["sudo", "nerdctl", "--snapshotter", self.snapshotter, "stop", self.container_name]
            subprocess.run(cmd_stop, capture_output=True, check=False, timeout=30)
            
            # Wait for container to fully stop
            time.sleep(2)
            
            # Remove the container
            cmd_rm = ["sudo", "nerdctl", "--snapshotter", self.snapshotter, "rm", self.container_name]
            subprocess.run(cmd_rm, capture_output=True, check=False, timeout=60)
            
            # Wait a moment for the container removal to be fully processed
            time.sleep(2)
            
        except Exception as e:
            print(f"Warning: Could not stop/remove container cleanly: {e}")
    
    def get_nerdctl_snapshotter(self) -> str:
        """Get the correct snapshotter name for nerdctl commands."""
        # Map estargz to stargz for nerdctl compatibility
        if self.snapshotter == "estargz":
            return "stargz"
        return self.snapshotter

    def cleanup_soci_snapshotter(self):
        """Perform SOCI-specific cleanup: remove state directory and restart service."""
        if self.snapshotter != "soci":
            return
            
        try:
            print("Performing SOCI-specific cleanup...")
            
            # Remove SOCI state directory
            print("Removing SOCI state directory...")
            cmd_rm = ["sudo", "rm", "-rf", "/var/lib/soci-snapshotter-grpc/"]
            result = subprocess.run(cmd_rm, capture_output=True, text=True, check=False, timeout=30)
            
            if result.returncode == 0:
                print("SOCI state directory removed successfully")
            else:
                print(f"Warning: Could not remove SOCI state directory: {result.stderr}")
            
            # Restart SOCI snapshotter service
            print("Restarting SOCI snapshotter service...")
            cmd_restart = ["sudo", "systemctl", "restart", "soci-snapshotter-grpc.service"]
            result = subprocess.run(cmd_restart, capture_output=True, text=True, check=False, timeout=30)
            
            if result.returncode == 0:
                print("SOCI snapshotter service restarted successfully")
                # Give the service a moment to start
                time.sleep(2)
            else:
                print(f"Warning: Could not restart SOCI snapshotter service: {result.stderr}")
                
        except Exception as e:
            print(f"Warning: Could not perform SOCI cleanup: {e}")

    def cleanup_images(self):
        """Remove the image to ensure fresh pulls for testing."""
        try:
            print(f"Removing image {self.image} for clean testing...")
            
            nerdctl_snapshotter = self.get_nerdctl_snapshotter()
            
            # First, try with image name/tag
            cmd_rmi = ["sudo", "nerdctl", "--snapshotter", nerdctl_snapshotter, "rmi", self.image]
            result = subprocess.run(cmd_rmi, capture_output=True, text=True, check=False, timeout=60)
            
            if result.returncode == 0:
                print("Image removed successfully")
                return
            
            # If that fails, get the image ID and try with that
            print("Trying to remove by image ID...")
            cmd_images = ["sudo", "nerdctl", "--snapshotter", nerdctl_snapshotter, "images", "--format", "{{.ID}}", self.image]
            images_result = subprocess.run(cmd_images, capture_output=True, text=True, check=False, timeout=30)
            
            if images_result.returncode == 0 and images_result.stdout.strip():
                image_id = images_result.stdout.strip().split('\n')[0]
                cmd_rmi_id = ["sudo", "nerdctl", "--snapshotter", nerdctl_snapshotter, "rmi", image_id]
                id_result = subprocess.run(cmd_rmi_id, capture_output=True, text=True, check=False, timeout=60)
                
                if id_result.returncode == 0:
                    print(f"Image removed successfully using ID: {image_id}")
                else:
                    print(f"Could not remove image by ID: {id_result.stderr}")
            else:
                print(f"Note: Could not find or remove image: {result.stderr}")
                
        except Exception as e:
            print(f"Warning: Could not remove image: {e}")
    
    def print_summary(self, total_time: float):
        """Print timing summary."""
        print("\n" + "="*50)
        print(f"{self.__class__.__name__.replace('Benchmark', '').upper()} TIMING SUMMARY")
        print("="*50)
        
        for label, value in self._get_summary_items(total_time):
            if label == "":
                print()  # Empty line
            elif label.endswith(":") and value is None:
                print(label)  # Section header
            elif value is not None:
                print(f"{label:<30} {value:.3f}s")
            else:
                print(f"{label:<30} N/A")
        
        print("="*50)
    
    def _get_summary_items(self, total_time: float) -> List[Tuple[str, Optional[float]]]:
        """Get summary items for printing. Must be overridden by subclasses."""
        items = []
        
        # Add container startup time at the beginning
        items.append(("Container Startup Time:", self.container_startup_duration))
        
        for phase_key, phase_value in self.phases.items():
            label = phase_key.replace('_', ' ').title() + ":"
            items.append((label, phase_value))
        items.append(("Total Test Time:", total_time))
        return items
    
    def run_benchmark(self) -> Dict[str, Optional[float]]:
        """Run the complete benchmark."""
        app_name = self.__class__.__name__.replace('Benchmark', '')
        print(f"=== {app_name} Startup Timing Test ===")
        print(f"Image: {self.image}")
        print(f"Snapshotter: {self.snapshotter}")
        print(f"Port: {self.port}")
        print()
        
        # Check credentials and login to registry if needed
        if ".ecr." in self.image:
            print("ECR image detected, attempting AWS login...")
            # Extract region from image URL if possible, otherwise use default
            region = "us-east-1"  # Default region
            if hasattr(self, '_region'):
                region = self._region
            docker_login_ecr(region=region)
        elif ".pkg.dev" in self.image:
            print("Google Artifact Registry image detected, attempting gcloud login...")
            # Extract location from image URL if possible, otherwise use default
            location = "us-central1"  # Default location
            if hasattr(self, '_location'):
                location = self._location
            else:
                # Try to parse location from image URL (format: location-docker.pkg.dev)
                import re
                match = re.search(r'([a-z]+-[a-z]+\d+)-docker\.pkg\.dev', self.image)
                if match:
                    location = match.group(1)
            docker_login_gar(location=location)
        
        # Cleanup
        print("Cleaning up existing containers...")
        self.cleanup_container()
        self.cleanup_soci_snapshotter()
        
        # Start timing
        self.start_time = time.time()
        start_datetime = datetime.fromtimestamp(self.start_time)
        print(f"Test started at: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        try:
            # Start container
            print("Starting container...")
            if not self.start_container():
                print("Failed to start container")
                return self.phases
            
            # Wait a moment for container to initialize
            time.sleep(2)
            
            # Monitor logs
            self.process_logs()
            
        except KeyboardInterrupt:
            print("\nBenchmark interrupted by user")
            self.interrupted = True
            self.should_stop.set()
            self.health_ready_event.set()  # Stop waiting for health check
        except Exception as e:
            print(f"Error during benchmark: {e}")
        finally:
            # Cleanup
            print("\nCleaning up...")
            self.stop_container()
            if hasattr(self, '_keep_image') and not self._keep_image:
                self.cleanup_images()
                self.cleanup_soci_snapshotter()
        
        # Calculate total time and print summary
        total_time = time.time() - self.start_time
        self.print_summary(total_time)
        
        return self.phases
    
    def create_arg_parser(self, description: str) -> argparse.ArgumentParser:
        """Create standard argument parser for benchmarks."""
        parser = argparse.ArgumentParser(description=description)
        
        # Image specification - either full image or repo + tag
        image_group = parser.add_mutually_exclusive_group()
        image_group.add_argument(
            "--image", 
            help="Full container image to test (e.g., registry.com/repo:tag-snapshotter)"
        )
        image_group.add_argument(
            "--repo",
            help="ECR repository name (e.g., my-vllm-app). Will construct full ECR URL automatically"
        )
        
        parser.add_argument(
            "--tag",
            default="latest",
            help="Image tag base (default: latest). Snapshotter suffix will be appended (e.g., latest-nydus)"
        )
        parser.add_argument(
            "--region",
            default="us-east-1",
            help="AWS region for ECR (default: us-east-1)"
        )
        parser.add_argument(
            "--container-name",
            default=f"{self.__class__.__name__.lower().replace('benchmark', '')}-timing-test",
            help="Name for the test container"
        )
        parser.add_argument(
            "--snapshotter",
            default="nydus",
            choices=["nydus", "overlayfs", "native", "soci", "estargz"],
            help="Snapshotter to use"
        )
        parser.add_argument(
            "--port",
            type=int,
            default=self.port,
            help=f"Local port to bind (default: {self.port})"
        )
        parser.add_argument(
            "--model-mount-path",
            help="Path to local SSD directory to mount for model storage (e.g., /mnt/ssd/models)"
        )
        parser.add_argument(
            "--output-json",
            help="Output results to JSON file"
        )
        parser.add_argument(
            "--keep-image",
            action="store_true",
            help="Don't remove image after test (faster for repeated runs)"
        )
        return parser
    
    def save_results(self, results: Dict[str, Optional[float]], output_file: str, 
                    image: str, snapshotter: str):
        """Save results to JSON file."""
        output_data = {
            "application": self.__class__.__name__.replace('Benchmark', '').lower(),
            "snapshotter": snapshotter,
            "image": image,
            "timestamp": datetime.now().isoformat(),
            "phases": results,
            "container_startup_duration": self.container_startup_duration,
            "health_ready_time": self.health_ready_time,
            "supports_health_polling": self.supports_health_polling()
        }
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"\nResults saved to: {output_file}")
    
    def setup_signal_handler(self):
        """Setup graceful interrupt handling."""
        def signal_handler(sig, frame):
            print("\nReceived interrupt signal, cleaning up...")
            self.interrupted = True
            self.should_stop.set()
            self.health_ready_event.set()  # Stop waiting for health check
            # Don't exit immediately, let cleanup happen
        
        signal.signal(signal.SIGINT, signal_handler)
    
    def main(self, description: str) -> int:
        """Main execution method for benchmark scripts."""
        parser = self.create_arg_parser(description)
        args = parser.parse_args()
        
        # Determine image to use
        if args.image:
            # Full image provided
            final_image = args.image
        elif args.repo:
            # Construct ECR image from repo + tag + snapshotter
            final_image = construct_ecr_image(args.repo, args.tag, args.snapshotter, args.region)
            print(f"Constructed ECR image: {final_image}")
        else:
            # Fall back to default image from subclass
            final_image = self.get_default_image(args.snapshotter)
        
        # Update instance with parsed arguments
        self.image = final_image
        self.container_name = args.container_name
        self.snapshotter = args.snapshotter
        self.port = args.port
        self.model_mount_path = args.model_mount_path
        self._keep_image = args.keep_image
        self._region = args.region
        
        # Setup signal handling
        self.setup_signal_handler()
        
        # Override image cleanup if requested
        if args.keep_image:
            self.cleanup_images = lambda: print("Keeping image as requested")
        
        # Run benchmark
        results = self.run_benchmark()
        
        # Output JSON if requested
        if args.output_json:
            self.save_results(results, args.output_json, self.image, args.snapshotter)
        
        
        return 0 if self._is_successful(results) else 1
    
    
    def _is_successful(self, results: Dict[str, Optional[float]]) -> bool:
        """Determine if benchmark was successful. Can be overridden by subclasses."""
        # Default: successful if we have first_log timing
        return results.get("first_log") is not None
