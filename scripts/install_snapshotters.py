#!/usr/bin/env python3
"""
Container Snapshotter Installation Script

This script installs and configures multiple container snapshotters:
- Nydus: Efficient container image storage with lazy loading
- SOCI (Seekable OCI): AWS-developed snapshotter for faster container startup
- StarGZ: Google-developed snapshotter with eStargz format support

The script also installs supporting tools like nerdctl and CNI plugins,
configures systemd services, and sets up containerd integration.

Requirements:
- Must be run as root
- Linux system with systemd
- Internet access for downloading binaries
"""

import os
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path

# Configuration constants for component versions
NYDUS_VERSION = "2.3.6"
NYDUS_SNAPSHOTTER_VERSION = "0.15.3"
NERDCTL_VERSION = "2.1.4"
CNI_VERSION = "v1.8.0"
SOCI_VERSION = "0.11.1"
STARGZ_VERSION = "0.17.0"

def run_command(cmd, check=True, shell=False):
    """
    Execute a shell command with error handling.
    
    Args:
        cmd: Command to execute (list or string)
        check: Whether to raise exception on non-zero exit code
        shell: Whether to use shell execution
        
    Returns:
        subprocess.CompletedProcess: Command execution result
    """
    if shell:
        result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
    else:
        result = subprocess.run(cmd, check=check, capture_output=True, text=True)
    return result

def check_root():
    """
    Verify that the script is running with root privileges.
    Exits with error code 1 if not running as root.
    """
    if os.geteuid() != 0:
        print("This script must be run as root")
        sys.exit(1)

def download_and_extract(url, extract_to=None):
    """
    Download and extract a tar.gz archive from a URL.
    
    Args:
        url: URL to download the archive from
        extract_to: Optional directory to extract to (current dir if None)
        
    Returns:
        str: Filename of the downloaded archive
    """
    filename = url.split('/')[-1]
    
    # Download the archive
    print(f"  Downloading {filename}...")
    run_command(['wget', url])
    
    # Extract the archive
    print(f"  Extracting {filename}...")
    if extract_to:
        run_command(['tar', '-xzf', filename, '-C', extract_to])
    else:
        run_command(['tar', '-xzf', filename])
    
    # Clean up the downloaded archive
    os.remove(filename)
    return filename

def install_nydus():
    """
    Install Nydus container image acceleration toolkit.
    
    Nydus provides lazy loading capabilities for container images,
    reducing startup time and bandwidth usage.
    """
    print("------------------ Installing Nydus -------------------------------")
    print(f"Installing Nydus v{NYDUS_VERSION}...")
    
    # Download and extract Nydus static binaries
    url = f"https://github.com/dragonflyoss/nydus/releases/download/v{NYDUS_VERSION}/nydus-static-v{NYDUS_VERSION}-linux-amd64.tgz"
    download_and_extract(url)
    
    # Install binaries to system path
    print("  Installing Nydus binaries...")
    nydus_binaries = list(Path('nydus-static').glob('*'))
    run_command(['cp', '-r'] + [str(b) for b in nydus_binaries] + ['/usr/local/bin/'])
    
    # Make binaries executable
    nydus_installed = list(Path('/usr/local/bin').glob('nydus*'))
    run_command(['chmod', '+x'] + [str(p) for p in nydus_installed])
    
    # Clean up temporary files
    shutil.rmtree('nydus-static', ignore_errors=True)

def install_nydus_snapshotter():
    """
    Install Nydus Snapshotter for containerd integration.
    
    This component bridges Nydus with containerd, enabling
    container runtime to use Nydus-optimized images.
    """
    print(f"Installing Nydus Snapshotter v{NYDUS_SNAPSHOTTER_VERSION}...")
    
    # Download Nydus Snapshotter
    url = f"https://github.com/containerd/nydus-snapshotter/releases/download/v{NYDUS_SNAPSHOTTER_VERSION}/nydus-snapshotter-v{NYDUS_SNAPSHOTTER_VERSION}-linux-amd64.tar.gz"
    download_and_extract(url)
    
    # Install the containerd-nydus-grpc binary
    print("  Installing Nydus Snapshotter binary...")
    run_command(['cp', 'bin/containerd-nydus-grpc', '/usr/local/bin/'])
    run_command(['chmod', '+x', '/usr/local/bin/containerd-nydus-grpc'])
    
    # Clean up temporary files
    shutil.rmtree('bin', ignore_errors=True)

def install_nerdctl():
    """
    Install nerdctl - containerd-compatible Docker CLI.
    
    nerdctl provides a Docker-compatible command line interface
    for containerd, enabling easy container management.
    """
    print(f"Installing nerdctl v{NERDCTL_VERSION}...")
    
    # Download nerdctl
    url = f"https://github.com/containerd/nerdctl/releases/download/v{NERDCTL_VERSION}/nerdctl-{NERDCTL_VERSION}-linux-amd64.tar.gz"
    download_and_extract(url)
    
    # Install nerdctl binary
    print("  Installing nerdctl binary...")
    run_command(['cp', 'nerdctl', '/usr/local/bin/'])
    
    # Clean up temporary files
    os.remove('nerdctl')

def install_cni_plugins():
    """
    Install Container Network Interface (CNI) plugins.
    
    CNI plugins provide networking capabilities for containers,
    enabling network isolation and communication.
    """
    print("Installing CNI plugins...")
    
    # Create CNI plugin directory
    print("  Creating CNI plugin directory...")
    os.makedirs('/opt/cni/bin', exist_ok=True)
    
    # Download and install CNI plugins
    url = f"https://github.com/containernetworking/plugins/releases/download/{CNI_VERSION}/cni-plugins-linux-amd64-{CNI_VERSION}.tgz"
    filename = url.split('/')[-1]
    
    print(f"  Downloading CNI plugins {CNI_VERSION}...")
    run_command(['wget', url])
    
    print("  Installing CNI plugins...")
    run_command(['tar', '-xzf', filename, '-C', '/opt/cni/bin'])
    os.remove(filename)

def test_nydus_installation():
    """
    Verify that Nydus components are properly installed.
    
    Tests the installation by checking version information
    for core Nydus tools.
    """
    print("Testing Nydus installation...")
    
    # List of Nydus tools to test
    commands = [
        ['nydus-image', '--version'],  # Image conversion tool
        ['nydusd', '--version'],       # Nydus daemon
        ['nydusify', '--version']      # Image format converter
    ]
    
    # Test each tool and report any failures
    for cmd in commands:
        try:
            result = run_command(cmd)
            print(f"  ✓ {cmd[0]} is working")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Warning: {' '.join(cmd)} failed: {e}")

def configure_nydus_snapshotter():
    """
    Create configuration files for Nydus Snapshotter.
    
    Sets up the nydusd daemon configuration with optimized
    settings for registry backend and filesystem prefetching.
    """
    print("=== Nydus Snapshotter Configuration Deployment ===")
    
    # Create Nydus configuration directory
    print("  Creating Nydus configuration directory...")
    os.makedirs('/etc/nydus', exist_ok=True)
    
    # Nydus daemon configuration for FUSE mode
    config_content = """{
  "device": {
    "backend": {
      "type": "registry",
      "config": {
        "timeout": 5,
        "connect_timeout": 5,
        "retry_limit": 2
      }
    },
    "cache": {
      "type": "blobcache"
    }
  },
  "mode": "direct",
  "digest_validate": false,
  "iostats_files": false,
  "enable_xattr": true,
  "amplify_io": 1048576,
  "fs_prefetch": {
    "enable": true,
    "threads_count": 64,
    "merging_size": 1048576,
    "prefetch_all": true
  }
}"""
    
    # Write configuration file
    print("  Writing Nydus daemon configuration...")
    with open('/etc/nydus/nydusd-config.fusedev.json', 'w') as f:
        f.write(config_content)

def install_soci():
    """
    Install SOCI (Seekable OCI) snapshotter.
    
    SOCI is AWS's container image format that enables
    faster container startup through lazy loading.
    """
    print("------------------ Installing Soci -------------------------------")
    print(f"Installing SOCI v{SOCI_VERSION}...")
    
    # Download SOCI snapshotter
    url = f"https://github.com/awslabs/soci-snapshotter/releases/download/v{SOCI_VERSION}/soci-snapshotter-{SOCI_VERSION}-linux-amd64.tar.gz"
    filename = url.split('/')[-1]
    
    print("  Downloading SOCI snapshotter...")
    run_command(['wget', url])
    
    # Extract specific binaries directly to system path
    print("  Installing SOCI binaries...")
    run_command(['tar', '-C', '/usr/local/bin', '-xvf', filename, 'soci', 'soci-snapshotter-grpc'])
    os.remove(filename)

def install_stargz():
    """
    Install StarGZ snapshotter.
    
    StarGZ (Stargz/eStargz) is Google's container image format
    that provides lazy loading capabilities similar to Nydus.
    """
    print("------------------ Installing (e)StarGZ -------------------------------")
    print(f"Installing StarGZ v{STARGZ_VERSION}...")
    
    # Download StarGZ snapshotter
    url = f"https://github.com/containerd/stargz-snapshotter/releases/download/v{STARGZ_VERSION}/stargz-snapshotter-v{STARGZ_VERSION}-linux-amd64.tar.gz"
    filename = url.split('/')[-1]
    
    print("  Downloading StarGZ snapshotter...")
    run_command(['wget', url])
    
    # Extract specific binaries directly to system path
    print("  Installing StarGZ binaries...")
    run_command(['tar', '-C', '/usr/local/bin', '-xvf', filename, 'containerd-stargz-grpc', 'ctr-remote'])
    os.remove(filename)

def setup_systemd_services(snapshotters):
    """
    Create and start systemd services for specified snapshotters.

    Creates service files for each snapshotter daemon and starts them.
    This enables automatic startup and management via systemctl.

    Args:
        snapshotters: List of snapshotters to set up ('nydus', 'soci', 'stargz')
    """
    print("------------------ Setting up Snapshotter Services -------------------------------")

    services_to_start = []

    if 'nydus' in snapshotters:
        # Nydus Snapshotter service configuration
        print("  Creating Nydus Snapshotter service...")
        nydus_service = """[Unit]
Description=nydus snapshotter (fuse mode)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/containerd-nydus-grpc --nydusd-config /etc/nydus/nydusd-config.fusedev.json
Restart=always
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

        with open('/etc/systemd/system/nydus-snapshotter-fuse.service', 'w') as f:
            f.write(nydus_service)
        services_to_start.append('nydus-snapshotter-fuse.service')

    if 'soci' in snapshotters:
        # SOCI Snapshotter service configuration
        print("  Creating SOCI Snapshotter service...")
        soci_service = """[Unit]
Description=SOCI Snapshotter GRPC daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/soci-snapshotter-grpc
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""

        with open('/etc/systemd/system/soci-snapshotter-grpc.service', 'w') as f:
            f.write(soci_service)
        services_to_start.append('soci-snapshotter-grpc.service')

    if 'stargz' in snapshotters:
        # StarGZ Snapshotter service configuration
        print("  Creating StarGZ Snapshotter service...")
        stargz_service = """[Unit]
Description=Stargz Snapshotter daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/containerd-stargz-grpc
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""

        with open('/etc/systemd/system/stargz-snapshotter.service', 'w') as f:
            f.write(stargz_service)
        services_to_start.append('stargz-snapshotter.service')

    # Start all snapshotter services
    if services_to_start:
        print("  Starting snapshotter services...")
        for service in services_to_start:
            print(f"    Starting {service}...")
            run_command(['systemctl', 'start', service])

def setup_containerd(snapshotters):
    """
    Configure containerd to use the installed snapshotters.

    Creates containerd configuration that registers specified
    snapshotters as proxy plugins, then restarts containerd.

    Args:
        snapshotters: List of snapshotters to configure ('nydus', 'soci', 'stargz')
    """
    print("------------------ Setting up Containerd -------------------------------")

    # Ensure containerd configuration directory exists
    print("  Creating containerd configuration directory...")
    os.makedirs('/etc/containerd', exist_ok=True)

    # Build containerd configuration with proxy plugins for specified snapshotters
    containerd_config = "version = 2\n\n[proxy_plugins]\n"

    if 'soci' in snapshotters:
        containerd_config += """  [proxy_plugins.soci]
    type = "snapshot"
    address = "/run/soci-snapshotter-grpc/soci-snapshotter-grpc.sock"
"""

    if 'nydus' in snapshotters:
        containerd_config += """  [proxy_plugins.nydus]
    type = "snapshot"
    address = "/run/containerd-nydus/containerd-nydus-grpc.sock"
"""

    if 'stargz' in snapshotters:
        containerd_config += """  [proxy_plugins.stargz]
    type = "snapshot"
    address = "/run/containerd-stargz-grpc/containerd-stargz-grpc.sock"
    [proxy_plugins.stargz.exports]
      root = "/var/lib/containerd-stargz-grpc/"
"""

    # Write containerd configuration
    print("  Writing containerd configuration...")
    with open('/etc/containerd/config.toml', 'w') as f:
        f.write(containerd_config)

    # Restart containerd to apply new configuration
    print("  Restarting containerd service...")
    run_command(['systemctl', 'restart', 'containerd'])

def main():
    """
    Main installation orchestrator.

    Performs the complete installation sequence:
    1. Verify root privileges
    2. Install specified snapshotter components and dependencies
    3. Configure services and containerd integration
    4. Start all services

    Uses a temporary directory for downloads to avoid cluttering
    the current working directory.
    """
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Install container snapshotters for lazy-loading container images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Install only Nydus (default)
  sudo python3 install_snapshotters.py

  # Install all snapshotters
  sudo python3 install_snapshotters.py --snapshotters nydus,soci,stargz

  # Install Nydus and SOCI
  sudo python3 install_snapshotters.py --snapshotters nydus,soci
        """)

    parser.add_argument(
        "--snapshotters",
        default="nydus",
        help="Comma-separated list of snapshotters to install (nydus,soci,stargz). Default: nydus"
    )

    args = parser.parse_args()

    # Parse and validate snapshotters
    requested_snapshotters = [s.strip() for s in args.snapshotters.split(",")]
    valid_snapshotters = {"nydus", "soci", "stargz"}
    invalid_snapshotters = set(requested_snapshotters) - valid_snapshotters

    if invalid_snapshotters:
        print(f"Error: Invalid snapshotters: {invalid_snapshotters}")
        print(f"Valid options: {valid_snapshotters}")
        sys.exit(1)

    # Ensure script is run with root privileges
    check_root()

    snapshotter_names = ", ".join(requested_snapshotters)
    print("Starting container snapshotter installation...")
    print(f"Installing: {snapshotter_names}, nerdctl, and CNI plugins")
    print()

    # Use temporary directory for all downloads and extraction
    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = os.getcwd()
        os.chdir(tmpdir)

        try:
            # Install core container runtime tools first
            install_nerdctl()
            install_cni_plugins()

            # Install Nydus components if requested
            if 'nydus' in requested_snapshotters:
                install_nydus()
                install_nydus_snapshotter()
                test_nydus_installation()
                configure_nydus_snapshotter()

            # Install SOCI if requested
            if 'soci' in requested_snapshotters:
                install_soci()

            # Install StarGZ if requested
            if 'stargz' in requested_snapshotters:
                install_stargz()

            # Set up system integration for installed snapshotters
            setup_systemd_services(requested_snapshotters)
            setup_containerd(requested_snapshotters)

        finally:
            # Return to original directory
            os.chdir(original_dir)

    print()
    print("------------------ INSTALLATION COMPLETE -------------------")
    print(f"Installed snapshotters: {snapshotter_names}")
    print("You can now use nerdctl with --snapshotter flag to specify:")
    for snapshotter in requested_snapshotters:
        print(f"  --snapshotter={snapshotter}")

if __name__ == "__main__":
    main()
