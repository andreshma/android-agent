"""android-agent command-line interface.

Owns all operator interaction: the consent gate, showing the plain-language
plan, the drill-down to raw commands, and the confirmation (with an extra
explicit yes for HIGH-risk plans). The heavy lifting lives in the orchestrator.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import consent
from .audit_log import ActionLog
from .bridge.device import Bridge
from .bridge.sandbox import ContainerRunner, LocalRunner
from .capabilities.flash import FlashTargetMismatch
from .config import Config
from .llm.factory import make_llm
from .models import Mission, Plan, RiskLevel
from .orchestrator import DeviceModeError, Orchestrator, require_mode

app = typer.Typer(
    help="LLM-driven agent to audit, optimize, flash and unlock YOUR OWN Android device.",
    no_args_is_help=True,
)
console = Console()


def _build_bridge(cfg: Config) -> Bridge:
    runner = ContainerRunner() if cfg.runner == "container" else LocalRunner()
    return Bridge(runner)


def _show_plan(plan: Plan, *, drill_down: bool) -> None:
    console.print(Panel(plan.summary, title=f"Plan · {plan.mission.value}", expand=False))
    table = Table(show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("What it does")
    table.add_column("Risk")
    table.add_column("Reversible")
    if drill_down:
        table.add_column("Command")
    for i, step in enumerate(plan.steps, 1):
        risk_style = {
            RiskLevel.NONE: "green",
            RiskLevel.LOW: "yellow",
            RiskLevel.HIGH: "bold red",
        }[step.risk]
        row = [
            str(i),
            step.human,
            f"[{risk_style}]{step.risk.value}[/]",
            "yes" if step.reversible else "no",
        ]
        if drill_down:
            row.append(" ".join(step.command))
        table.add_row(*row)
    console.print(table)


@app.command()
def devices(runner: str = typer.Option("local", help="local | container")) -> None:
    """List connected devices (adb + fastboot)."""
    cfg = Config.from_env()
    cfg.runner = runner
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
    runner: str = typer.Option("local", help="local | container"),
    log: bool = typer.Option(True, "--log/--no-log", help="Record actions to an audit log."),
) -> None:
    """Propose a plan for a mission, then run it after your confirmation."""
    cfg = Config.from_env()
    cfg.runner = runner
    if llm:
        cfg.llm_backend = llm
    bridge = _build_bridge(cfg)

    # --- resolve the target device ---
    device = _resolve_or_abort(bridge, serial)
    _require_mode_or_abort(device, mission)
    device = _consent(device, serial)

    # --- phase 1: propose ---
    llm_impl = make_llm(cfg.llm_backend)
    action_log = ActionLog() if log else None
    orch = Orchestrator(llm_impl, bridge, log=action_log)
    if action_log:
        console.print(f"[dim]Logging actions to {action_log.path}[/]")
    console.print(f"[dim]Asking {llm_impl.name} to plan the '{mission.value}' mission…[/]")
    plan = orch.propose(device, mission, request)
    _show_plan(plan, drill_down=drill_down)

    _confirm_and_run(orch, device, plan)


def _consent(device, serial: str):
    """Show the consent gate and mark the device authorized, or abort."""
    console.print(Panel(consent.consent_prompt(), title="Before we start", border_style="red"))
    if not typer.confirm(f"Do you confirm the above for device {serial} and want to continue?"):
        raise typer.Abort()
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
        if not typer.confirm("Type yes to confirm you understand and want to proceed"):
            raise typer.Abort()
    if not typer.confirm("Run this plan now?"):
        raise typer.Abort()
    for i, res in enumerate(orch.run(device, plan), 1):
        mark = "[green]ok[/]" if res.ok else "[red]failed[/]"
        console.print(f"{i}. {mark} — {res.step.human}")
        if not res.ok and res.error:
            console.print(f"   [red]{res.error.strip()}[/]")


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
    runner: str = typer.Option("local", help="local | container"),
    log: bool = typer.Option(True, "--log/--no-log", help="Record actions to an audit log."),
) -> None:
    """Disable likely-bloatware apps (deterministic, no LLM; reversible)."""
    cfg = Config.from_env()
    cfg.runner = runner
    bridge = _build_bridge(cfg)
    device = _resolve_or_abort(bridge, serial)
    _require_mode_or_abort(device, Mission.OPTIMIZE)
    device = _consent(device, serial)

    orch = Orchestrator(None, bridge, log=ActionLog() if log else None)
    optimize = orch.capability(Mission.OPTIMIZE)
    plan = optimize.build_debloat_plan(device)  # type: ignore[attr-defined]
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
    runner: str = typer.Option("local", help="local | container"),
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
    cfg.runner = runner
    bridge = _build_bridge(cfg)
    device = _resolve_or_abort(bridge, serial)
    _require_mode_or_abort(device, Mission.FLASH)
    device = _consent(device, serial)

    orch = Orchestrator(None, bridge, log=ActionLog() if log else None)
    flash = orch.capability(Mission.FLASH)
    try:
        plan = flash.build_rom_flash_plan(device, product, images)  # type: ignore[attr-defined]
    except FlashTargetMismatch as exc:
        console.print(f"[bold red]Refusing to flash:[/] {exc}")
        raise typer.Abort() from exc
    _show_plan(plan, drill_down=drill_down)
    _confirm_and_run(orch, device, plan)


@app.command("log")
def show_log(
    serial: str = typer.Option(None, "--serial", "-s", help="Filter by device serial."),
    limit: int = typer.Option(20, help="Show the most recent N entries."),
) -> None:
    """Show the recorded action trail (what was proposed and what ran)."""
    entries = list(ActionLog().read_entries(serial=serial))
    if not entries:
        console.print("[yellow]No logged actions yet.[/]")
        return
    table = Table(show_lines=False, title="Action log")
    table.add_column("When (UTC)")
    table.add_column("Device")
    table.add_column("Event")
    table.add_column("Detail")
    for e in entries[-limit:]:
        if e.get("event") == "plan_proposed":
            detail = f"{e.get('mission')} · {e.get('steps')} steps · risk {e.get('max_risk')}"
        else:
            ok = e.get("ok")
            mark = "[green]ok[/]" if ok else "[red]fail[/]"
            detail = f"{mark} {' '.join(e.get('command', []))}"
        table.add_row(
            (e.get("ts", "") or "")[:19],
            e.get("serial", "") or "",
            e.get("event", "") or "",
            detail,
        )
    console.print(table)


if __name__ == "__main__":
    app()
