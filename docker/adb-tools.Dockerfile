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
# Supply-chain note: for a reproducible, tamper-resistant build, pin the base
# image by digest instead of the tag, e.g.
#   FROM debian:bookworm-slim@sha256:<digest-from-your-pull>
# Resolve the digest on your own machine (`docker buildx imagetools inspect
# debian:bookworm-slim`) rather than trusting one copied from elsewhere.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends android-sdk-platform-tools \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user (audit M3 / Trivy DS002). USB device-node access is
# granted explicitly by ContainerRunner via --device, so root is not required.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin agent
USER 10001

# adb/fastboot are the only entry points; the concrete command is supplied by
# ContainerRunner at `run` time.
ENTRYPOINT []
