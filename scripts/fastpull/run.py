"""
FastPull run command - Run containers with specified snapshotters and benchmarking.
"""

import argparse
import subprocess
import sys
import threading
import time
from typing import List, Optional

from . import benchmark
from . import common


def add_parser(subparsers):
    """Add run subcommand parser."""
    parser = subparsers.add_parser(
        'run',
        help='Run container with specified snapshotter',
        description='Run containers with Nydus or OverlayFS snapshotter'
    )

    # Mode selection (replaces --snapshotter)
    parser.add_argument(
        '--mode',
        choices=['nydus', 'normal'],
        default='nydus',
        help='Run mode: nydus (default, adds -fastpull suffix) or normal (overlayfs, no suffix)'
    )

    # Benchmarking arguments
    parser.add_argument(
        '--benchmark-mode',
        choices=['none', 'completion', 'readiness'],
        default='none',
        help='Benchmarking mode (default: none)'
    )
    parser.add_argument(
        '--readiness-endpoint',
        help='HTTP endpoint to poll for readiness (required if benchmark-mode=readiness)'
    )
    parser.add_argument(
        '--output-json',
        help='Export benchmark metrics to JSON file'
    )

    # Common container flags
    parser.add_argument('--name', help='Container name')
    parser.add_argument('-p', '--publish', action='append', help='Publish ports (can be used multiple times)')
    parser.add_argument('-e', '--env', action='append', help='Set environment variables')
    parser.add_argument('-v', '--volume', action='append', help='Bind mount volumes')
    parser.add_argument('--gpus', help='GPU devices to use (e.g., "all")')
    parser.add_argument('--rm', action='store_true', help='Automatically remove container when it exits')
    parser.add_argument('-d', '--detach', action='store_true', help='Run container in background')

    # Image as positional argument (like docker/nerdctl run)
    parser.add_argument(
        'image',
        help='Container image to run'
    )

    # Pass-through for additional nerdctl flags (optional trailing args)
    parser.add_argument(
        'nerdctl_args',
        nargs='*',
        help='Additional arguments to pass to nerdctl/docker (e.g., command to run in container)'
    )

    parser.set_defaults(func=run_command)
    return parser


def run_command(args):
    """Execute the run command."""
    # Validate benchmark mode
    if args.benchmark_mode == 'readiness' and not args.readiness_endpoint:
        print("Error: --readiness-endpoint is required when --benchmark-mode=readiness")
        sys.exit(1)

    # Determine snapshotter and modify image tag based on mode
    if args.mode == 'nydus':
        args.snapshotter = 'nydus'
        # Add -fastpull suffix to image tag if not already present
        if ':' in args.image:
            base, tag = args.image.rsplit(':', 1)
            if not tag.endswith('-fastpull'):
                args.image = f"{base}:{tag}-fastpull"
        else:
            args.image = f"{args.image}:latest-fastpull"
    else:  # normal mode
        args.snapshotter = 'overlayfs'
        # Use image as-is for normal mode

    # Build the nerdctl/docker command
    cmd = build_run_command(args)

    print(f"Running container with {args.snapshotter} snapshotter...")
    print(f"Image: {args.image}")
    print(f"Command: {' '.join(cmd)}\n")

    # For benchmarking, we need to track the container
    if args.benchmark_mode != 'none':
        run_with_benchmark(cmd, args)
    else:
        run_without_benchmark(cmd)


def build_run_command(args) -> List[str]:
    """
    Build the nerdctl/docker run command from arguments.

    Args:
        args: Parsed command-line arguments

    Returns:
        Command as list of strings
    """
    # Determine binary (use sudo)
    if args.snapshotter == 'overlayfs':
        cmd = ['sudo', 'nerdctl', '--snapshotter', 'overlayfs', 'run']
    else:
        cmd = ['sudo', 'nerdctl', '--snapshotter', args.snapshotter, 'run']

    # Add common flags
    if args.name:
        cmd.extend(['--name', args.name])

    if args.rm:
        cmd.append('--rm')

    if args.detach:
        cmd.append('-d')

    # Add ports
    if args.publish:
        for port in args.publish:
            cmd.extend(['-p', port])

    # Add environment variables
    if args.env:
        for env in args.env:
            cmd.extend(['-e', env])

    # Add volumes
    if args.volume:
        for vol in args.volume:
            cmd.extend(['-v', vol])

    # Add GPU support
    if args.gpus:
        cmd.extend(['--gpus', args.gpus])

    # Add any additional pass-through arguments
    if args.nerdctl_args:
        cmd.extend(args.nerdctl_args)

    # Add image (must be last)
    cmd.append(args.image)

    return cmd


def run_without_benchmark(cmd: List[str]):
    """
    Run container without benchmarking.

    Args:
        cmd: Command to execute
    """
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running container: {e}")
        sys.exit(1)


def run_with_benchmark(cmd: List[str], args):
    """
    Run container with benchmarking enabled.

    Args:
        cmd: Command to execute
        args: Parsed arguments
    """
    # Force detached mode for benchmarking
    if '-d' not in cmd and '--detach' not in cmd:
        cmd.insert(cmd.index('run') + 1, '-d')

    # Initialize benchmark tracker early (before starting container)
    # We'll set container_id later, but we need to start event monitoring first
    bench = benchmark.ContainerBenchmark(
        container_id='',  # Will be set after container starts
        benchmark_mode=args.benchmark_mode,
        readiness_endpoint=args.readiness_endpoint,
        mode=args.mode
    )

    # Start event monitoring BEFORE starting the container
    print("Starting containerd events monitoring...")
    bench.start_event_monitoring()

    # Small delay to ensure event monitoring is ready
    time.sleep(0.5)

    # Start the container
    try:
        print(f"Running container...")
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        container_id = result.stdout.strip()

        if not container_id:
            print("Error: Failed to get container ID")
            sys.exit(1)

        print(f"Container started: {container_id[:12]}")

        # Update benchmark tracker with container ID
        bench.container_id = container_id

    except subprocess.CalledProcessError as e:
        print(f"Error starting container: {e}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        sys.exit(1)

    # Start monitoring logs in background
    print("Monitoring container logs...")
    stop_logs_event = threading.Event()
    log_thread = start_log_monitoring(container_id, args.snapshotter, bench.start_time, stop_logs_event)

    # Wait for completion or readiness
    try:
        if args.benchmark_mode == 'completion':
            success = bench.wait_for_completion()
        elif args.benchmark_mode == 'readiness':
            success = bench.wait_for_readiness()
        else:
            success = True

        # Stop log monitoring after benchmark completes
        stop_logs_event.set()

        if not success:
            print("Benchmark failed (timeout)")
            # Cleanup on failure
            cleanup_container(container_id, args.snapshotter)
            sys.exit(1)

        # Print summary
        bench.print_summary()

        # Export JSON if requested
        if args.output_json:
            bench.export_json(args.output_json)

        # Cleanup container after successful benchmark
        print("\nBenchmark complete, cleaning up container...")
        cleanup_container(container_id, args.snapshotter)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        # Stop and remove container
        cleanup_container(container_id, args.snapshotter)
        sys.exit(1)


def start_log_monitoring(container_id: str, snapshotter: str, start_time: float, stop_event: threading.Event) -> threading.Thread:
    """
    Start monitoring container logs in background thread.

    Args:
        container_id: Container ID
        snapshotter: Snapshotter type
        start_time: Benchmark start time
        stop_event: Event to signal when to stop monitoring

    Returns:
        Log monitoring thread
    """
    def log_reader():
        try:
            cmd = ['sudo', 'nerdctl', 'logs', '-f', container_id]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            for line in process.stdout:
                if stop_event.is_set():
                    process.terminate()
                    break
                if line:
                    elapsed = time.time() - start_time
                    print(f"[{elapsed:.3f}s] {line.rstrip()}")

        except Exception as e:
            pass  # Silently handle errors (container might be stopped)

    thread = threading.Thread(target=log_reader, daemon=True)
    thread.start()
    return thread


def cleanup_container(container_id: str, snapshotter: str):
    """
    Stop and remove container.

    Args:
        container_id: Container ID
        snapshotter: Snapshotter type
    """
    print(f"Cleaning up container {container_id[:12]}...")
    subprocess.run(['sudo', 'nerdctl', 'stop', container_id], capture_output=True)
    subprocess.run(['sudo', 'nerdctl', 'rm', container_id], capture_output=True)
