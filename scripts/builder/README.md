# Container-Based Image Builder

Builds container images using `buildctl` in a containerized environment. Produces both normal OCI and Nydus-optimized images.

## Features

- **Registry-agnostic**: Works with AWS ECR, Google Artifact Registry, Docker Hub, or any OCI registry
- **No local dependencies**: All build tools run inside a container
- **Two image formats**: Builds both normal OCI and Nydus images in one go
- **Direct push**: Images pushed directly to registry via buildctl

## Architecture

```
Host (authenticated) → Builder Container (buildctl + nydus-image) → Registry
```

- **Host**: Authenticates to registry, mounts build context and docker config
- **Builder Container**: Runs buildctl to build and push images
- **No Docker daemon dependency**: buildctl pushes directly to registries

## Prerequisites

1. **Docker** installed on host (no other dependencies needed!)
2. **Authenticated to your registry** before running:

```bash
# AWS ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789.dkr.ecr.us-east-1.amazonaws.com

# Google Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Docker Hub
docker login
```

## Usage

```bash
docker run --rm --privileged \
  -v /path/to/build-context:/workspace:ro \
  -v ~/.docker/config.json:/root/.docker/config.json:ro \
  tensorfuse/fastpull-builder:latest \
  <image:tag>
```

### Examples

**AWS ECR:**
```bash
docker run --rm --privileged \
  -v ./my-app:/workspace:ro \
  -v ~/.docker/config.json:/root/.docker/config.json:ro \
  tensorfuse/fastpull-builder:latest \
  123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:latest
```

**Google Artifact Registry:**
```bash
docker run --rm --privileged \
  -v ./my-app:/workspace:ro \
  -v ~/.docker/config.json:/root/.docker/config.json:ro \
  tensorfuse/fastpull-builder:latest \
  us-central1-docker.pkg.dev/my-project/my-repo/my-app:v1.0
```

**Docker Hub:**
```bash
docker run --rm --privileged \
  -v ./my-app:/workspace:ro \
  -v ~/.docker/config.json:/root/.docker/config.json:ro \
  tensorfuse/fastpull-builder:latest \
  docker.io/username/my-app:latest
```

**No tag (defaults to :latest):**
```bash
docker run --rm --privileged \
  -v ./my-app:/workspace:ro \
  -v ~/.docker/config.json:/root/.docker/config.json:ro \
  tensorfuse/fastpull-builder:latest \
  my-registry.com/my-app
```

**Custom Dockerfile:**
```bash
docker run --rm --privileged \
  -v ./my-app:/workspace:ro \
  -v ~/.docker/config.json:/root/.docker/config.json:ro \
  -e DOCKERFILE=Dockerfile.custom \
  tensorfuse/fastpull-builder:latest \
  my-registry.com/my-app:latest
```

## Output

The script builds and pushes two images:
- `<image>:<tag>` - Normal OCI image
- `<image>:<tag>-fastpull` - Fastpull-optimized image

## Files

- `Dockerfile` - Builder container definition (builds from nydusaccelerator/buildkit fork)
- `build.sh` - Build script that runs inside container (entrypoint)
- `README.md` - This file

## Technical Details

### Buildkit with Nydus Support
The Dockerfile builds `buildkitd` and `buildctl` from the [nydusaccelerator/buildkit](https://github.com/nydusaccelerator/buildkit) fork with the `-tags=nydus` flag, which enables Nydus compression support. The standard moby/buildkit does not include this functionality.

### Components
- **buildkitd/buildctl**: Compiled from nydusaccelerator/buildkit fork
- **nydus-image**: v2.3.6 binary (set via `NYDUS_BUILDER` env var)
- **buildctl-daemonless.sh**: Wrapper that runs buildkitd in rootless mode

## How It Works

1. **Pull builder image**: Downloads `tensorfuse/fastpull-builder:latest` from Docker Hub
2. **Mount context**: Your build context is mounted read-only into `/workspace`
3. **Mount auth**: `~/.docker/config.json` is mounted for registry authentication
4. **Run buildctl**: Builds normal OCI image with `buildctl-daemonless.sh`
5. **Run buildctl again**: Builds Fastpull image with Nydus compression
6. **Direct push**: Both images pushed directly to registry

## Troubleshooting

**"Error: Docker config not found"**
- Run registry authentication command first (see Prerequisites)

**"Error: Build context path does not exist"**
- Check that `--context` points to a valid directory

**"Error: Dockerfile not found"**
- Ensure Dockerfile exists in context directory
- Or specify custom name with `--dockerfile`

**Build fails with authentication error:**
- Re-authenticate to your registry
- Check that `~/.docker/config.json` contains valid credentials

**"permission denied" errors:**
- Builder container runs with `--privileged` flag (required for buildkit)
- Ensure Docker is running with appropriate permissions

## Comparison with Original build_push.py

| Feature | Original | Container-Based |
|---------|----------|-----------------|
| Dependencies | Requires nerdctl, nydusify, soci, stargz locally | All tools in container |
| Registry | AWS ECR or GAR | Any OCI registry |
| Formats | normal, nydus, soci, estargz | normal, nydus |
| Push method | nerdctl/docker | buildctl (direct) |
| Portability | Requires snapshotter setup | Runs anywhere Docker runs |
