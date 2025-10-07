# FastPull CLI - Quick Reference

The new unified `fastpull` command-line interface for building and running containers with lazy-loading snapshotters.

## Installation

The setup script automatically detects your OS (Ubuntu/Debian/RHEL/CentOS/Fedora) and installs all dependencies including `python3-venv` and `wget`.

```bash
# Full installation (containerd + Nydus + CLI)
sudo python3 scripts/setup.py

# Install only CLI (if containerd/Nydus already installed)
sudo python3 scripts/setup.py --cli-only

# Verify installation
fastpull --version
```

**Supported Package Managers:**
- `apt` (Ubuntu/Debian)
- `yum` (RHEL/CentOS 7)
- `dnf` (RHEL/CentOS 8+/Fedora)

## Commands

### `fastpull quickstart` - Quick Benchmark Comparisons

Run pre-configured benchmarks to quickly compare snapshotter performance.

#### Available Workloads

**TensorRT:**
```bash
sudo fastpull quickstart tensorrt
sudo fastpull quickstart tensorrt --output-dir ./results
```

**vLLM:**
```bash
sudo fastpull quickstart vllm
sudo fastpull quickstart vllm --output-dir ./results
```

**SGLang:**
```bash
sudo fastpull quickstart sglang
sudo fastpull quickstart sglang --output-dir ./results
```

Each quickstart automatically:
1. Runs with FastPull mode (Nydus snapshotter)
2. Runs with Normal mode (OverlayFS snapshotter)
3. Measures readiness benchmarking for startup performance
4. **Auto-cleans containers and images after completion**

---

### `fastpull run` - Run Containers with Benchmarking

Run containers with FastPull (Nydus) or Normal (OverlayFS) mode.

#### Basic Usage

```bash
# Run with FastPull mode (default, auto-adds -nydus suffix to tag)
fastpull run myapp:latest

# Run with Normal mode (OverlayFS, no suffix)
fastpull run --mode normal myapp:latest

# Run with GPU support
fastpull run myapp:latest --gpus all -p 8080:8080
```

#### Benchmarking Modes

**Readiness Mode** - Poll HTTP endpoint until 200 response:
```bash
fastpull run \
  myapp:latest \
  --benchmark-mode readiness \
  --readiness-endpoint http://localhost:8080/health \
  -p 8080:8080
```

**Completion Mode** - Wait for container to exit:
```bash
fastpull run \
  myapp:latest \
  --benchmark-mode completion
```

**Export Metrics** - Save results to JSON:
```bash
fastpull run \
  myapp:latest \
  --benchmark-mode readiness \
  --readiness-endpoint http://localhost:8080/health \
  --output-json results.json \
  -p 8080:8080
```

#### Supported Flags

- `--mode` - Run mode: nydus (default, adds -nydus suffix), normal (overlayfs, no suffix)
- `IMAGE` - Container image to run (positional argument, required)
- `--benchmark-mode` - Options: none, completion, readiness (default: none)
- `--readiness-endpoint` - HTTP endpoint for health checks
- `--output-json` - Export metrics to JSON file
- `--name` - Container name
- `-p, --publish` - Publish ports (repeatable)
- `-e, --env` - Environment variables (repeatable)
- `-v, --volume` - Bind mount volumes (repeatable)
- `--gpus` - GPU devices (e.g., "all")
- `--rm` - Auto-remove container on exit
- `-d, --detach` - Run in background

**Note:** Any additional arguments after the image are passed through to nerdctl.

#### Pass-through Examples

```bash
# Custom entrypoint
fastpull run myapp:latest --entrypoint /bin/bash

# Command override
fastpull run myapp:latest python script.py --arg1 value1

# Additional nerdctl flags
fastpull run myapp:latest --privileged --network host
```

---

### `fastpull build` - Build and Push Images in Multiple Formats

Build Docker and snapshotter-optimized images, then push to registry.

#### Basic Usage

```bash
# Build Docker and Nydus (default) and push
fastpull build --dockerfile-path ./app --repository-url myapp:latest

# Build specific formats
fastpull build \
  --dockerfile-path ./app \
  --repository-url myapp:v1 \
  --format docker,nydus
```

#### Build Options

```bash
# No cache
fastpull build --dockerfile-path ./app --repository-url myapp:latest --no-cache

# With build arguments
fastpull build \
  --dockerfile-path ./app \
  --repository-url myapp:latest \
  --build-arg VERSION=1.0 \
  --build-arg ENV=prod

# Custom Dockerfile
fastpull build \
  --dockerfile-path ./app \
  --repository-url myapp:latest \
  --dockerfile Dockerfile.prod
```

#### Supported Flags

- `--dockerfile-path` - Path to Dockerfile directory (required)
- `--repository-url` - Full image reference including registry, repository, and tag (required)
- `--format` - Comma-separated formats: docker, nydus (default: docker,nydus)
- `--no-cache` - Build without cache
- `--build-arg` - Build arguments (repeatable)
- `--dockerfile` - Dockerfile name (default: Dockerfile)

**Note:** Images are automatically pushed to the registry after building.

---

### `fastpull clean` - Remove Local Images and Artifacts

Clean up local container images and stopped containers.

#### Basic Usage

```bash
# Clean all images and containers (requires confirmation)
fastpull clean --all

# Clean only images
fastpull clean --images

# Clean only stopped containers
fastpull clean --containers

# Target specific snapshotter
fastpull clean --all --snapshotter nydus
fastpull clean --all --snapshotter overlayfs

# Dry run to see what would be removed
fastpull clean --all --dry-run

# Force removal without confirmation
fastpull clean --all --force
```

#### Supported Flags

- `--images` - Remove all images
- `--containers` - Remove stopped containers
- `--all` - Remove both images and containers
- `--snapshotter` - Target specific snapshotter: nydus, overlayfs, all (default: all)
- `--dry-run` - Show what would be removed without removing
- `--force` - Force removal without confirmation

---

## Complete Workflow Example

```bash
# 1. Build and push images in multiple formats
fastpull build \
  --dockerfile-path ./my-app \
  --repository-url 123456789012.dkr.ecr.us-east-1.amazonaws.com/myapp:v1.0 \
  --format docker,nydus

# 2. Run with benchmarking (FastPull mode, auto-adds -nydus suffix)
fastpull run \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/myapp:v1.0 \
  --benchmark-mode readiness \
  --readiness-endpoint http://localhost:8000/health \
  --output-json benchmark-results.json \
  -p 8000:8000 \
  --gpus all
```

---

## Benchmarking Metrics

When using `--benchmark-mode`, fastpull tracks:

1. **Time to Container Start** - Using `ctr events` to monitor container lifecycle
2. **Time to Readiness/Completion**:
   - **Readiness mode**: Polls HTTP endpoint until 200 response
   - **Completion mode**: Waits for container to exit

Example output:

**FastPull mode (Nydus):**
```
==================================================
FASTPULL BENCHMARK SUMMARY
==================================================
Time to Container Start: 2.34s
Time to Readiness:       45.67s
Total Elapsed Time:      48.01s
==================================================
```

**Normal mode (OverlayFS):**
```
==================================================
NORMAL BENCHMARK SUMMARY
==================================================
Time to Container Start: 13.64s
Time to Readiness:       387.77s
Total Elapsed Time:      387.77s
==================================================
```

---

## Uninstallation

```bash
# Remove fastpull CLI
sudo python3 scripts/setup.py --uninstall
```

---

## Backwards Compatibility

The original scripts remain unchanged and continue to work:
- `scripts/build_push.py`
- `scripts/benchmark/test-bench-vllm.py`
- `scripts/benchmark/test-bench-sglang.py`
- `scripts/install_snapshotters.py`

---

## Service Management

After installation, the Nydus snapshotter service is renamed to `fastpull.service`:

```bash
# Check status
systemctl status fastpull.service

# Restart service
sudo systemctl restart fastpull.service

# View logs
journalctl -u fastpull.service -f
```
