# Minimal image with Android platform-tools (adb + fastboot) for the
# ContainerRunner sandbox. Build it with:
#
#   docker build -t android-agent/adb-tools:latest -f docker/adb-tools.Dockerfile .
#   # or: podman build -t android-agent/adb-tools:latest -f docker/adb-tools.Dockerfile .
#
# The container is run with no network (Linux) or only the host gateway
# (Windows/macOS) by ContainerRunner; it never needs internet at runtime.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends android-sdk-platform-tools \
    && rm -rf /var/lib/apt/lists/*

# adb/fastboot are the only entry points; the concrete command is supplied by
# ContainerRunner at `run` time.
ENTRYPOINT []
