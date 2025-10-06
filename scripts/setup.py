#!/usr/bin/env python3
"""
FastPull Setup Script

Installs containerd, Nydus snapshotter, and FastPull CLI via pip.
"""

import argparse
import os
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
VENV_PATH = os.path.join(PROJECT_ROOT, '.venv')
FASTPULL_BIN = '/usr/local/bin/fastpull'


def run_command(cmd, check=True, capture_output=False, shell=False):
    """Run a command and return result."""
    try:
        if shell:
            result = subprocess.run(cmd, shell=True, check=check, capture_output=capture_output, text=True)
        else:
            result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
        return result
    except subprocess.CalledProcessError as e:
        if not check:
            return e
        raise


def check_root():
    """Check if running as root."""
    if os.geteuid() != 0:
        print("Error: This script must be run as root (use sudo)")
        sys.exit(1)


def install_containerd_nerdctl():
    """Install containerd and nerdctl."""
    print("\n" + "="*60)
    print("Installing Containerd & Nerdctl")
    print("="*60)

    # Check if already installed
    nerdctl_path = "/usr/local/bin/nerdctl"
    if os.path.exists(nerdctl_path):
        print(f"✓ nerdctl already installed at {nerdctl_path}")
        result = run_command([nerdctl_path, "--version"], capture_output=True)
        print(f"  {result.stdout.strip()}")
        return True

    print("\nInstalling containerd and nerdctl...")

    install_script = """
set -e

cd /tmp

# Remove old download if exists
rm -f /tmp/nerdctl-full.tar.gz

# Download nerdctl-full
NERDCTL_VERSION="1.7.3"
echo "Downloading nerdctl-full ${NERDCTL_VERSION}..."
wget -O /tmp/nerdctl-full.tar.gz https://github.com/containerd/nerdctl/releases/download/v${NERDCTL_VERSION}/nerdctl-full-${NERDCTL_VERSION}-linux-amd64.tar.gz

# Extract to /usr/local
echo "Extracting to /usr/local..."
tar -C /usr/local -xzf /tmp/nerdctl-full.tar.gz

# Enable and start containerd service
echo "Enabling containerd service..."
systemctl enable containerd
systemctl start containerd

# Clean up
rm -f /tmp/nerdctl-full.tar.gz

echo "✓ Containerd and nerdctl installed"
"""

    try:
        result = run_command(install_script, shell=True, capture_output=True)
        print("✓ Containerd and nerdctl installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install containerd: {e}")
        if e.stdout:
            print(f"stdout: {e.stdout}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        return False


def install_nydus():
    """Install Nydus snapshotter."""
    print("\n" + "="*60)
    print("Installing Nydus Snapshotter")
    print("="*60)

    nydus_path = "/usr/local/bin/containerd-nydus-grpc"
    service_path = "/etc/systemd/system/fastpull.service"

    # Check if binary exists
    if os.path.exists(nydus_path):
        print(f"✓ Nydus binary found at {nydus_path}")
        # Always recreate service and config (to ensure latest settings)
        print("Updating service and configuration...")
        create_nydus_service()
        return True

    install_script = """
set -e

NYDUS_VERSION="v2.3.6"
echo "Downloading Nydus snapshotter ${NYDUS_VERSION}..."

# Download Nydus
cd /tmp
wget -O nydus.tgz https://github.com/dragonflyoss/nydus/releases/download/${NYDUS_VERSION}/nydus-static-${NYDUS_VERSION}-linux-amd64.tgz

# Extract to /usr/local/bin
tar xzf nydus.tgz
mv nydus-static/* /usr/local/bin/
rm -rf nydus-static nydus.tgz

echo "✓ Nydus binaries installed"
"""

    try:
        result = run_command(install_script, shell=True, capture_output=True)
        print("✓ Nydus binaries installed successfully")

        # Now create the service (shared code)
        create_nydus_service()
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install Nydus: {e}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        return False


def create_nydus_service():
    """Create systemd service for Nydus snapshotter."""
    service_script = """
# Create systemd service
cat > /etc/systemd/system/fastpull.service <<'EOF'
[Unit]
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
EOF

# Create necessary directories
mkdir -p /etc/nydus
mkdir -p /var/lib/nydus/cache

# Create Nydus config if it doesn't exist
if [ ! -f /etc/nydus/nydusd-config.fusedev.json ]; then
cat > /etc/nydus/nydusd-config.fusedev.json <<'EOF'
{
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
  "amplify_io": 10485760,
  "fs_prefetch": {
    "enable": true,
    "threads_count": 16,
    "merging_size": 1048576,
    "prefetch_all": true
  }
}
EOF
fi

# Enable and start service
systemctl daemon-reload
systemctl enable fastpull.service
systemctl start fastpull.service

echo "✓ Nydus service created and started"
"""

    try:
        run_command(service_script, shell=True, capture_output=True)
        print("✓ Created and started fastpull.service")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to create service: {e}")
        return False


def configure_containerd_for_nydus():
    """Configure containerd to use Nydus snapshotter."""
    print("\nConfiguring containerd for Nydus...")

    config_dir = "/etc/containerd"
    config_file = os.path.join(config_dir, "config.toml")

    os.makedirs(config_dir, exist_ok=True)

    # Create containerd config with Nydus proxy plugin
    config_content = """version = 2

[proxy_plugins]
  [proxy_plugins.nydus]
    type = "snapshot"
    address = "/run/containerd-nydus/containerd-nydus-grpc.sock"

[plugins."io.containerd.grpc.v1.cri".containerd]
  snapshotter = "nydus"
  disable_snapshot_annotations = false
"""

    with open(config_file, 'w') as f:
        f.write(config_content)

    print(f"✓ Updated containerd config at {config_file}")

    # Restart fastpull service first
    print("Restarting fastpull service...")
    run_command(["systemctl", "restart", "fastpull.service"], check=False)

    # Then restart containerd service
    print("Restarting containerd service...")
    run_command(["systemctl", "restart", "containerd.service"], check=False)

    print("✓ Services restarted")

    return True


def install_cli():
    """Install fastpull CLI via pip in a venv."""
    print("\n" + "="*60)
    print("Installing FastPull CLI")
    print("="*60)

    try:
        # Create venv if it doesn't exist
        if not os.path.exists(VENV_PATH):
            print(f"Creating virtual environment at {VENV_PATH}...")
            result = run_command(['python3', '-m', 'venv', VENV_PATH], check=False, capture_output=True)
            if result.returncode != 0:
                print(f"✗ Failed to create venv: {result.stderr}")
                return False
            print(f"✓ Created virtual environment")

        # Get pip path in venv
        venv_pip = os.path.join(VENV_PATH, 'bin', 'pip')
        venv_python = os.path.join(VENV_PATH, 'bin', 'python3')

        # Install fastpull in venv
        print("Installing fastpull in virtual environment...")
        result = run_command([venv_pip, 'install', '-e', PROJECT_ROOT], check=False, capture_output=True)
        if result.returncode != 0:
            print(f"✗ Failed to install in venv: {result.stderr}")
            return False
        print("✓ Installed fastpull in virtual environment")

        # Create wrapper script in /usr/local/bin
        wrapper_script = f"""#!/bin/bash
# FastPull CLI wrapper script
# Activates venv and runs fastpull

exec {venv_python} -m scripts.fastpull.cli "$@"
"""

        print(f"Creating wrapper script at {FASTPULL_BIN}...")
        with open(FASTPULL_BIN, 'w') as f:
            f.write(wrapper_script)
        os.chmod(FASTPULL_BIN, 0o755)
        print(f"✓ Created fastpull command at {FASTPULL_BIN}")

        return True

    except Exception as e:
        print(f"✗ Failed to install fastpull: {e}")
        return False


def verify_installation():
    """Verify fastpull installation."""
    print("\n" + "="*60)
    print("Verifying Installation")
    print("="*60)

    # Test CLI
    try:
        result = run_command(['fastpull', '--version'], capture_output=True, check=False)
        if result.returncode == 0:
            print(f"✓ fastpull CLI: {result.stdout.strip()}")
        else:
            print(f"✗ fastpull CLI not found in PATH")
            print("Try running: hash -r (or restart your shell)")
            return False
    except Exception as e:
        print(f"✗ fastpull CLI test failed: {e}")
        return False

    # Check nerdctl
    nerdctl_path = "/usr/local/bin/nerdctl"
    if os.path.exists(nerdctl_path):
        try:
            result = run_command([nerdctl_path, "--version"], capture_output=True)
            print(f"✓ nerdctl: {result.stdout.strip().split()[2]}")
        except:
            print(f"  nerdctl found but version check failed")

    # Check containerd service
    try:
        result = run_command(["systemctl", "is-active", "containerd.service"], capture_output=True)
        if result.returncode == 0:
            print(f"✓ containerd service: active")
        else:
            print(f"  containerd service: {result.stdout.strip()}")
    except:
        print(f"  Could not check containerd service")

    # Check FastPull service
    try:
        result = run_command(["systemctl", "is-active", "fastpull.service"], capture_output=True)
        if result.returncode == 0:
            print(f"✓ fastpull service: active")
        else:
            print(f"  fastpull service: {result.stdout.strip()}")
    except:
        print(f"  Could not check fastpull service")

    return True


def main():
    """Main setup function."""
    parser = argparse.ArgumentParser(
        description='Install FastPull with containerd and Nydus snapshotter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full installation (containerd + Nydus + CLI)
  sudo python3 scripts/setup.py

  # Install only CLI (skip containerd/Nydus setup)
  sudo python3 scripts/setup.py --cli-only

  # Uninstall fastpull CLI
  sudo python3 scripts/setup.py --uninstall
"""
    )
    parser.add_argument(
        '--cli-only',
        action='store_true',
        help='Install only the fastpull CLI, skip containerd/Nydus setup'
    )
    parser.add_argument(
        '--uninstall',
        action='store_true',
        help='Uninstall fastpull CLI'
    )

    args = parser.parse_args()

    # Check root
    check_root()

    if args.uninstall:
        print("Uninstalling fastpull...")
        removed = False

        # Remove wrapper script
        if os.path.exists(FASTPULL_BIN):
            os.remove(FASTPULL_BIN)
            print(f"✓ Removed {FASTPULL_BIN}")
            removed = True

        # Remove venv
        if os.path.exists(VENV_PATH):
            import shutil
            shutil.rmtree(VENV_PATH)
            print(f"✓ Removed virtual environment at {VENV_PATH}")
            removed = True

        if removed:
            print("✓ Uninstall complete")
        else:
            print("✗ fastpull not found or already uninstalled")
        return

    print("="*60)
    print("FastPull Setup")
    print("="*60)

    if args.cli_only:
        print("\nThis will install:")
        print("  • FastPull CLI tool (via pip)")
        print()
    else:
        print("\nThis will install:")
        print("  • Containerd and nerdctl")
        print("  • Nydus snapshotter")
        print("  • FastPull CLI tool (via pip)")
        print()

    if not args.cli_only:
        # Install containerd and nerdctl
        if not install_containerd_nerdctl():
            print("\n⚠ Warning: Containerd installation failed")
            print("You can still install the CLI with --cli-only")
            sys.exit(1)

        # Install Nydus snapshotter
        if not install_nydus():
            print("\n⚠ Warning: Nydus installation failed")

        # Configure containerd for Nydus
        configure_containerd_for_nydus()

    # Install CLI
    if not install_cli():
        print("\nSetup incomplete: CLI installation failed")
        if not args.cli_only:
            print("Note: Snapshotters were installed successfully")
        sys.exit(1)

    # Verify
    verify_installation()

    print("\n" + "="*60)
    print("✅ Fastpull installed successfully on your VM")
    print("="*60)
    print("\n📋 Usage:")
    print("  fastpull --help")
    print("  fastpull run --help")
    print("  fastpull build --help")
    print("  fastpull quickstart --help")
    if not args.cli_only:
        print("\n🔍 Check services:")
        print("  systemctl status containerd")
        print("  systemctl status fastpull")
    print("\n📖 Example:")
    print("  fastpull quickstart tensorrt")
    print("="*60)


if __name__ == '__main__':
    main()
