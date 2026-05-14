# Container image for shimkit.
#
# Multi-stage: builder produces a wheel; final stage installs it into a
# minimal slim image with a non-root user. Multi-arch (amd64 + arm64)
# built by docker buildx — see DOCKER_SETUP.md.
#
# Usage:
#   docker run --rm ghcr.io/simtabi/shimkit:latest version
#   docker run --rm ghcr.io/simtabi/shimkit:latest doctor

ARG PYTHON_VERSION=3.12

# Base image is pinned by manifest digest so the build is reproducible.
# Dependabot's `docker` ecosystem watches this line and opens a PR when
# a new digest is published upstream.
# To refresh manually:
#   docker pull python:${PYTHON_VERSION}-slim
#   docker inspect --format='{{index .RepoDigests 0}}' python:${PYTHON_VERSION}-slim
FROM python:${PYTHON_VERSION}-slim@sha256:401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461 AS builder
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip build \
 && python -m build --wheel --outdir /wheel

FROM python:${PYTHON_VERSION}-slim@sha256:401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461 AS runtime
LABEL org.opencontainers.image.title="shimkit" \
      org.opencontainers.image.description="A toolkit of developer utilities" \
      org.opencontainers.image.source="https://github.com/simtabi/shimkit" \
      org.opencontainers.image.licenses="MIT"

# Runtime deps that shimkit shells out to. curl is needed by Brew.install_self,
# git for any future tool that touches repos.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheel/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl \
 && rm /tmp/*.whl

# Non-root user. ~/.config is writable so `shimkit config edit` works.
RUN useradd --create-home --shell /bin/bash shimkit
USER shimkit
WORKDIR /home/shimkit

# `shimkit version` is cheap, has no side effects, and validates that
# the entrypoint resolves — enough to decide image health for orchestrators.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["shimkit", "version"]

ENTRYPOINT ["shimkit"]
CMD ["--help"]
