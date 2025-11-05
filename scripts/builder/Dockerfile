# Build stage: Compile buildkit with Nydus support
FROM golang:1.21-alpine AS buildkit-builder

# Install build dependencies
RUN apk add --no-cache git make

# Clone nydusaccelerator/buildkit fork
ARG BUILDKIT_VERSION=nydus-compression-type-enhance
RUN git clone --depth 1 --branch ${BUILDKIT_VERSION} \
    https://github.com/nydusaccelerator/buildkit.git /buildkit

WORKDIR /buildkit

# Build buildkitd and buildctl with Nydus support
RUN go build -tags=nydus -o ./bin/buildkitd ./cmd/buildkitd && \
    go build -o ./bin/buildctl ./cmd/buildctl

# Runtime stage
FROM alpine:latest

# Copy buildkit binaries with Nydus support
COPY --from=buildkit-builder /buildkit/bin/buildctl /usr/bin/buildctl
COPY --from=buildkit-builder /buildkit/bin/buildkitd /usr/bin/buildkitd

# Copy buildctl-daemonless.sh wrapper from moby/buildkit repo
ADD https://raw.githubusercontent.com/moby/buildkit/master/examples/buildctl-daemonless/buildctl-daemonless.sh /usr/bin/buildctl-daemonless.sh
RUN chmod +x /usr/bin/buildctl-daemonless.sh

# Install runtime dependencies
RUN apk add --no-cache \
    ca-certificates \
    curl \
    wget \
    iptables \
    fuse-overlayfs \
    containerd

# Install nydus-image binary (v2.3.6)
ARG NYDUS_VERSION=v2.3.6
RUN wget -O /tmp/nydus.tgz \
    "https://github.com/dragonflyoss/nydus/releases/download/${NYDUS_VERSION}/nydus-static-${NYDUS_VERSION}-linux-amd64.tgz" \
    && tar -xzf /tmp/nydus.tgz -C /tmp \
    && mv /tmp/nydus-static/nydus-image /usr/bin/nydus-image \
    && chmod +x /usr/bin/nydus-image \
    && rm -rf /tmp/nydus.tgz /tmp/nydus-static

# Set NYDUS_BUILDER environment variable (required for buildkit)
ENV NYDUS_BUILDER=/usr/bin/nydus-image

# Copy build script
COPY build.sh /usr/local/bin/build.sh
RUN chmod +x /usr/local/bin/build.sh

WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/build.sh"]
