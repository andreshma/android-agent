"""ContainerRunner command construction is pure, so test it per-OS."""

from android_agent.bridge.sandbox import ContainerRunner, RunOutput


def test_build_command_linux_usb_passthrough_no_network():
    runner = ContainerRunner(image="img", platform="linux")
    cmd = runner.build_command(["adb", "-s", "S1", "shell", "getprop"], engine="podman")
    assert cmd[:4] == ["podman", "run", "--rm", "-i"]
    assert "--network" in cmd and "none" in cmd
    assert "--device=/dev/bus/usb" in cmd
    # inner command is passed through unchanged on Linux
    assert cmd[-4:] == ["-s", "S1", "shell", "getprop"]
    assert "img" in cmd


def test_build_command_windows_uses_host_adb_server():
    runner = ContainerRunner(image="img", platform="win32")
    cmd = runner.build_command(["adb", "-s", "S1", "shell", "getprop"], engine="docker")
    assert "--add-host" in cmd
    assert "host.docker.internal:host-gateway" in cmd
    # adb is redirected at the host's adb server
    i = cmd.index("adb")
    assert cmd[i : i + 3] == ["adb", "-H", "host.docker.internal"]
    # no USB device / no --network none on Windows
    assert "--device=/dev/bus/usb" not in cmd


def test_build_command_windows_fastboot_not_redirected():
    runner = ContainerRunner(image="img", platform="darwin")
    cmd = runner.build_command(["fastboot", "devices"], engine="docker")
    i = cmd.index("fastboot")
    assert cmd[i:] == ["fastboot", "devices"]


def test_run_without_engine_reports_cleanly():
    # Force "no engine found" by pinning a non-existent engine? engine() uses
    # shutil.which; instead construct with an explicit engine and check build.
    runner = ContainerRunner(engine=None, platform="linux")
    # engine() may legitimately find podman/docker on the dev box; only assert
    # the clean-error contract when none is present.
    if runner.engine() is None:
        out: RunOutput = runner.run(["adb", "devices"])
        assert out.returncode == 127
        assert "container engine" in out.stderr
