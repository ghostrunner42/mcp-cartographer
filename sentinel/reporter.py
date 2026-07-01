"""Render health trends from saved snapshots."""
from __future__ import annotations
from typing import Optional

from sentinel.metrics import HealthSnapshot
from rich.console import Console
from rich.table import Table
from rich.rule import Rule
from rich.panel import Panel
from rich import box


def _score_color(score: int) -> str:
    if score >= 80:
        return "green"
    elif score >= 60:
        return "yellow"
    return "red"


def _delta_str(current: int, previous: Optional[int]) -> str:
    if previous is None:
        return "[dim]—[/dim]"
    diff = current - previous
    if diff > 0:
        return f"[green]+{diff}[/green]"
    elif diff < 0:
        return f"[red]{diff}[/red]"
    return "[dim]0[/dim]"


def render_report(history: list, console: Console) -> None:
    """Render a trend table for a list of HealthSnapshots (newest first)."""
    if not history:
        console.print(
            "[yellow]No history yet. Run [bold]sentinel run[/bold] first.[/yellow]"
        )
        return

    project_name = history[0].project_name
    oldest_date = history[-1].timestamp[:10]
    newest_date = history[0].timestamp[:10]

    console.print(Rule(f"[bold cyan]Sentinel Report — {project_name}[/bold cyan]"))
    console.print(
        f"[dim]History: {oldest_date} → {newest_date}  "
        f"({len(history)} snapshot(s))[/dim]\n"
    )

    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold white",
        expand=False,
    )
    table.add_column("Date", style="dim", min_width=10)
    table.add_column("Score", justify="right", min_width=6)
    table.add_column("Δ", justify="right", min_width=4)
    table.add_column("Tests", justify="center", min_width=10)
    table.add_column("Dead(H)", justify="right", min_width=7)
    table.add_column("Stale Deps", justify="right", min_width=10)
    table.add_column("Uncommitted", justify="right", min_width=11)

    prev_score: Optional[int] = None

    for i, snap in enumerate(history):
        color = _score_color(snap.score)
        score_str = f"[{color}]{snap.score}[/{color}]"
        delta = _delta_str(snap.score, prev_score)

        # Tests column
        if not snap.tests_found:
            tests_str = "[dim]—[/dim]"
        elif snap.tests_passed is not None or snap.tests_failed is not None:
            p = snap.tests_passed or 0
            f = snap.tests_failed or 0
            if f > 0:
                tests_str = f"[green]{p}✓[/green] [red]{f}✗[/red]"
            else:
                tests_str = f"[green]{p}✓[/green]"
        else:
            runner = snap.test_runner or "?"
            tests_str = f"[yellow]{runner}?[/yellow]"

        dead_str = (
            str(snap.dead_symbols_high)
            if snap.ghost_available and snap.dead_symbols_high is not None
            else "[dim]—[/dim]"
        )
        stale_str = (
            str(snap.stale_deps)
            if snap.drift_available and snap.stale_deps is not None
            else "[dim]—[/dim]"
        )
        uncommitted_str = str(snap.uncommitted_files)

        table.add_row(
            snap.timestamp[:10],
            score_str,
            delta,
            tests_str,
            dead_str,
            stale_str,
            uncommitted_str,
        )
        prev_score = snap.score

    console.print(table)

    # Warning panel if latest score dropped >10 from previous
    if len(history) >= 2:
        latest_score = history[0].score
        previous_score = history[1].score
        if previous_score - latest_score > 10:
            drop = previous_score - latest_score
            notes = "\n".join(f"  • {n}" for n in history[0].score_notes)
            console.print(
                Panel(
                    f"[bold red]Score dropped {drop} points[/bold red] "
                    f"({previous_score} → {latest_score})\n\n"
                    f"[yellow]Reasons:[/yellow]\n{notes}",
                    title="[red]Health Warning[/red]",
                    border_style="red",
                )
            )


def render_snapshot(snap: HealthSnapshot, console: Console) -> None:
    """Render a single snapshot with full metric breakdown."""
    color = _score_color(snap.score)

    console.print(Rule(f"[bold cyan]Sentinel — {snap.project_name}[/bold cyan]"))
    console.print(
        f"  [dim]Path:[/dim]      {snap.project_path}\n"
        f"  [dim]Captured:[/dim]  {snap.timestamp[:19].replace('T', ' ')} UTC\n"
    )

    # Score
    console.print(
        f"  [bold]Health Score:[/bold] [{color}]{snap.score}/100[/{color}]"
    )
    if snap.score_notes:
        for note in snap.score_notes:
            console.print(f"    [yellow]–[/yellow] {note}")
    else:
        console.print("    [green]No deductions — looking good![/green]")

    console.print()

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Metric", style="dim")
    table.add_column("Value")

    # Git
    table.add_row("Uncommitted files", str(snap.uncommitted_files))
    table.add_row("Days since commit", f"{snap.days_since_commit:.1f}")

    # Tests
    if snap.tests_found:
        runner = snap.test_runner or "unknown"
        if snap.tests_passed is not None or snap.tests_failed is not None:
            p = snap.tests_passed or 0
            f = snap.tests_failed or 0
            test_val = f"{p} passed, {f} failed ({runner})"
        else:
            test_val = f"found ({runner}, result unknown)"
        table.add_row("Tests", test_val)
    else:
        table.add_row("Tests", "[dim]not detected[/dim]")

    # Ghost
    if snap.ghost_available:
        table.add_row(
            "Dead code (high confidence)",
            f"{snap.dead_symbols_high} / {snap.dead_symbols_total} total",
        )
    else:
        table.add_row("Dead code", "[dim]ghost not available[/dim]")

    # Drift
    if snap.drift_available:
        table.add_row(
            "Stale deps / Vulnerable",
            f"{snap.stale_deps} / {snap.vulnerable_deps}",
        )
    else:
        table.add_row("Dependencies", "[dim]drift not available[/dim]")

    # File stats
    table.add_row("Python files", str(snap.py_file_count))
    table.add_row("TypeScript files", str(snap.ts_file_count))
    table.add_row("Total source lines", str(snap.total_lines))

    console.print(table)
