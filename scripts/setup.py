#!/usr/bin/env python3
"""
FastPull Setup Script

Installs fastpull CLI and configures containerd with Nydus snapshotter.
"""

import argparse
import os
import shutil
import subprocess
import sys


FASTPULL_CLI = "/usr/local/bin/fastpull"
FASTPULL_LIB = "/usr/local/lib/fastpull"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_CLI = os.path.join(SCRIPT_DIR, "fastpull-cli.py")
SOURCE_LIB = os.path.join(SCRIPT_DIR, "fastpull")


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

    if os.path.exists(nydus_path):
        print(f"✓ Nydus already installed at {nydus_path}")
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

# Create config directory
mkdir -p /etc/nydus

# Create Nydus config
cat > /etc/nydus/config.json <<'EOF'
{
  "device": {
    "backend": {
      "type": "registry",
      "config": {
        "scheme": "https"
      }
    },
    "cache": {
      "type": "blobcache",
      "config": {
        "work_dir": "/var/lib/nydus/cache"
      }
    }
  },
  "mode": "direct",
  "digest_validate": false,
  "iostats_files": false,
  "enable_xattr": true,
  "fs_prefetch": {
    "enable": true,
    "threads_count": 4
  }
}
EOF

# Create cache directory
mkdir -p /var/lib/nydus/cache

# Create systemd service
cat > /etc/systemd/system/fastpull.service <<'EOF'
[Unit]
Description=FastPull - Nydus Snapshotter
After=containerd.service
Requires=containerd.service

[Service]
Type=notify
ExecStart=/usr/local/bin/containerd-nydus-grpc \
    --config-path /etc/nydus/config.json \
    --daemon-mode shared \
    --log-level info \
    --root /var/lib/nydus \
    --address /run/nydus/nydus-snapshotter.sock \
    --nydusd-path /usr/local/bin/nydusd \
    --log-to-stdout
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF

# Create socket directory
mkdir -p /run/nydus

# Enable and start service
systemctl daemon-reload
systemctl enable fastpull.service
systemctl start fastpull.service

echo "✓ Nydus snapshotter installed and started"
"""

    try:
        result = run_command(install_script, shell=True, capture_output=True)
        print("✓ Nydus snapshotter installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install Nydus: {e}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
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
    address = "/run/nydus/nydus-snapshotter.sock"

[plugins."io.containerd.grpc.v1.cri".containerd]
  snapshotter = "nydus"
  disable_snapshot_annotations = false
"""

    with open(config_file, 'w') as f:
        f.write(config_content)

    print(f"✓ Created containerd config at {config_file}")

    # Restart containerd service
    print("Restarting containerd service...")
    run_command(["systemctl", "restart", "containerd.service"], check=False)

    return True


def install_cli():
    """Install fastpull CLI and library to /usr/local."""
    print("\n" + "="*60)
    print("Installing FastPull CLI")
    print("="*60)

    # Check if source exists
    if not os.path.exists(SOURCE_CLI):
        print(f"✗ Source CLI not found: {SOURCE_CLI}")
        return False

    if not os.path.exists(SOURCE_LIB):
        print(f"✗ Source library not found: {SOURCE_LIB}")
        return False

    try:
        # Copy the fastpull module directory
        if os.path.exists(FASTPULL_LIB):
            shutil.rmtree(FASTPULL_LIB)
        shutil.copytree(SOURCE_LIB, FASTPULL_LIB)
        print(f"✓ Installed fastpull library to {FASTPULL_LIB}")

        # Copy and rename CLI script
        shutil.copy2(SOURCE_CLI, FASTPULL_CLI)
        os.chmod(FASTPULL_CLI, 0o755)
        print(f"✓ Installed fastpull CLI to {FASTPULL_CLI}")

        return True
    except Exception as e:
        print(f"✗ Failed to install fastpull: {e}")
        return False


def verify_installation():
    """Verify fastpull installation."""
    print("\n" + "="*60)
    print("Verifying Installation")
    print("="*60)

    # Check CLI
    if not os.path.exists(FASTPULL_CLI):
        print(f"✗ fastpull CLI not found at {FASTPULL_CLI}")
        return False

    # Test CLI
    try:
        result = run_command([FASTPULL_CLI, '--version'], capture_output=True)
        print(f"✓ fastpull CLI: {result.stdout.strip()}")
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

        if os.path.exists(FASTPULL_CLI):
            os.remove(FASTPULL_CLI)
            print(f"✓ Removed {FASTPULL_CLI}")
            removed = True
        else:
            print(f"  {FASTPULL_CLI} not found")

        if os.path.exists(FASTPULL_LIB):
            shutil.rmtree(FASTPULL_LIB)
            print(f"✓ Removed {FASTPULL_LIB}")
            removed = True
        else:
            print(f"  {FASTPULL_LIB} not found")

        if removed:
            print("✓ Uninstall complete")
        return

    print("="*60)
    print("FastPull Setup")
    print("="*60)
    print("\nThis will install:")
    print("  • Containerd and nerdctl")
    print("  • Nydus snapshotter")
    print("  • FastPull CLI tool")
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
        print("\nSetup failed: Could not install CLI")
        sys.exit(1)

    # Verify
    verify_installation()

    print("\n" + "="*60)
    print("Setup Complete!")
    print("="*60)
    print("\n📋 Usage:")
    print("  fastpull run --help")
    print("  fastpull build --help")
    print("  fastpull push --help")
    print("\n🔍 Check services:")
    print("  systemctl status containerd")
    print("  systemctl status fastpull")
    print("\n📖 Example:")
    print("  sudo fastpull run --snapshotter nydus ubuntu:latest")
    print("="*60)


if __name__ == '__main__':
    main()
