#!/usr/bin/env python3
"""
FastPull - Accelerate AI/ML container startup with lazy-loading snapshotters.

Main CLI entry point for the unified fastpull command.
"""

import argparse
import sys

from . import __version__, run, build, quickstart, clean


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='fastpull',
        description='FastPull - Accelerate AI/ML container startup with lazy-loading snapshotters',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run container with benchmarking
  fastpull run --snapshotter nydus --image myapp:latest-nydus \\
    --benchmark-mode readiness --readiness-endpoint http://localhost:8080/health -p 8080:8080

  # Build and push Docker and Nydus images
  fastpull build --image-path ./app --image myapp:v1 --format docker,nydus

For more information, visit: https://github.com/tensorfuse/fastpull
        """
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(
        dest='command',
        title='commands',
        description='Available fastpull commands',
        help='Command to execute'
    )

    # Add subcommands
    run.add_parser(subparsers)
    build.add_parser(subparsers)
    quickstart.add_parser(subparsers)
    clean.add_parser(subparsers)

    # Parse arguments
    args = parser.parse_args()

    # If no command specified, print help
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute the command
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
