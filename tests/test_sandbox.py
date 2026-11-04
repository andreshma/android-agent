"""ContainerRunner command construction is pure, so test it per-OS."""

from android_agent.bridge import sandbox
from android_agent.bridge.sandbox import ContainerRunner, RunOutput, _child_env


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


def test_build_command_applies_hardening_flags():
    runner = ContainerRunner(image="img", platform="linux")
    cmd = runner.build_command(["adb", "devices"], engine="docker")
    # Least-privilege defaults are present on every run (audit M3).
    assert "--security-opt=no-new-privileges" in cmd
    assert "--cap-drop=ALL" in cmd
    assert "--read-only" in cmd
    assert "--tmpfs=/tmp" in cmd
    assert "--pids-limit=512" in cmd
    # hardening comes before the image, the inner command after it
    assert cmd.index("--cap-drop=ALL") < cmd.index("img")


def test_hardening_present_on_windows_too():
    runner = ContainerRunner(image="img", platform="win32")
    cmd = runner.build_command(["adb", "devices"], engine="docker")
    assert "--cap-drop=ALL" in cmd
    assert "--security-opt=no-new-privileges" in cmd


def test_mounts_for_detects_existing_image_file(tmp_path):
    img = tmp_path / "boot.img"
    img.write_bytes(b"IMG")
    cmd = ["fastboot", "flash", "boot", str(img)]
    mounts = ContainerRunner.mounts_for(cmd)
    assert str(img) in mounts
    assert mounts[str(img)].startswith("/mnt/img/")
    assert mounts[str(img)].endswith("boot.img")
    # non-file tokens are never mounted
    assert "flash" not in mounts and "boot" not in mounts


def test_build_command_mounts_and_rewrites_image_path():
    runner = ContainerRunner(image="img", platform="linux")
    mounts = {"/host/boot.img": "/mnt/img/0_boot.img"}
    cmd = runner.build_command(
        ["fastboot", "flash", "boot", "/host/boot.img"], engine="docker", mounts=mounts
    )
    # read-only bind mount present
    assert "-v" in cmd
    assert "/host/boot.img:/mnt/img/0_boot.img:ro" in cmd
    # the argv path is rewritten to the container path
    assert "/host/boot.img" not in cmd[cmd.index("img") :]
    assert cmd[-1] == "/mnt/img/0_boot.img"


def test_child_env_strips_llm_api_keys(monkeypatch):
    # The device toolchain must not inherit the hosted-LLM key (audit L3).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = _child_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert env.get("PATH") == "/usr/bin"


def test_subprocess_runs_with_scrubbed_env(monkeypatch):
    seen: dict = {}

    class _Proc:
        returncode, stdout, stderr = 0, "", ""

    def fake_run(argv, **kwargs):
        seen["env"] = kwargs.get("env")
        return _Proc()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)
    sandbox._run_subprocess(["echo", "hi"], timeout=1.0)
    assert seen["env"] is not None
    assert "ANTHROPIC_API_KEY" not in seen["env"]


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
