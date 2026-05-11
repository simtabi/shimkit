# Distributing shimkit as a container image

shimkit ships a multi-stage `Dockerfile` (root of the repo). This
document covers building, publishing to GitHub Container Registry
(GHCR) and Docker Hub, and the CI workflow that automates it.

For Python publication see [`PYPI_SETUP.md`](PYPI_SETUP.md).
For the full release flow see [`installer/RELEASE.md`](installer/RELEASE.md).

## Why publish a container

- Zero-install try-out: `docker run --rm ghcr.io/simtabi/shimkit doctor`
- Hermetic CI usage — no surprises from the runner's Python version
- Reproducible — same image yields same behaviour everywhere

## Building locally

```bash
# single-arch, fast — for development
docker build -t shimkit:dev .
docker run --rm shimkit:dev version           # → 0.1.0
docker run --rm shimkit:dev doctor

# Multi-arch — requires docker buildx (usually pre-installed)
docker buildx create --use --name shimkit-builder
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag shimkit:dev \
  --load \
  .
```

`--load` only works for single-arch builds; for multi-arch use `--push`
to push directly to a registry.

The image is ~150 MB (python:3.12-slim base + curl/git/shimkit). The
final stage uses a non-root user `shimkit` with a real home directory
so `shimkit config edit` can write `~/.config/shimkit/shimkit.json`.

## Publishing to GHCR (recommended)

GitHub Container Registry is free for public images, uses the same
auth as the rest of the repo, and is the canonical home for OSS
release artifacts hosted on GitHub.

### One-time setup

1. Make sure the repo has **Settings → Actions → General →
   Workflow permissions** set to "Read and write permissions". The
   release workflow needs `packages: write`.
2. (Optional) Link the package to the repo for automatic visibility/
   permission inheritance: <https://github.com/simtabi?tab=packages> →
   shimkit package → **Package settings** → **Connect repository** →
   `simtabi/shimkit`.

### CI step (add to `.github/workflows/release.yml`)

```yaml
  publish-ghcr:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      packages: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/simtabi/shimkit
          tags: |
            type=ref,event=tag
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=raw,value=latest,enable={{is_default_branch}}
      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

This block can be appended to the existing `release.yml`. It runs after
`build` (the Python wheel build), independently of PyPI publish and
the Homebrew tap bump.

`docker/metadata-action` derives sensible tags from the git tag:

| Git tag  | Image tags                                                    |
|----------|---------------------------------------------------------------|
| v0.1.0   | `ghcr.io/simtabi/shimkit:v0.1.0`, `:0.1.0`, `:0.1`, `:latest` |
| v1.2.3   | `ghcr.io/simtabi/shimkit:v1.2.3`, `:1.2.3`, `:1.2`, `:latest` |

`:latest` only updates on the default branch — feature-branch tag pushes
won't accidentally clobber it.

### End-user pull

```bash
docker pull ghcr.io/simtabi/shimkit:latest
docker run --rm ghcr.io/simtabi/shimkit:latest version
docker run --rm -v "$HOME/.config/shimkit:/home/shimkit/.config/shimkit" \
  ghcr.io/simtabi/shimkit doctor
```

Mounting `~/.config/shimkit` lets the container see the user's override
file. Without it, the container uses only the bundled defaults — fine
for one-shot commands.

## Publishing to Docker Hub (optional, secondary)

Docker Hub is more familiar to some users than GHCR, but it has stricter
rate limits for anonymous pulls and requires manual account/repo
management.

### One-time setup

1. Create a Docker Hub account at <https://hub.docker.com>.
2. Create the repo: <https://hub.docker.com/repositories/simtabi> →
   **Create repository** → name `shimkit`, public.
3. Generate an access token: **Account Settings → Personal access
   tokens** → New token, scope **Read, Write, Delete**. Copy it.
4. Add the secret to GitHub: `simtabi/shimkit` → **Settings → Secrets
   and variables → Actions** → `DOCKERHUB_TOKEN` (token) and
   `DOCKERHUB_USERNAME` (your Docker Hub username).

### CI step

Either duplicate the `publish-ghcr` job with Docker Hub credentials, or
extend it to push to both registries:

```yaml
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: |
            ghcr.io/simtabi/shimkit
            simtabi/shimkit
          tags: |
            type=semver,pattern={{version}}
            type=raw,value=latest,enable={{is_default_branch}}
      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
```

`docker/metadata-action` deduplicates the image list; one build, two
registries.

## Verifying the published image

```bash
docker run --rm --pull=always ghcr.io/simtabi/shimkit version
docker run --rm --pull=always ghcr.io/simtabi/shimkit doctor

# Show the image manifest (size, layers, arch)
docker manifest inspect ghcr.io/simtabi/shimkit:latest

# Confirm multi-arch:
docker buildx imagetools inspect ghcr.io/simtabi/shimkit:latest
```

## Troubleshooting

### `denied: permission_denied` when pushing to ghcr.io

The workflow doesn't have `packages: write`. Add it to the job-level
`permissions:` block (see the YAML above).

### Image is 500+ MB

Check `.dockerignore` is picking up; the bundled `.dockerignore`
excludes `.git`, `.venv`, `dist`, tests, and other non-runtime files.
Also confirm you're using `python:3.12-slim`, not `python:3.12` — the
slim variant is ~120 MB smaller.

### `multiple platforms feature is currently not supported for docker driver`

```bash
docker buildx create --use --name shimkit-builder
```

The default `docker` driver only builds single-arch. `buildx` with a
new builder uses the `docker-container` driver which supports
multi-arch.

### `manifest unknown` when pulling

Probably the image was pushed to a different registry than you're
pulling from. GHCR images live at `ghcr.io/simtabi/shimkit`, Docker
Hub at `simtabi/shimkit` (or `docker.io/simtabi/shimkit`). Make sure
the host prefix matches.

## References

- Dockerfile syntax: <https://docs.docker.com/engine/reference/builder/>
- docker/build-push-action: <https://github.com/docker/build-push-action>
- docker/metadata-action: <https://github.com/docker/metadata-action>
- GHCR docs: <https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry>
