#!/usr/bin/env python3
"""
Build and push container images with different snapshotter formats.
Supports ECR (AWS) and GAR (Google Artifact Registry).
"""

import argparse
import os
import subprocess
import sys
import json
from pathlib import Path
from abc import ABC, abstractmethod


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


class Registry(ABC):
    """Abstract base class for container registries."""

    @abstractmethod
    def check_credentials(self):
        """Check if credentials are configured."""
        pass

    @abstractmethod
    def create_repository(self, image_name):
        """Create repository if it doesn't exist."""
        pass

    @abstractmethod
    def login(self):
        """Login to registry with docker and nerdctl."""
        pass

    @abstractmethod
    def get_registry_url(self):
        """Return the registry URL."""
        pass

    def get_full_image_name(self, image_name, tag="latest"):
        """Construct full image reference."""
        return f"{self.get_registry_url()}/{image_name}:{tag}"


class ECRRegistry(Registry):
    """AWS Elastic Container Registry implementation."""

    def __init__(self, account, region):
        self.account = account
        self.region = region
        self.registry_url = f"{account}.dkr.ecr.{region}.amazonaws.com"

    def check_credentials(self):
        """Check if AWS credentials are configured."""
        try:
            run_command("aws sts get-caller-identity", capture_output=True)
            print("✓ AWS credentials are configured")
        except:
            print("Error: AWS credentials not configured. Please run 'aws configure' first.")
            sys.exit(1)

    def create_repository(self, image_name):
        """Create ECR repository if it doesn't exist."""
        print(f"Checking/creating ECR repository: {image_name}")

        # Check if repository exists
        check_cmd = f"aws ecr describe-repositories --repository-names {image_name} --region {self.region}"
        try:
            run_command(check_cmd, capture_output=True)
            print(f"✓ Repository {image_name} already exists")
        except:
            # Repository doesn't exist, create it
            create_cmd = f"aws ecr create-repository --repository-name {image_name} --region {self.region}"
            run_command(create_cmd)
            print(f"✓ Created repository {image_name}")

    def login(self):
        """Login to ECR using both docker and nerdctl."""
        print("Logging into ECR...")

        password = run_command(f"aws ecr get-login-password --region {self.region}", capture_output=True)

        # Login with docker
        login_cmd = f"echo '{password}' | docker login -u AWS --password-stdin {self.registry_url}"
        run_command(login_cmd)

        # Login with nerdctl
        login_cmd = f"echo '{password}' | nerdctl login -u AWS --password-stdin {self.registry_url}"
        run_command(login_cmd)

        # Login with sudo nerdctl
        login_cmd = f"echo '{password}' | sudo nerdctl login -u AWS --password-stdin {self.registry_url}"
        run_command(login_cmd)

        print("✓ Successfully logged into ECR")

    def get_registry_url(self):
        """Return the ECR registry URL."""
        return self.registry_url


class GARRegistry(Registry):
    """Google Artifact Registry implementation."""

    def __init__(self, project_id, repository, location):
        self.project_id = project_id
        self.repository = repository
        self.location = location
        self.registry_url = f"{location}-docker.pkg.dev/{project_id}/{repository}"

    def check_credentials(self):
        """Check if GCP credentials are configured."""
        try:
            run_command("gcloud auth application-default print-access-token", capture_output=True)
            print("✓ GCP credentials are configured")
        except:
            print("Error: GCP credentials not configured.")
            print("Please run 'gcloud auth application-default login' or 'gcloud auth login'")
            sys.exit(1)

    def create_repository(self, image_name):
        """Create GAR repository if it doesn't exist."""
        print(f"Checking/creating GAR repository: {self.repository}")

        # Check if repository exists
        check_cmd = f"gcloud artifacts repositories describe {self.repository} --location={self.location} --project={self.project_id}"
        try:
            run_command(check_cmd, capture_output=True)
            print(f"✓ Repository {self.repository} already exists")
        except:
            # Repository doesn't exist, create it
            create_cmd = f"gcloud artifacts repositories create {self.repository} --repository-format=docker --location={self.location} --project={self.project_id}"
            run_command(create_cmd)
            print(f"✓ Created repository {self.repository}")

    def login(self):
        """Login to GAR using both docker and nerdctl."""
        print("Logging into Google Artifact Registry...")

        # Configure Docker authentication helper for GAR
        auth_cmd = f"gcloud auth configure-docker {self.location}-docker.pkg.dev"
        run_command(auth_cmd)

        # Get access token for nerdctl login
        token = run_command("gcloud auth print-access-token", capture_output=True)

        # Login with nerdctl
        login_cmd = f"echo '{token}' | nerdctl login -u oauth2accesstoken --password-stdin {self.location}-docker.pkg.dev"
        run_command(login_cmd)

        # Login with sudo nerdctl
        login_cmd = f"echo '{token}' | sudo nerdctl login -u oauth2accesstoken --password-stdin {self.location}-docker.pkg.dev"
        run_command(login_cmd)

        print("✓ Successfully logged into GAR")

    def get_registry_url(self):
        """Return the GAR registry URL."""
        return self.registry_url


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
        full_image = registry.get_full_image_name(image_name, "latest")
        tag_cmd = f"docker tag {image_name} {full_image}"
        run_command(tag_cmd)

        # Push the image
        push_cmd = f"docker push {full_image}"
        run_command(push_cmd)

        print(f"✓ Successfully built and pushed {full_image}")

    finally:
        os.chdir(original_dir)


def convert_to_nydus(image_name, registry):
    """Convert and push Nydus image."""
    print("Converting to Nydus format...")

    source_image = registry.get_full_image_name(image_name, "latest")
    target_image = registry.get_full_image_name(image_name, "latest-nydus")

    nydus_cmd = f"""nydusify convert \\
        --source {source_image} \\
        --source-backend-config ~/.docker/config.json \\
        --target {target_image}"""

    run_command(nydus_cmd)
    print(f"✓ Successfully converted and pushed {target_image}")


def convert_to_soci(image_name, registry):
    """Convert and push SOCI image."""
    print("Converting to SOCI format...")

    source_image = registry.get_full_image_name(image_name, "latest")
    target_image = registry.get_full_image_name(image_name, "latest-soci")

    # Pull the image with nerdctl first
    pull_cmd = f"sudo nerdctl pull {source_image}"
    run_command(pull_cmd)

    # Convert to SOCI
    soci_cmd = f"sudo soci convert {source_image} {target_image}"
    run_command(soci_cmd)

    # Push SOCI image
    push_cmd = f"sudo nerdctl push {target_image}"
    run_command(push_cmd)

    print(f"✓ Successfully converted and pushed {target_image}")


def convert_to_estargz(image_name, registry):
    """Convert and push eStargz image."""
    print("Converting to eStargz format...")

    source_image = registry.get_full_image_name(image_name, "latest")
    target_image = registry.get_full_image_name(image_name, "latest-estargz")

    # Pull the image with nerdctl first
    pull_cmd = f"sudo nerdctl pull {source_image}"
    run_command(pull_cmd)

    estargz_cmd = f"sudo nerdctl image convert --estargz --oci {source_image} {target_image}"
    run_command(estargz_cmd)

    # Push eStargz image
    push_cmd = f"sudo nerdctl push {target_image}"
    run_command(push_cmd)

    print(f"✓ Successfully converted and pushed {target_image}")


def cleanup_built_images(image_name, registry, formats):
    """Remove only the images that were built in this run."""
    import time

    print("\n" + "="*60)
    print("🧹 CLEANUP: Removing built images...")
    print("="*60)

    cleanup_start = time.time()
    images_to_remove = []

    # Collect all image references that were built
    if "normal" in formats:
        images_to_remove.append(image_name)  # Local tag
        images_to_remove.append(registry.get_full_image_name(image_name, "latest"))
    if "nydus" in formats:
        images_to_remove.append(registry.get_full_image_name(image_name, "latest-nydus"))
    if "soci" in formats:
        images_to_remove.append(registry.get_full_image_name(image_name, "latest-soci"))
    if "estargz" in formats:
        images_to_remove.append(registry.get_full_image_name(image_name, "latest-estargz"))

    # Cleanup Docker images
    print("\n📦 Docker Cleanup:")
    for image in images_to_remove:
        try:
            print(f"  Removing: {image}")
            run_command(f"docker rmi -f {image}", check=False, capture_output=True)
        except Exception as e:
            print(f"    ⚠️  Warning: Could not remove {image}: {e}")

    # Cleanup nerdctl images for relevant snapshotters
    snapshotter_map = {
        "normal": "overlayfs",
        "nydus": "nydus",
        "soci": "soci",
        "estargz": "stargz"
    }

    print(f"\n🔧 nerdctl Cleanup:")
    for format_type in formats:
        snapshotter = snapshotter_map.get(format_type)
        if not snapshotter:
            continue

        print(f"  Processing {snapshotter} snapshotter...")
        try:
            # Determine the correct tag
            if format_type == "normal":
                tag = "latest"
            else:
                tag = f"latest-{format_type}"

            image_ref = registry.get_full_image_name(image_name, tag)
            print(f"    Removing: {image_ref}")
            run_command(f"sudo nerdctl --snapshotter {snapshotter} rmi -f {image_ref}", check=False, capture_output=True)

        except Exception as e:
            print(f"    ⚠️  Warning: Could not cleanup {snapshotter} images: {e}")

    total_cleanup_time = time.time() - cleanup_start
    print(f"\n✅ Cleanup completed in {total_cleanup_time:.2f}s")
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
        description="Build and push container images with different snapshotter formats. Supports ECR (AWS) and GAR (Google Artifact Registry).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # ECR (AWS) - Build image from custom path
  python3 build_push.py --registry-type ecr --account 123456789 --image-path /path/to/my/image --image-name my-image --region us-east-1

  # ECR - Build with specific formats
  python3 build_push.py --registry-type ecr --account 123456789 --image-path ./images/cuda --image-name cuda-test --formats normal,nydus

  # GAR (Google) - Build and push all formats
  python3 build_push.py --registry-type gar --project-id my-gcp-project --repository my-repo --image-path ./images/vllm --image-name vllm-app --location us-central1

  # GAR - Build with specific formats
  python3 build_push.py --registry-type gar --project-id my-project --repository ai-models --image-path ./images/sglang --image-name sglang --location us-east1 --formats normal,nydus,soci

  # List available images in default directory
  python3 build_push.py --list-images
        """)

    # Registry selection
    parser.add_argument("--registry-type", choices=["ecr", "gar"], default="ecr",
                       help="Registry type: ecr (AWS) or gar (Google Artifact Registry). Default: ecr")

    # Common arguments
    parser.add_argument("--image-path", required=False, help="Full path to image directory")
    parser.add_argument("--image-name", required=False, help="Image name for the container")
    parser.add_argument("--formats", default="normal,nydus,soci,estargz",
                       help="Comma-separated list of formats to build (normal,nydus,soci,estargz)")
    parser.add_argument("--list-images", action="store_true", help="List available image directories")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup of local images after build")

    # ECR-specific arguments
    parser.add_argument("--account", required=False, help="AWS account ID (required for ECR)")
    parser.add_argument("--region", required=False, default="us-east-1",
                       help="AWS region for ECR (default: us-east-1)")

    # GAR-specific arguments
    parser.add_argument("--project-id", required=False, help="GCP project ID (optional for GAR, defaults to gcloud config)")
    parser.add_argument("--repository", required=False, help="GAR repository name (required for GAR)")
    parser.add_argument("--location", required=False, default="us-central1",
                       help="GCP location for GAR (default: us-central1)")

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

    # Validate registry-specific arguments
    if args.registry_type == "ecr":
        if not args.account:
            parser.error("--account is required for ECR")
    elif args.registry_type == "gar":
        # Get project ID from gcloud config if not provided
        if not args.project_id:
            try:
                args.project_id = run_command("gcloud config get project", capture_output=True)
                if not args.project_id:
                    parser.error("--project-id is required for GAR (or set default project with 'gcloud config set project PROJECT_ID')")
                print(f"Using project ID from gcloud config: {args.project_id}")
            except:
                parser.error("--project-id is required for GAR (or set default project with 'gcloud config set project PROJECT_ID')")
        if not args.repository:
            parser.error("--repository is required for GAR")

    # Validate common required arguments
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

    # Create registry instance based on type
    if args.registry_type == "ecr":
        registry = ECRRegistry(args.account, args.region)
        registry_info = f"Account: {args.account}, Region: {args.region}"
    else:  # gar
        registry = GARRegistry(args.project_id, args.repository, args.location)
        registry_info = f"Project: {args.project_id}, Repository: {args.repository}, Location: {args.location}"

    print("="*70)
    print("🚀 STARTING CONTAINER IMAGE BUILD AND PUSH")
    print("="*70)
    print(f"Registry Type: {args.registry_type.upper()}")
    print(f"Building image: {image_name}")
    print(f"From directory: {image_dir}")
    print(f"{registry_info}")
    print(f"Formats: {formats}")
    print()

    import time
    total_start_time = time.time()

    # Check credentials
    print(f"🔐 Checking {args.registry_type.upper()} credentials...")
    registry.check_credentials()

    # Login to registry
    print(f"\n🔑 Logging into {args.registry_type.upper()}...")
    registry.login()

    # Create repository
    print(f"\n📦 Setting up repository...")
    registry.create_repository(image_name)
    
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
    print(f"Registry: {registry.get_registry_url()}")
    print(f"Base image: {registry.get_full_image_name(image_name, 'latest')}")
    if "nydus" in formats:
        print(f"Nydus image: {registry.get_full_image_name(image_name, 'latest-nydus')}")
    if "soci" in formats:
        print(f"SOCI image: {registry.get_full_image_name(image_name, 'latest-soci')}")
    if "estargz" in formats:
        print(f"eStargz image: {registry.get_full_image_name(image_name, 'latest-estargz')}")

    print(f"\n⏱️  Total build and push time: {total_time:.2f}s ({total_time/60:.1f} minutes)")
    print("="*70)

    # Cleanup built images by default (unless --no-cleanup is specified)
    if not args.no_cleanup:
        cleanup_built_images(image_name, registry, formats)


if __name__ == "__main__":
    main()
