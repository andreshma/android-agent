"""android-agent command-line interface.

Owns all operator interaction: the consent gate, showing the plain-language
plan, the drill-down to raw commands, and the confirmation (with an extra
explicit yes for HIGH-risk plans). The heavy lifting lives in the orchestrator.
"""

from __future__ import annotations

import urllib.parse
from enum import Enum
from importlib.metadata import PackageNotFoundError, version

import httpx
import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from . import consent
from .audit_log import ActionLog
from .bridge import allowlist
from .bridge.allowlist import CommandDenied
from .bridge.device import Bridge
from .bridge.sandbox import ContainerRunner, LocalRunner
from .capabilities.flash import FlashTargetMismatch
from .config import Config
from .llm.factory import is_hosted, make_llm
from .models import Mission, Plan, RiskLevel
from .orchestrator import DeviceModeError, Orchestrator, PlanRejected, require_mode

app = typer.Typer(
    help="LLM-driven agent to audit, optimize, flash and unlock YOUR OWN Android device.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,  # never render locals (could leak an API key)
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        try:
            v = version("android-agent")
        except PackageNotFoundError:  # pragma: no cover - always installed in practice
            v = "unknown"
        console.print(f"android-agent {v}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed version and exit.",
    ),
) -> None:
    """LLM-driven agent for YOUR OWN Android device."""


class RunnerKind(str, Enum):
    local = "local"
    container = "container"


# Typer Option for --runner, shared by the commands. Enum-validated (an unknown
# value errors instead of silently falling back), default from the env/config.
_RUNNER_OPT = typer.Option(
    None, "--runner", envvar="ANDROID_AGENT_RUNNER", help="Execution backend: local | container."
)


def _apply_runner(cfg: Config, runner: RunnerKind | None) -> Config:
    if runner is not None:
        cfg.runner = runner.value
    return cfg


def _build_bridge(cfg: Config) -> Bridge:
    # Fail-safe: only the exact 'container' string selects the sandbox; anything
    # else is rejected rather than silently running unsandboxed.
    if cfg.runner == "container":
        return Bridge(ContainerRunner())
    if cfg.runner != "local":
        console.print(f"[red]Unknown runner '{cfg.runner}'. Use 'local' or 'container'.[/]")
        raise typer.Abort()
    return Bridge(LocalRunner())


def _llm_kwargs(cfg: Config) -> dict:
    """Backend-specific kwargs so documented config actually reaches the LLM."""
    if cfg.llm_backend.lower() == "ollama":
        return {"model": cfg.ollama_model, "host": cfg.ollama_host}
    if cfg.llm_backend.lower() in {"anthropic", "claude"}:
        return {"model": cfg.anthropic_model}
    return {}


def _show_plan(plan: Plan, *, drill_down: bool = False) -> None:
    # ``drill_down`` is kept for compatibility, but the raw command is now shown
    # for EVERY step by default (audit M2): the operator should always be able
    # to see what will actually run, not only the LLM-authored description. All
    # dynamic text is escaped so device/LLM output can't inject Rich markup
    # (audit M3).
    console.print(Panel(escape(plan.summary), title=f"Plan · {plan.mission.value}", expand=False))
    table = Table(show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("What it does")
    table.add_column("Risk")
    table.add_column("Reversible")
    table.add_column("Command")
    for i, step in enumerate(plan.steps, 1):
        risk_style = {
            RiskLevel.NONE: "green",
            RiskLevel.LOW: "yellow",
            RiskLevel.HIGH: "bold red",
        }[step.risk]
        table.add_row(
            str(i),
            escape(step.human),
            f"[{risk_style}]{step.risk.value}[/]",
            "yes" if step.reversible else "no",
            escape(" ".join(step.command)),
        )
    console.print(table)


@app.command()
def devices(runner: RunnerKind | None = _RUNNER_OPT) -> None:
    """List connected devices (adb + fastboot)."""
    cfg = Config.from_env()
    cfg = _apply_runner(cfg, runner)
    bridge = _build_bridge(cfg)
    found = bridge.list_devices()
    if not found:
        console.print("[yellow]No devices detected.[/] Connect a device with USB debugging on.")
        return
    for d in found:
        console.print(f"• {d.serial} ({d.mode.value}) {d.model or ''}")


@app.command()
def run(
    mission: Mission = typer.Argument(..., help="audit | optimize | flash | unlock"),
    request: str = typer.Argument(..., help="What you want, in your own words."),
    serial: str = typer.Option(..., "--serial", "-s", help="Target device serial."),
    llm: str = typer.Option(None, help="Override LLM backend: ollama | anthropic"),
    drill_down: bool = typer.Option(False, "--drill-down", help="Show the raw commands too."),
    runner: RunnerKind | None = _RUNNER_OPT,
    log: bool = typer.Option(True, "--log/--no-log", help="Record actions to an audit log."),
) -> None:
    """Propose a plan for a mission, then run it after your confirmation."""
    cfg = Config.from_env()
    cfg = _apply_runner(cfg, runner)
    if llm:
        cfg.llm_backend = llm
    bridge = _build_bridge(cfg)

    # --- resolve the target device ---
    device = _resolve_or_abort(bridge, serial)
    _require_mode_or_abort(device, mission)
    _disclose_egress(cfg)
    action_log = ActionLog() if log else None
    device = _consent(device, serial, action_log)

    # --- phase 1: propose ---
    try:
        llm_impl = make_llm(cfg.llm_backend, **_llm_kwargs(cfg))
    except ImportError as exc:
        console.print(f"[bold red]{exc}[/]")
        raise typer.Abort() from exc
    orch = Orchestrator(llm_impl, bridge, log=action_log)
    if action_log:
        console.print(f"[dim]Logging actions to {action_log.path}[/]")
    console.print(f"[dim]Asking {llm_impl.name} to plan the '{mission.value}' mission…[/]")
    try:
        plan = orch.propose(device, mission, request)
    except (CommandDenied, PlanRejected) as exc:
        console.print(f"[bold red]Rejected the proposed plan:[/] {exc}")
        raise typer.Abort() from exc
    except (httpx.HTTPError, ConnectionError) as exc:
        console.print(
            f"[bold red]Could not reach the LLM backend ({llm_impl.name}):[/] {exc}\n"
            "Is the local model server running (Ollama), or the network reachable?"
        )
        raise typer.Abort() from exc
    except (ValueError, RuntimeError) as exc:
        # Malformed model output, truncation, or 'no emit_plan tool call'.
        console.print(f"[bold red]The model did not return a usable plan:[/] {exc}")
        raise typer.Abort() from exc
    _show_plan(plan, drill_down=drill_down)

    _confirm_and_run(orch, device, plan)


def _ollama_host_is_remote(cfg: Config) -> bool:
    """True if the configured Ollama host is not loopback, so device facts would
    leave this machine even on the "local" backend (audit M9)."""
    raw = (cfg.ollama_host or "").strip()
    parsed = urllib.parse.urlparse(raw if "://" in raw else "//" + raw)
    host = (parsed.hostname or "").lower()
    return host not in {"", "localhost", "127.0.0.1", "::1"}


def _disclose_egress(cfg: Config) -> None:
    """Warn the operator when the chosen backend sends device data off-machine."""
    if is_hosted(cfg.llm_backend):
        console.print(
            Panel(
                "You selected a HOSTED LLM backend "
                f"([bold]{escape(cfg.llm_backend)}[/]). Read-only device facts "
                "(model, product, installed package names, system properties) "
                "will be sent to that third-party API to plan this mission. Use "
                "the default [bold]ollama[/] backend on a local host to keep all "
                "device data on this machine.",
                title="Data leaves your machine",
                border_style="red",
            )
        )
    elif cfg.llm_backend.lower() == "ollama" and _ollama_host_is_remote(cfg):
        scheme = urllib.parse.urlparse(cfg.ollama_host).scheme or "http"
        cleartext = " The connection is plain HTTP (not encrypted)." if scheme == "http" else ""
        console.print(
            Panel(
                f"Your Ollama host [bold]{escape(cfg.ollama_host)}[/] is NOT this "
                "machine. Read-only device facts (model, product, installed "
                "package names, system properties) will be sent there to plan "
                f"this mission.{cleartext} Point OLLAMA_HOST at localhost to keep "
                "all device data on this machine.",
                title="Data leaves your machine",
                border_style="red",
            )
        )


def _consent(device, serial: str, log: ActionLog | None = None):
    """Show the consent gate and mark the device authorized, or abort."""
    console.print(Panel(consent.consent_prompt(), title="Before we start", border_style="red"))
    if not typer.confirm(f"Do you confirm the above for device {serial} and want to continue?"):
        raise typer.Abort()
    if log:
        log.consent_recorded(serial)
    return consent.grant(device)


def _confirm_and_run(orch: Orchestrator, device, plan: Plan) -> None:
    """Confirm a plan (extra yes for HIGH risk), execute it, and print results."""
    if not plan.steps:
        console.print("[green]Nothing to do.[/]")
        return
    if plan.max_risk is RiskLevel.HIGH:
        console.print(
            "[bold red]This plan contains HIGH-risk, irreversible steps (data may be erased).[/]"
        )
        # Show the repo-authored description and the exact command for every
        # HIGH step, so the operator confirms what will truly run rather than the
        # LLM's own wording (audit M2).
        for step in plan.steps:
            if step.risk is RiskLevel.HIGH:
                try:
                    desc = allowlist.description_for(step.command)
                except CommandDenied:  # pragma: no cover - plan is validated first
                    desc = "(unrecognized command)"
                console.print(
                    f"   [red]•[/] {escape(desc)}: [dim]{escape(' '.join(step.command))}[/]"
                )
        # Require the literal word "yes": typer.confirm would accept a bare "y",
        # so a piped `yes |` could auto-answer a destructive plan (audit L5).
        typed = typer.prompt("Type the word 'yes' to confirm you understand and want to proceed")
        if typed.strip().lower() != "yes":
            console.print("[yellow]Not confirmed; aborting.[/]")
            raise typer.Abort()
    if not typer.confirm("Run this plan now?"):
        raise typer.Abort()
    if orch.log:
        orch.log.plan_confirmed(device.serial, plan)
    results = orch.run(device, plan)
    for i, res in enumerate(results, 1):
        mark = "[green]ok[/]" if res.ok else "[red]failed[/]"
        console.print(f"{i}. {mark} — {escape(res.step.human)}")
        if not res.ok and res.error:
            console.print(f"   [red]{escape(res.error.strip())}[/]")
    skipped = len(plan.steps) - len(results)
    if skipped > 0:
        console.print(
            f"[yellow]Stopped after a failed step; {skipped} remaining step(s) "
            f"were skipped. The device may be in a partial state — do not power "
            f"it off; review the error above.[/]"
        )


def _resolve_or_abort(bridge: Bridge, serial: str):
    device = bridge.find_device(serial)
    if device is None:
        console.print(f"[red]Device {serial} not found.[/] Run 'android-agent devices' to list.")
        raise typer.Abort()
    return device


def _require_mode_or_abort(device, mission: Mission) -> None:
    try:
        require_mode(device, mission)
    except DeviceModeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Abort() from exc


@app.command()
def debloat(
    serial: str = typer.Option(..., "--serial", "-s", help="Target device serial."),
    drill_down: bool = typer.Option(False, "--drill-down", help="Show the raw commands too."),
    runner: RunnerKind | None = _RUNNER_OPT,
    log: bool = typer.Option(True, "--log/--no-log", help="Record actions to an audit log."),
) -> None:
    """Disable likely-bloatware apps (deterministic, no LLM; reversible)."""
    cfg = Config.from_env()
    cfg = _apply_runner(cfg, runner)
    bridge = _build_bridge(cfg)
    device = _resolve_or_abort(bridge, serial)
    _require_mode_or_abort(device, Mission.OPTIMIZE)
    action_log = ActionLog() if log else None
    device = _consent(device, serial, action_log)

    orch = Orchestrator(None, bridge, log=action_log)
    optimize = orch.capability(Mission.OPTIMIZE)
    plan = optimize.build_debloat_plan(device)  # type: ignore[attr-defined]
    # Validate the deterministic plan through the same gate as an LLM plan
    # (allowlist + mission + protected-package + authoritative risk) — audit H1.
    try:
        orch.validate(plan)
    except (CommandDenied, PlanRejected) as exc:
        console.print(f"[bold red]Rejected the plan:[/] {escape(str(exc))}")
        raise typer.Abort() from exc
    if action_log:
        action_log.plan_proposed(device.serial, plan)
    _show_plan(plan, drill_down=drill_down)
    _confirm_and_run(orch, device, plan)


@app.command("flash-rom")
def flash_rom(
    serial: str = typer.Option(..., "--serial", "-s", help="Target device serial (fastboot)."),
    product: str = typer.Option(..., "--product", help="Expected device product/codename."),
    image: list[str] = typer.Option(
        ..., "--image", help="partition=path, e.g. --image boot=boot.img (repeatable)."
    ),
    drill_down: bool = typer.Option(False, "--drill-down", help="Show the raw commands too."),
    runner: RunnerKind | None = _RUNNER_OPT,
    log: bool = typer.Option(True, "--log/--no-log", help="Record actions to an audit log."),
) -> None:
    """Flash ROM images in a verified, ordered, guarded walkthrough (HIGH risk).

    The device's product is verified against --product first; it refuses to
    flash on a mismatch. Ensure you have unlocked the bootloader and made a
    backup beforehand.
    """
    images: dict[str, str] = {}
    for item in image:
        if "=" not in item:
            console.print(f"[red]Bad --image '{item}'. Use partition=path.[/]")
            raise typer.Abort()
        part, path = item.split("=", 1)
        images[part.strip()] = path.strip()

    cfg = Config.from_env()
    cfg = _apply_runner(cfg, runner)
    bridge = _build_bridge(cfg)
    device = _resolve_or_abort(bridge, serial)
    _require_mode_or_abort(device, Mission.FLASH)
    action_log = ActionLog() if log else None
    device = _consent(device, serial, action_log)

    orch = Orchestrator(None, bridge, log=action_log)
    flash = orch.capability(Mission.FLASH)
    try:
        plan = flash.build_rom_flash_plan(device, product, images)  # type: ignore[attr-defined]
        # Validate the built plan before showing it, so a partition name the
        # allowlist rejects is caught here — not mid-flash after earlier
        # partitions were already written (audit H1).
        orch.validate(plan)
    except (FlashTargetMismatch, FileNotFoundError, ValueError, CommandDenied, PlanRejected) as exc:
        console.print(f"[bold red]Refusing to flash:[/] {escape(str(exc))}")
        raise typer.Abort() from exc
    if action_log:
        action_log.plan_proposed(device.serial, plan)
    _show_plan(plan, drill_down=drill_down)
    _confirm_and_run(orch, device, plan)


@app.command("log")
def show_log(
    serial: str = typer.Option(None, "--serial", "-s", help="Filter by device serial."),
    limit: int = typer.Option(20, help="Show the most recent N entries."),
    verify: bool = typer.Option(
        False, "--verify", help="Check the hash chain is intact and report the result."
    ),
) -> None:
    """Show the recorded action trail (what was proposed and what ran)."""
    log = ActionLog()
    if verify:
        # Integrity check: the hash chain detects a reordered, edited or removed
        # entry (audit L1). It cannot detect truncation of the tail on its own —
        # ship the log to append-only storage for that.
        if log.verify():
            console.print("[green]Action log integrity: OK[/] (hash chain intact).")
        else:
            console.print(
                "[bold red]Action log integrity: FAILED[/] — the hash chain is "
                "broken (an entry was reordered, edited or removed)."
            )
            raise typer.Exit(code=1)
    entries = list(log.read_entries(serial=serial))
    if not entries:
        console.print("[yellow]No logged actions yet.[/]")
        return
    table = Table(show_lines=False, title="Action log")
    table.add_column("When (UTC)")
    table.add_column("Device")
    table.add_column("Event")
    table.add_column("Detail")
    for e in entries[-limit:]:
        event = e.get("event")
        if event == "plan_proposed":
            detail = f"{e.get('mission')} · {e.get('steps')} steps · risk {e.get('max_risk')}"
        elif event == "plan_confirmed":
            detail = f"confirmed {e.get('mission')} · risk {e.get('max_risk')}"
        elif event == "consent_recorded":
            detail = "operator confirmed ownership/consent"
        elif event == "step_executed":
            mark = "[green]ok[/]" if e.get("ok") else "[red]fail[/]"
            detail = f"{mark} {escape(' '.join(e.get('command', [])))}"
        else:
            detail = ""
        table.add_row(
            escape((e.get("ts", "") or "")[:19]),
            escape(e.get("serial", "") or ""),
            escape(e.get("event", "") or ""),
            detail,
        )
    console.print(table)


if __name__ == "__main__":
    app()
