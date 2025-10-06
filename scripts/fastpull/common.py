"""
Common utilities for fastpull commands.

Includes registry detection, authentication helpers, and shared functions.
"""

import re
import subprocess
from typing import Optional, Tuple


def detect_registry_type(image: str) -> str:
    """
    Auto-detect registry type from image URL.

    Args:
        image: Container image URL

    Returns:
        Registry type: 'ecr', 'gar', 'dockerhub', or 'unknown'
    """
    if 'dkr.ecr' in image or 'ecr.aws' in image:
        return 'ecr'
    elif 'pkg.dev' in image:
        return 'gar'
    elif 'docker.io' in image or '/' not in image or image.count('/') == 1:
        return 'dockerhub'
    return 'unknown'


def parse_ecr_url(image: str) -> Optional[Tuple[str, str, str]]:
    """
    Parse ECR image URL to extract account, region, and repository.

    Args:
        image: ECR image URL

    Returns:
        Tuple of (account_id, region, repository) or None if invalid
    """
    pattern = r'(\d+)\.dkr\.ecr\.([^.]+)\.amazonaws\.com/(.+)'
    match = re.match(pattern, image)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None


def parse_gar_url(image: str) -> Optional[Tuple[str, str, str]]:
    """
    Parse GAR image URL to extract location, project, and repository.

    Args:
        image: GAR image URL

    Returns:
        Tuple of (location, project_id, repository) or None if invalid
    """
    pattern = r'([^-]+)-docker\.pkg\.dev/([^/]+)/([^/]+)/(.+)'
    match = re.match(pattern, image)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None


def run_command(cmd: list, check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
    """
    Run a shell command with consistent error handling.

    Args:
        cmd: Command to run as list of strings
        check: Raise exception on non-zero exit code
        capture_output: Capture stdout/stderr

    Returns:
        CompletedProcess instance
    """
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture_output,
        text=True
    )


def get_snapshotter_binary(snapshotter: str) -> str:
    """
    Get the appropriate binary for the snapshotter.

    Args:
        snapshotter: Snapshotter type

    Returns:
        Binary name ('nerdctl' or 'docker')
    """
    # All snapshotters use nerdctl except for plain docker
    if snapshotter in ['docker', 'overlayfs']:
        return 'docker'
    return 'nerdctl'


def get_aws_account_id() -> Optional[str]:
    """
    Get AWS account ID from AWS CLI.

    Returns:
        Account ID or None if failed
    """
    try:
        result = subprocess.run(
            ['aws', 'sts', 'get-caller-identity', '--query', 'Account', '--output', 'text'],
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def get_aws_region() -> Optional[str]:
    """
    Get AWS region from AWS CLI configuration.

    Returns:
        Region or None if failed
    """
    try:
        result = subprocess.run(
            ['aws', 'configure', 'get', 'region'],
            check=True,
            capture_output=True,
            text=True
        )
        region = result.stdout.strip()
        return region if region else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
