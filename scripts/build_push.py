#!/usr/bin/env python3
"""
Build and push container images with different snapshotter formats.
Supports building from any image directory and creating ECR repositories.
"""

import argparse
import os
import subprocess
import sys
import json
from pathlib import Path


def run_command(cmd, check=True, capture_output=False):
    """Run a shell command and handle errors."""
    import time
    
    print(f"Running: {cmd}")
    start_time = time.time()
    
    try:
        if capture_output:
            result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
            elapsed = time.time() - start_time
            print(f"✓ Completed in {elapsed:.2f}s")
            return result.stdout.strip()
        else:
            subprocess.run(cmd, shell=True, check=check)
            elapsed = time.time() - start_time
            print(f"✓ Completed in {elapsed:.2f}s")
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        print(f"❌ Failed after {elapsed:.2f}s")
        print(f"Error running command: {cmd}")
        print(f"Error: {e}")
        if capture_output and e.stdout:
            print(f"Stdout: {e.stdout}")
        if capture_output and e.stderr:
            print(f"Stderr: {e.stderr}")
        sys.exit(1)


def check_aws_credentials():
    """Check if AWS credentials are configured."""
    try:
        run_command("aws sts get-caller-identity", capture_output=True)
        print("✓ AWS credentials are configured")
    except:
        print("Error: AWS credentials not configured. Please run 'aws configure' first.")
        sys.exit(1)


def create_ecr_repository(registry, image_name, region):
    """Create ECR repository if it doesn't exist."""
    print(f"Checking/creating ECR repository: {image_name}")
    
    # Check if repository exists
    check_cmd = f"aws ecr describe-repositories --repository-names {image_name} --region {region}"
    try:
        run_command(check_cmd, capture_output=True)
        print(f"✓ Repository {image_name} already exists")
    except:
        # Repository doesn't exist, create it
        create_cmd = f"aws ecr create-repository --repository-name {image_name} --region {region}"
        run_command(create_cmd)
        print(f"✓ Created repository {image_name}")


def docker_login(account, region):
    """Login to ECR using both docker and nerdctl."""
    print("Logging into ECR...")
    
    password = run_command(f"aws ecr get-login-password --region {region}", capture_output=True)
    registry = f"{account}.dkr.ecr.{region}.amazonaws.com"
    
    # Login with docker
    login_cmd = f"echo '{password}' | docker login -u AWS --password-stdin {registry}"
    run_command(login_cmd)
    
    # Login with nerdctl
    login_cmd = f"echo '{password}' | nerdctl login -u AWS --password-stdin {registry}"
    run_command(login_cmd)
    
    # Login with sudo nerdctl
    login_cmd = f"echo '{password}' | sudo nerdctl login -u AWS --password-stdin {registry}"
    run_command(login_cmd)
    
    print("✓ Successfully logged into ECR")
    return registry


def build_and_push_image(image_dir, image_name, registry):
    """Build and push the base Docker image."""
    print(f"Building image from {image_dir}...")
    
    # Change to image directory for build context
    original_dir = os.getcwd()
    os.chdir(image_dir)
    
    try:
        # Build the image
        build_cmd = f"docker build -t {image_name} ."
        run_command(build_cmd)
        
        # Tag for registry
        tag_cmd = f"docker tag {image_name} {registry}/{image_name}:latest"
        run_command(tag_cmd)
        
        # Push the image
        push_cmd = f"docker push {registry}/{image_name}:latest"
        run_command(push_cmd)
        
        print(f"✓ Successfully built and pushed {registry}/{image_name}:latest")
        
    finally:
        os.chdir(original_dir)


def convert_to_nydus(image_name, registry):
    """Convert and push Nydus image."""
    print("Converting to Nydus format...")
    
    nydus_cmd = f"""nydusify convert \\
        --source {registry}/{image_name}:latest \\
        --source-backend-config ~/.docker/config.json \\
        --target {registry}/{image_name}:latest-nydus"""
    
    run_command(nydus_cmd)
    print(f"✓ Successfully converted and pushed {registry}/{image_name}:latest-nydus")


def convert_to_soci(image_name, registry):
    """Convert and push SOCI image."""
    print("Converting to SOCI format...")
    
    # Pull the image with nerdctl first
    pull_cmd = f"sudo nerdctl pull {registry}/{image_name}:latest"
    run_command(pull_cmd)
    
    # Convert to SOCI
    soci_cmd = f"sudo soci convert {registry}/{image_name}:latest {registry}/{image_name}:latest-soci"
    run_command(soci_cmd)
    
    # Push SOCI image
    push_cmd = f"sudo nerdctl push {registry}/{image_name}:latest-soci"
    run_command(push_cmd)
    
    print(f"✓ Successfully converted and pushed {registry}/{image_name}:latest-soci")


def convert_to_estargz(image_name, registry):
    """Convert and push eStargz image."""
    print("Converting to eStargz format...")
    
    # Pull the image with nerdctl first
    pull_cmd = f"sudo nerdctl pull {registry}/{image_name}:latest"
    run_command(pull_cmd)
    
    estargz_cmd = f"sudo nerdctl image convert --estargz --oci {registry}/{image_name}:latest {registry}/{image_name}:latest-estargz"
    run_command(estargz_cmd)
    
    # Push eStargz image
    push_cmd = f"sudo nerdctl push {registry}/{image_name}:latest-estargz"
    run_command(push_cmd)
    
    print(f"✓ Successfully converted and pushed {registry}/{image_name}:latest-estargz")


def cleanup_all_images():
    """Remove all Docker and nerdctl images to ensure clean state for benchmarking."""
    import time
    
    print("\n" + "="*60)
    print("🧹 CLEANUP: Removing all local images for benchmarking...")
    print("="*60)
    
    cleanup_start = time.time()
    
    # Cleanup Docker images
    print("\n📦 Docker Cleanup:")
    try:
        # Get all Docker images
        print("  Checking for Docker images...")
        images_cmd = "docker images -q"
        image_ids = run_command(images_cmd, capture_output=True, check=False)
        
        if image_ids.strip():
            # Remove all Docker images
            print("  Removing Docker images...")
            cleanup_cmd = f"docker rmi -f {image_ids.replace(chr(10), ' ')}"
            run_command(cleanup_cmd, check=False)
        else:
            print("  ✓ No Docker images to remove")
            
        # Also clean up Docker system
        print("  Running Docker system cleanup...")
        run_command("docker system prune -f", check=False)
        
    except Exception as e:
        print(f"  ⚠️  Warning: Could not cleanup Docker images: {e}")
    
    # Cleanup nerdctl images for all snapshotters
    snapshotters = ["overlayfs", "nydus", "soci", "stargz"]
    
    print(f"\n🔧 nerdctl Cleanup ({len(snapshotters)} snapshotters):")
    for snapshotter in snapshotters:
        print(f"  Processing {snapshotter} snapshotter...")
        try:
            # Get all nerdctl images for this snapshotter
            images_cmd = f"sudo nerdctl --snapshotter {snapshotter} images -q"
            image_ids = run_command(images_cmd, capture_output=True, check=False)
            
            if image_ids.strip():
                # Remove all nerdctl images for this snapshotter
                cleanup_cmd = f"sudo nerdctl --snapshotter {snapshotter} rmi -f {image_ids.replace(chr(10), ' ')}"
                run_command(cleanup_cmd, check=False)
            else:
                print(f"    ✓ No {snapshotter} images to remove")
                
            # Clean up nerdctl system for this snapshotter
            run_command(f"sudo nerdctl --snapshotter {snapshotter} system prune -f", check=False)
            
        except Exception as e:
            print(f"    ⚠️  Warning: Could not cleanup {snapshotter} images: {e}")
    
    total_cleanup_time = time.time() - cleanup_start
    print(f"\n✅ Cleanup completed in {total_cleanup_time:.2f}s - Ready for benchmarking!")
    print("="*60)


def list_available_images(base_path="snapshotters/images"):
    """List available image directories."""
    images_dir = Path(base_path)
    if not images_dir.exists():
        print(f"Error: {base_path} directory not found")
        return []
    
    image_dirs = []
    for item in images_dir.iterdir():
        if item.is_dir() and (item / "Dockerfile").exists():
            image_dirs.append(item.name)
    
    return sorted(image_dirs)


def main():
    parser = argparse.ArgumentParser(
        description="Build and push container images with different snapshotter formats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build image from custom path
  python3 build_push.py --account 123456789 --image-path /path/to/my/image --image-name my-image --region us-west-2
  
  # Build with specific formats
  python3 build_push.py --account 123456789 --image-path ./images/cuda --image-name cuda-test --formats normal,nydus
  
  # List available images in default directory
  python3 build_push.py --list-images
        """)
    
    parser.add_argument("--account", required=False, help="AWS account ID")
    parser.add_argument("--image-path", required=False, help="Full path to image directory")
    parser.add_argument("--region", required=False, default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("--image-name", required=False, help="Image name for the container")
    parser.add_argument("--formats", default="normal,nydus,soci,estargz", 
                       help="Comma-separated list of formats to build (normal,nydus,soci,estargz)")
    parser.add_argument("--list-images", action="store_true", help="List available image directories")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup of local images after build")
    
    args = parser.parse_args()
    
    # List available images
    if args.list_images:
        available_images = list_available_images()
        if available_images:
            print("Available image directories:")
            for img in available_images:
                print(f"  - {img}")
        else:
            print("No image directories found with Dockerfiles")
        return
    
    # Validate required arguments
    if not args.account:
        parser.error("--account is required")
    if not args.image_path:
        parser.error("--image-path is required")
    if not args.image_name:
        parser.error("--image-name is required")
    
    # Validate image directory exists
    image_dir = Path(args.image_path)
    if not image_dir.exists():
        print(f"Error: Image directory '{args.image_path}' not found")
        sys.exit(1)
    
    dockerfile_path = image_dir / "Dockerfile"
    if not dockerfile_path.exists():
        print(f"Error: No Dockerfile found in {image_dir}")
        sys.exit(1)
    
    # Parse formats
    formats = [f.strip() for f in args.formats.split(",")]
    valid_formats = {"normal", "nydus", "soci", "estargz"}
    invalid_formats = set(formats) - valid_formats
    if invalid_formats:
        print(f"Error: Invalid formats: {invalid_formats}")
        print(f"Valid formats: {valid_formats}")
        sys.exit(1)
    
    # Set image name
    image_name = args.image_name
    
    print("="*70)
    print("🚀 STARTING CONTAINER IMAGE BUILD AND PUSH")
    print("="*70)
    print(f"Building image: {image_name}")
    print(f"From directory: {image_dir}")
    print(f"Account: {args.account}")
    print(f"Region: {args.region}")
    print(f"Formats: {formats}")
    print()
    
    import time
    total_start_time = time.time()
    
    # Check AWS credentials
    print("🔐 Checking AWS credentials...")
    check_aws_credentials()
    
    # Login to ECR
    print("\n🔑 Logging into ECR...")
    registry = docker_login(args.account, args.region)
    
    # Create ECR repository
    print(f"\n📦 Setting up ECR repository...")
    create_ecr_repository(registry, image_name, args.region)
    
    # Build and push base image
    if "normal" in formats:
        print(f"\n🏗️  Building and pushing base image...")
        build_start = time.time()
        build_and_push_image(str(image_dir), image_name, registry)
        build_time = time.time() - build_start
        print(f"✅ Base image build completed in {build_time:.2f}s")
    
    # Convert to different formats
    if "nydus" in formats:
        print(f"\n🔄 Converting to Nydus format...")
        nydus_start = time.time()
        convert_to_nydus(image_name, registry)
        nydus_time = time.time() - nydus_start
        print(f"✅ Nydus conversion completed in {nydus_time:.2f}s")
    
    if "soci" in formats:
        print(f"\n🔄 Converting to SOCI format...")
        soci_start = time.time()
        convert_to_soci(image_name, registry)
        soci_time = time.time() - soci_start
        print(f"✅ SOCI conversion completed in {soci_time:.2f}s")
    
    if "estargz" in formats:
        print(f"\n🔄 Converting to eStargz format...")
        estargz_start = time.time()
        convert_to_estargz(image_name, registry)
        estargz_time = time.time() - estargz_start
        print(f"✅ eStargz conversion completed in {estargz_time:.2f}s")
    
    total_time = time.time() - total_start_time
    
    print("\n" + "="*70)
    print("🎉 ALL FORMATS BUILT AND PUSHED SUCCESSFULLY!")
    print("="*70)
    print(f"Registry: {registry}")
    print(f"Base image: {registry}/{image_name}:latest")
    if "nydus" in formats:
        print(f"Nydus image: {registry}/{image_name}:latest-nydus")
    if "soci" in formats:
        print(f"SOCI image: {registry}/{image_name}:latest-soci")
    if "estargz" in formats:
        print(f"eStargz image: {registry}/{image_name}:latest-estargz")
    
    print(f"\n⏱️  Total build and push time: {total_time:.2f}s ({total_time/60:.1f} minutes)")
    print("="*70)
    
    # Cleanup all local images by default (unless --no-cleanup is specified)
    if not args.no_cleanup:
        cleanup_all_images()


if __name__ == "__main__":
    main()
