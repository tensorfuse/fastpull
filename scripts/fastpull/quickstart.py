"""
FastPull quickstart command - Quick benchmarking comparisons.
"""

import argparse
import subprocess
import sys
import os


# Workload configurations: (name, base_image, endpoint)
WORKLOADS = {
    'tensorrt': ('TensorRT', 'tensorrt', '/health'),
    'vllm': ('vLLM', 'vllm', '/health'),
    'sglang': ('SGLang', 'sglang', '/health_generate'),
}


def add_parser(subparsers):
    """Add quickstart subcommand parser."""
    parser = subparsers.add_parser(
        'quickstart',
        help='Quick benchmark comparisons',
        description='Run pre-configured benchmarks'
    )

    subparsers_qs = parser.add_subparsers(dest='workload', help='Workload to benchmark')

    for workload in WORKLOADS:
        wp = subparsers_qs.add_parser(workload, help=f'Benchmark {WORKLOADS[workload][0]} (nydus vs overlayfs)')
        wp.add_argument('--output-dir', help='Directory to save results')
        wp.set_defaults(func=run_quickstart)

    parser.set_defaults(func=lambda args: parser.print_help() if not args.workload else None)
    return parser


def run_quickstart(args):
    """Run benchmark comparison for a workload."""
    name, image_name, endpoint = WORKLOADS[args.workload]

    print(f"\n{'='*60}\n{name} Benchmark: FastPull vs Normal\n{'='*60}\n")

    base = f"public.ecr.aws/s6z9f6e5/tensorfuse/fastpull/{image_name}:latest"

    for mode in ['nydus', 'normal']:
        print(f"\n[{mode.upper()}] Starting benchmark...")

        # Use fastpull command directly (works when installed via pip)
        cmd = [
            'fastpull', 'run',
            '--mode', mode,
            '--benchmark-mode', 'readiness',
            '--readiness-endpoint', f'http://localhost:8080{endpoint}',
            '-p', '8080:8000',
            '--gpus', 'all',
            base  # Image as positional argument (tag suffix added automatically by run command)
        ]

        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            cmd.extend(['--output-json', f'{args.output_dir}/{image_name}-{mode}.json'])

        try:
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, KeyboardInterrupt):
            sys.exit(1)

    print(f"\n{'='*60}\nBenchmark complete!")
    if args.output_dir:
        print(f"Results: {args.output_dir}/")
    print(f"{'='*60}\n")

    # Auto cleanup after benchmarks complete
    print("\nCleaning up containers and images...")
    cleanup_cmd = ['fastpull', 'clean', '--all', '--force']
    try:
        subprocess.run(cleanup_cmd, check=False)  # Don't fail if cleanup has issues
    except Exception as e:
        print(f"Warning: Cleanup had issues: {e}")
    print("Cleanup complete!\n")
