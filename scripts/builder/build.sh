#!/bin/sh
set -e

# Usage: build.sh <image[:tag]>
# Example: build.sh my-registry.com/my-app:latest
# Example: build.sh my-registry.com/my-app (defaults to :latest)

if [ $# -lt 1 ]; then
    echo "Usage: $0 <image[:tag]>"
    echo "Example: $0 123456789.dkr.ecr.us-east-1.amazonaws.com/my-app:v1.0"
    echo "Example: $0 123456789.dkr.ecr.us-east-1.amazonaws.com/my-app (defaults to :latest)"
    exit 1
fi

IMAGE_WITH_TAG="$1"
DOCKERFILE="${DOCKERFILE:-Dockerfile}"
CONTEXT_PATH="${CONTEXT_PATH:-/workspace}"

# Parse image and tag (default to :latest if no tag provided)
if echo "$IMAGE_WITH_TAG" | grep -q ":"; then
    IMAGE_NAME="${IMAGE_WITH_TAG%:*}"
    TAG="${IMAGE_WITH_TAG##*:}"
else
    IMAGE_NAME="$IMAGE_WITH_TAG"
    TAG="latest"
fi

FULL_IMAGE="${IMAGE_NAME}:${TAG}"
FULL_IMAGE_FASTPULL="${IMAGE_NAME}:${TAG}-fastpull"

echo "=========================================="
echo "Building images for: ${IMAGE_NAME}"
echo "Tag: ${TAG}"
echo "Context: ${CONTEXT_PATH}"
echo "Dockerfile: ${DOCKERFILE}"
echo "=========================================="

# Build normal OCI image
echo ""
echo ">>> Building normal OCI image: ${FULL_IMAGE}"
echo ""
time buildctl-daemonless.sh build \
    --frontend dockerfile.v0 \
    --local context="${CONTEXT_PATH}" \
    --local dockerfile="${CONTEXT_PATH}" \
    --opt filename="${DOCKERFILE}" \
    --output type=image,name="${FULL_IMAGE}",push=true

echo ""
echo "✓ Normal OCI image built and pushed: ${FULL_IMAGE}"
echo ""

# Build Fastpull image
echo ""
echo ">>> Building Fastpull image: ${FULL_IMAGE_FASTPULL}"
echo ""
time buildctl-daemonless.sh build \
    --frontend dockerfile.v0 \
    --local context="${CONTEXT_PATH}" \
    --local dockerfile="${CONTEXT_PATH}" \
    --opt filename="${DOCKERFILE}" \
    --output type=image,name="${FULL_IMAGE_FASTPULL}",push=true,compression=nydus,force-compression=true,oci-mediatypes=true

echo ""
echo "✓ Fastpull image built and pushed: ${FULL_IMAGE_FASTPULL}"
echo ""

echo "=========================================="
echo "✓ Build complete!"
echo "  Normal:   ${FULL_IMAGE}"
echo "  Fastpull: ${FULL_IMAGE_FASTPULL}"
echo "=========================================="
