"""
FastPull clean command - Remove local images and artifacts.
"""

import argparse
import subprocess
import sys
from typing import List


def add_parser(subparsers):
    """Add clean subcommand parser."""
    parser = subparsers.add_parser(
        'clean',
        help='Remove local images and artifacts',
        description='Clean up fastpull images and containers'
    )

    parser.add_argument(
        '--images',
        action='store_true',
        help='Remove all fastpull images'
    )
    parser.add_argument(
        '--containers',
        action='store_true',
        help='Remove stopped containers'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Remove all images and containers'
    )
    parser.add_argument(
        '--snapshotter',
        choices=['nydus', 'overlayfs', 'all'],
        default='all',
        help='Target specific snapshotter (default: all)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be removed without removing'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force removal without confirmation'
    )

    parser.set_defaults(func=clean_command)
    return parser


def clean_command(args):
    """Execute the clean command."""
    # If no specific target, clean all
    if not args.images and not args.containers and not args.all:
        print("Please specify what to clean: --images, --containers, or --all")
        sys.exit(1)

    if args.all:
        args.images = True
        args.containers = True

    # Determine which snapshotters to clean
    snapshotters = ['nydus', 'overlayfs'] if args.snapshotter == 'all' else [args.snapshotter]

    # Clean containers first
    if args.containers:
        clean_containers(snapshotters, args.dry_run, args.force)

    # Clean images
    if args.images:
        clean_images(snapshotters, args.dry_run, args.force)


def clean_containers(snapshotters: List[str], dry_run: bool = False, force: bool = False):
    """
    Remove stopped containers.

    Args:
        snapshotters: List of snapshotters to target
        dry_run: If True, only show what would be removed
        force: If True, skip confirmation
    """
    print("\n=== Cleaning Containers ===")

    for snapshotter in snapshotters:
        # Get all containers (including stopped ones)
        result = subprocess.run(
            ['sudo', 'nerdctl', '--snapshotter', snapshotter, 'ps', '-a', '-q'],
            capture_output=True,
            text=True
        )

        container_ids = result.stdout.strip().split('\n') if result.stdout.strip() else []

        if not container_ids:
            print(f"[{snapshotter}] No containers to clean")
            continue

        print(f"[{snapshotter}] Found {len(container_ids)} container(s)")

        if dry_run:
            print(f"[{snapshotter}] Would remove {len(container_ids)} container(s)")
            for cid in container_ids:
                print(f"  - {cid}")
            continue

        # Confirm removal
        if not force:
            response = input(f"Remove {len(container_ids)} container(s) for {snapshotter}? [y/N]: ")
            if response.lower() != 'y':
                print(f"[{snapshotter}] Skipped")
                continue

        # Remove containers
        for cid in container_ids:
            subprocess.run(
                ['sudo', 'nerdctl', '--snapshotter', snapshotter, 'rm', '-f', cid],
                capture_output=True
            )

        print(f"[{snapshotter}] Removed {len(container_ids)} container(s)")


def clean_images(snapshotters: List[str], dry_run: bool = False, force: bool = False):
    """
    Remove all images.

    Args:
        snapshotters: List of snapshotters to target
        dry_run: If True, only show what would be removed
        force: If True, skip confirmation
    """
    print("\n=== Cleaning Images ===")

    for snapshotter in snapshotters:
        # Get all images
        result = subprocess.run(
            ['sudo', 'nerdctl', '--snapshotter', snapshotter, 'images', '-q'],
            capture_output=True,
            text=True
        )

        image_ids = result.stdout.strip().split('\n') if result.stdout.strip() else []

        if not image_ids:
            print(f"[{snapshotter}] No images to clean")
            continue

        print(f"[{snapshotter}] Found {len(image_ids)} image(s)")

        if dry_run:
            print(f"[{snapshotter}] Would remove {len(image_ids)} image(s)")
            # Show image details
            result = subprocess.run(
                ['sudo', 'nerdctl', '--snapshotter', snapshotter, 'images'],
                capture_output=True,
                text=True
            )
            print(result.stdout)
            continue

        # Confirm removal
        if not force:
            response = input(f"Remove {len(image_ids)} image(s) for {snapshotter}? [y/N]: ")
            if response.lower() != 'y':
                print(f"[{snapshotter}] Skipped")
                continue

        # Remove images
        subprocess.run(
            ['sudo', 'nerdctl', '--snapshotter', snapshotter, 'rmi', '-f'] + image_ids,
            capture_output=True
        )

        print(f"[{snapshotter}] Removed {len(image_ids)} image(s)")

    print("\n=== Cleanup Complete ===\n")
