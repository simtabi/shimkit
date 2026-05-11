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

FROM python:${PYTHON_VERSION}-slim AS builder
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip build \
 && python -m build --wheel --outdir /wheel

FROM python:${PYTHON_VERSION}-slim AS runtime
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

ENTRYPOINT ["shimkit"]
CMD ["--help"]
