"""
FastPull build command - Build and convert container images.

Supports two modes:
1. Build from Dockerfile: docker build → push → convert
2. Convert existing image: pull (if needed) → push → convert
"""

import argparse
import os
import subprocess
import sys
from typing import List

from . import common


def add_parser(subparsers):
    """Add build subcommand parser."""
    parser = subparsers.add_parser(
        'build',
        help='Build and convert container images',
        description='Build Docker images and convert to Nydus/SOCI/eStarGZ formats'
    )

    # Image specification
    parser.add_argument(
        '--repository-url',
        required=True,
        help='Full image reference (e.g., account.dkr.ecr.region.amazonaws.com/myapp:v1)'
    )
    parser.add_argument(
        '--dockerfile-path',
        help='Path to Dockerfile directory (optional - if not provided, assumes image exists)'
    )

    # Registry configuration
    parser.add_argument(
        '--registry',
        choices=['ecr', 'gar', 'dockerhub', 'auto'],
        default='auto',
        help='Registry type (default: auto-detect from image URL)'
    )

    # Google GAR parameters
    parser.add_argument(
        '--project-id',
        help='GCP project ID (for GAR)'
    )
    parser.add_argument(
        '--location',
        default='us-central1',
        help='GCP location (default: us-central1)'
    )
    parser.add_argument(
        '--repository',
        help='GAR repository name (for GAR)'
    )

    # Build options
    parser.add_argument(
        '--format',
        default='docker,nydus',
        help='Comma-separated formats: docker, nydus, soci, estargz (default: docker,nydus)'
    )
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Build without cache'
    )
    parser.add_argument(
        '--build-arg',
        action='append',
        help='Build arguments (can be used multiple times)'
    )
    parser.add_argument(
        '--dockerfile',
        default='Dockerfile',
        help='Dockerfile name (default: Dockerfile)'
    )

    parser.set_defaults(func=build_command)
    return parser


def build_command(args):
    """Execute the build command."""
    # Auto-detect registry
    if args.registry == 'auto':
        args.registry = common.detect_registry_type(args.repository_url)
        if args.registry == 'unknown':
            print(f"Error: Could not auto-detect registry from image: {args.repository_url}")
            print("Please specify --registry explicitly")
            sys.exit(1)
        print(f"Auto-detected registry: {args.registry}")

    # Validate registry-specific parameters
    if args.registry == 'ecr':
        # Get account and region from AWS CLI
        args.account = common.get_aws_account_id()
        args.region = common.get_aws_region()

        if not args.account:
            print("Error: Could not detect AWS account ID. Please configure AWS CLI (aws configure)")
            sys.exit(1)

        if not args.region:
            args.region = 'us-east-1'  # Fallback to default

        print(f"Using AWS account: {args.account}, region: {args.region}")

    if args.registry == 'gar' and not args.repository:
        parsed = common.parse_gar_url(args.repository_url)
        if parsed:
            args.location, args.project_id, args.repository = parsed
        else:
            print("Error: --repository required for GAR")
            sys.exit(1)

    # Parse formats
    formats = [f.strip().lower() for f in args.format.split(',')]
    valid_formats = ['docker', 'nydus', 'soci', 'estargz']
    for fmt in formats:
        if fmt not in valid_formats:
            print(f"Error: Invalid format '{fmt}'. Valid: {', '.join(valid_formats)}")
            sys.exit(1)

    # Authenticate with registry
    print(f"\nAuthenticating with {args.registry}...")
    if not authenticate_registry(args):
        print("Error: Authentication failed")
        sys.exit(1)

    # Determine build mode
    if args.dockerfile_path:
        # Mode 1: Build from Dockerfile
        build_from_dockerfile(args, formats)
    else:
        # Mode 2: Convert existing image
        if 'docker' in formats:
            print("Warning: --image-path not provided, skipping docker build")
            formats.remove('docker')

        if not formats:
            print("Error: No formats to build (docker requires --image-path)")
            sys.exit(1)

        convert_existing_image(args, formats)

    print("\n" + "="*60)
    print("BUILD COMPLETE")
    print("="*60)


def authenticate_registry(args) -> bool:
    """Authenticate with the registry."""
    if args.registry == 'ecr':
        return authenticate_ecr(args)
    elif args.registry == 'gar':
        return authenticate_gar(args)
    elif args.registry == 'dockerhub':
        print("Assuming Docker Hub authentication already configured")
        return True
    return False


def authenticate_ecr(args) -> bool:
    """Authenticate with AWS ECR."""
    try:
        # Get login password
        result = subprocess.run(
            ['aws', 'ecr', 'get-login-password', '--region', args.region],
            check=True,
            capture_output=True,
            text=True
        )
        password = result.stdout.strip()

        # Login with docker
        registry_url = f"{args.account}.dkr.ecr.{args.region}.amazonaws.com"
        subprocess.run(
            ['docker', 'login', '--username', 'AWS', '--password-stdin', registry_url],
            input=password,
            check=True,
            capture_output=True,
            text=True
        )

        # Login with nerdctl
        subprocess.run(
            ['sudo', 'nerdctl', 'login', '--username', 'AWS', '--password-stdin', registry_url],
            input=password,
            check=True,
            capture_output=True,
            text=True
        )

        print(f"✓ Authenticated with ECR")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ ECR authentication failed: {e}")
        return False


def authenticate_gar(args) -> bool:
    """Authenticate with Google Artifact Registry."""
    try:
        if not args.project_id:
            result = subprocess.run(
                ['gcloud', 'config', 'get', 'project'],
                check=True,
                capture_output=True,
                text=True
            )
            args.project_id = result.stdout.strip()

        registry_url = f"{args.location}-docker.pkg.dev"
        subprocess.run(
            ['gcloud', 'auth', 'configure-docker', registry_url, '--quiet'],
            check=True,
            capture_output=True
        )

        print(f"✓ Authenticated with GAR")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ GAR authentication failed: {e}")
        return False


def build_from_dockerfile(args, formats: List[str]):
    """Mode 1: Build from Dockerfile, push, and convert."""
    print("\n" + "="*60)
    print("MODE: Build from Dockerfile")
    print("="*60)

    # Validate image path
    if not os.path.isdir(args.dockerfile_path):
        print(f"Error: Directory not found: {args.dockerfile_path}")
        sys.exit(1)

    dockerfile_path = os.path.join(args.dockerfile_path, args.dockerfile)
    if not os.path.isfile(dockerfile_path):
        print(f"Error: Dockerfile not found: {dockerfile_path}")
        sys.exit(1)

    built_images = []

    # Build and push Docker image
    if 'docker' in formats:
        if build_and_push_docker(args):
            built_images.append(args.repository_url)

    # Convert to other formats
    if 'nydus' in formats:
        nydus_image = f"{args.repository_url.rsplit(':', 1)[0]}:{args.repository_url.rsplit(':', 1)[1]}-nydus"
        if convert_to_nydus(args.repository_url, nydus_image):
            built_images.append(nydus_image)

    if 'soci' in formats:
        soci_image = f"{args.repository_url.rsplit(':', 1)[0]}:{args.repository_url.rsplit(':', 1)[1]}-soci"
        if convert_to_soci(args.repository_url, soci_image):
            built_images.append(soci_image)

    if 'estargz' in formats:
        estargz_image = f"{args.repository_url.rsplit(':', 1)[0]}:{args.repository_url.rsplit(':', 1)[1]}-estargz"
        if convert_to_estargz(args.repository_url, estargz_image):
            built_images.append(estargz_image)

    # Summary
    print_summary(built_images)


def convert_existing_image(args, formats: List[str]):
    """Mode 2: Convert existing image (no docker build)."""
    print("\n" + "="*60)
    print("MODE: Convert Existing Image")
    print("="*60)

    built_images = []

    # Convert to requested formats
    if 'nydus' in formats:
        nydus_image = f"{args.repository_url.rsplit(':', 1)[0]}:{args.repository_url.rsplit(':', 1)[1]}-nydus"
        if convert_to_nydus(args.repository_url, nydus_image):
            built_images.append(nydus_image)

    if 'soci' in formats:
        soci_image = f"{args.repository_url.rsplit(':', 1)[0]}:{args.repository_url.rsplit(':', 1)[1]}-soci"
        if convert_to_soci(args.repository_url, soci_image):
            built_images.append(soci_image)

    if 'estargz' in formats:
        estargz_image = f"{args.repository_url.rsplit(':', 1)[0]}:{args.repository_url.rsplit(':', 1)[1]}-estargz"
        if convert_to_estargz(args.repository_url, estargz_image):
            built_images.append(estargz_image)

    # Summary
    print_summary(built_images)


def build_and_push_docker(args) -> bool:
    """Build and push Docker image."""
    print(f"\n[Docker] Building {args.repository_url}...")

    # Build
    cmd = [
        'docker', 'build',
        '-t', args.repository_url,
        '-f', os.path.join(args.dockerfile_path, args.dockerfile)
    ]

    if args.no_cache:
        cmd.append('--no-cache')

    if args.build_arg:
        for build_arg in args.build_arg:
            cmd.extend(['--build-arg', build_arg])

    cmd.append(args.dockerfile_path)

    try:
        subprocess.run(cmd, check=True)
        print(f"[Docker] ✓ Built {args.repository_url}")
    except subprocess.CalledProcessError:
        print(f"[Docker] ✗ Build failed")
        return False

    # Push
    print(f"[Docker] Pushing {args.repository_url}...")
    try:
        subprocess.run(['docker', 'push', args.repository_url], check=True)
        print(f"[Docker] ✓ Pushed {args.repository_url}")
        return True
    except subprocess.CalledProcessError:
        print(f"[Docker] ✗ Push failed")
        return False


def convert_to_nydus(source_image: str, target_image: str) -> bool:
    """Convert to Nydus format."""
    print(f"\n[Nydus] Converting {source_image} → {target_image}...")

    cmd = [
        'nydusify', 'convert',
        '--source', source_image,
        '--target', target_image
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"[Nydus] ✓ Converted and pushed {target_image}")
        return True
    except subprocess.CalledProcessError:
        print(f"[Nydus] ✗ Conversion failed")
        return False


def convert_to_soci(source_image: str, target_image: str) -> bool:
    """Convert to SOCI format."""
    print(f"\n[SOCI] Converting {source_image} → {target_image}...")

    # Pull with nerdctl
    try:
        subprocess.run(['sudo', 'nerdctl', 'pull', source_image], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print(f"[SOCI] ✗ Pull failed")
        return False

    # Convert
    try:
        subprocess.run(['sudo', 'soci', 'create', source_image], check=True)
    except subprocess.CalledProcessError:
        print(f"[SOCI] ✗ Conversion failed")
        return False

    # Tag and push
    try:
        subprocess.run(['sudo', 'nerdctl', 'tag', source_image, target_image], check=True)
        subprocess.run(['sudo', 'nerdctl', 'push', target_image], check=True)
        print(f"[SOCI] ✓ Converted and pushed {target_image}")
        return True
    except subprocess.CalledProcessError:
        print(f"[SOCI] ✗ Push failed")
        return False


def convert_to_estargz(source_image: str, target_image: str) -> bool:
    """Convert to eStarGZ format."""
    print(f"\n[eStarGZ] Converting {source_image} → {target_image}...")

    try:
        subprocess.run(['sudo', 'nerdctl', '--snapshotter', 'stargz', 'pull', source_image],
                      check=True, capture_output=True)
        subprocess.run(['sudo', 'nerdctl', '--snapshotter', 'stargz', 'tag', source_image, target_image],
                      check=True)
        subprocess.run(['sudo', 'nerdctl', '--snapshotter', 'stargz', 'push', target_image],
                      check=True)
        print(f"[eStarGZ] ✓ Converted and pushed {target_image}")
        return True
    except subprocess.CalledProcessError:
        print(f"[eStarGZ] ✗ Conversion failed")
        return False


def print_summary(images: List[str]):
    """Print build summary."""
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    if images:
        print("Successfully built and pushed:")
        for img in images:
            print(f"  ✓ {img}")
    else:
        print("No images were built successfully")
    print("="*60)
