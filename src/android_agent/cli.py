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
from .config import Config
from .llm.factory import make_llm
from .models import Mission, Plan, RiskLevel
from .orchestrator import Orchestrator

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
    device = bridge.find_device(serial)
    if device is None:
        console.print(f"[red]Device {serial} not found.[/] Run 'android-agent devices' to list.")
        raise typer.Abort()

    # --- consent gate ---
    console.print(Panel(consent.consent_prompt(), title="Before we start", border_style="red"))
    if not typer.confirm(f"Do you confirm the above for device {serial} and want to continue?"):
        raise typer.Abort()
    device = consent.grant(device)

    # --- phase 1: propose ---
    llm_impl = make_llm(cfg.llm_backend)
    action_log = ActionLog() if log else None
    orch = Orchestrator(llm_impl, bridge, log=action_log)
    if action_log:
        console.print(f"[dim]Logging actions to {action_log.path}[/]")
    console.print(f"[dim]Asking {llm_impl.name} to plan the '{mission.value}' mission…[/]")
    plan = orch.propose(device, mission, request)
    _show_plan(plan, drill_down=drill_down)

    # --- confirmation (HIGH risk needs an explicit second yes) ---
    if plan.max_risk is RiskLevel.HIGH:
        console.print(
            "[bold red]This plan contains HIGH-risk, irreversible steps (data may be erased).[/]"
        )
        if not typer.confirm("Type yes to confirm you understand and want to proceed"):
            raise typer.Abort()
    if not typer.confirm("Run this plan now?"):
        raise typer.Abort()

    # --- phase 2: execute ---
    results = orch.run(device, plan)
    for i, res in enumerate(results, 1):
        mark = "[green]ok[/]" if res.ok else "[red]failed[/]"
        console.print(f"{i}. {mark} — {res.step.human}")
        if not res.ok and res.error:
            console.print(f"   [red]{res.error.strip()}[/]")


if __name__ == "__main__":
    app()
