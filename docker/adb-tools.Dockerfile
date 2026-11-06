# Minimal image with Android platform-tools (adb + fastboot) for the
# ContainerRunner sandbox. Build it with:
#
#   docker build -t android-agent/adb-tools:latest -f docker/adb-tools.Dockerfile .
#   # or: podman build -t android-agent/adb-tools:latest -f docker/adb-tools.Dockerfile .
#
# The container is run with no network (Linux) or only the host gateway
# (Windows/macOS) by ContainerRunner, with --cap-drop=ALL, no-new-privileges,
# a read-only root filesystem and a non-root user; it never needs internet at
# runtime.
#
# Supply-chain: the base image is pinned by digest (audit M6) so the build is
# reproducible and not silently moved by a re-tag. Re-resolve it yourself with
# `docker buildx imagetools inspect debian:bookworm-slim` before bumping, rather
# than trusting a digest copied from elsewhere. (bookworm-slim, 2026-11-06.)
FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc

# platform-tools version caveat (audit M6): Debian ships adb/fastboot ~29.x,
# which lags Google's current platform-tools. It is fine for the read-only and
# simple flash flows here, but for a modern device (dynamic partitions /
# fastbootd, newer vbmeta) prefer `--runner local` with current platform-tools
# from https://developer.android.com/tools/releases/platform-tools. Container
# mode is EXPERIMENTAL and unverified on hardware (see docs/TESTING.md).
RUN apt-get update \
    && apt-get install -y --no-install-recommends adb fastboot \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user (audit M3 / Trivy DS002). USB device-node access is
# granted explicitly by ContainerRunner via --device, so root is not required.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin agent
USER 10001

# No background service runs in this one-shot tool container, so a healthcheck
# is not meaningful; declare NONE explicitly (Trivy DS026 / Checkov CKV_DOCKER_2
# — audit L11).
HEALTHCHECK NONE

# adb/fastboot are the only entry points; the concrete command is supplied by
# ContainerRunner at `run` time.
ENTRYPOINT []
