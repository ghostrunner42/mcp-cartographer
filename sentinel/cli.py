"""CLI entry point — `sentinel`."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

err = Console(stderr=True)
out = Console()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="jarvis-suite")
def main():
    """Sentinel — ambient project health watcher."""


@main.command("run")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def cmd_run(path: str) -> None:
    """Collect health metrics for PATH and save a snapshot."""
    from sentinel.metrics import collect
    from sentinel.watcher import save, write_flags
    from sentinel.reporter import render_snapshot

    target = Path(path).resolve()

    with err.status("[cyan]Collecting metrics…[/cyan]"):
        snap = collect(target)

    dest = save(snap, snap.project_name)
    render_snapshot(snap, out)
    err.print(f"\n[green]✓ Saved to {dest}[/green]")
    flags_written = write_flags(snap)
    if flags_written:
        err.print(f"[yellow]⚑ {len(flags_written)} flag(s) written for cue[/yellow]")


@main.command("report")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def cmd_report(path: str) -> None:
    """Show health trend report for PATH."""
    from sentinel.watcher import load_history
    from sentinel.reporter import render_report

    project_name = Path(path).resolve().name
    history = load_history(project_name)
    render_report(history, out)


@main.command("status")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def cmd_status(path: str) -> None:
    """Show the latest saved snapshot for PATH."""
    from sentinel.watcher import latest
    from sentinel.reporter import render_snapshot

    project_name = Path(path).resolve().name
    snap = latest(project_name)
    if snap is None:
        err.print(
            f"[yellow]No snapshot found for '{project_name}'. "
            "Run [bold]sentinel run[/bold] first.[/yellow]"
        )
        sys.exit(1)
    render_snapshot(snap, out)


@main.command("install")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
def cmd_install(path: str) -> None:
    """Install a daily cron job that runs sentinel for PATH."""
    abs_path = Path(path).resolve()
    log_file = Path.home() / ".local" / "share" / "sentinel.log"

    cron_entry = (
        f"0 9 * * 1-5 cd {abs_path} && sentinel run "
        f">> {log_file} 2>&1"
    )

    # Read existing crontab
    rc, existing = _read_crontab()
    if rc != 0 and existing.strip():
        err.print(f"[yellow]Warning: crontab -l exited {rc}[/yellow]")

    # Check for duplicate
    if str(abs_path) in existing and "sentinel run" in existing:
        out.print(
            f"[yellow]A sentinel cron entry for [bold]{abs_path}[/bold] "
            "already exists.[/yellow]"
        )
        return

    new_crontab = existing.rstrip("\n") + "\n" + cron_entry + "\n"

    # Write back
    try:
        proc = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            err.print(f"[red]Failed to write crontab: {proc.stderr}[/red]")
            sys.exit(1)
    except FileNotFoundError:
        err.print("[red]crontab command not found.[/red]")
        sys.exit(1)

    out.print(f"[green]✓ Cron job installed for [bold]{abs_path}[/bold][/green]")
    out.print(f"  Schedule: [bold]0 9 * * 1-5[/bold] (weekdays at 09:00)")
    out.print(f"  Log:      {log_file}")
    out.print(f"\n  Entry:\n  [dim]{cron_entry}[/dim]")


def _read_crontab() -> tuple:
    """Return (returncode, stdout) from crontab -l."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        return (result.returncode, result.stdout)
    except FileNotFoundError:
        return (1, "")
