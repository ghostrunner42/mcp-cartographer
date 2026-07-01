"""Rich terminal and plain-text output."""
from __future__ import annotations
from pathlib import Path
from ghost.models import GhostReport, Confidence

from rich.console import Console
from rich.table import Table
from rich.rule import Rule
from rich.text import Text
from rich.panel import Panel
from rich import box

console = Console()


def _confidence_badge(c: Confidence) -> Text:
    if c == Confidence.HIGH:
        return Text("● HIGH  ", style="bold red")
    if c == Confidence.MEDIUM:
        return Text("● MED   ", style="yellow")
    return Text("● LOW   ", style="grey50")


def _kind_style(kind: str) -> str:
    return {"function": "cyan", "method": "blue", "class": "magenta", "variable": "white"}.get(kind, "white")


def render(report: GhostReport, root: Path, show_medium: bool = True) -> None:
    high = report.high_confidence
    medium = report.medium_confidence

    header = (
        f"[bold]{root.name}[/bold]   "
        f"[grey50]{report.scanned_files} files · "
        f"{report.total_symbols} symbols · "
        f"[red]{len(high)} dead[/red] · "
        f"[yellow]{len(medium)} suspect[/yellow][/grey50]"
    )
    console.print(Panel(header, title="[bold red]Ghost[/bold red]", border_style="red"))
    console.print()

    if not report.dead_symbols and not report.unreferenced_files:
        console.print("[green]✓ No dead code found.[/green]")
        return

    # --- Dead symbols table ---
    visible = high + (medium if show_medium else [])
    if visible:
        console.print(Rule("[bold]Dead Symbols[/bold]", style="red"))
        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold", expand=True)
        table.add_column("Conf", min_width=8, no_wrap=True)
        table.add_column("Kind", min_width=8, no_wrap=True)
        table.add_column("Symbol", min_width=20, no_wrap=True, overflow="ellipsis")
        table.add_column("Location", min_width=30, no_wrap=True, overflow="ellipsis")
        table.add_column("Reason", no_wrap=True, overflow="ellipsis")

        current_file = None
        for sym in visible:
            rel = sym.path.relative_to(root)
            loc = f"{rel}:{sym.line}"
            if sym.parent:
                display = f"{sym.parent}.{sym.name}"
            else:
                display = sym.name

            if sym.path != current_file:
                current_file = sym.path
                table.add_section()

            table.add_row(
                _confidence_badge(sym.confidence),
                Text(sym.kind, style=_kind_style(sym.kind)),
                Text(display, style="bold" if sym.confidence == Confidence.HIGH else ""),
                Text(loc, style="grey50"),
                Text(sym.reason, style="grey70"),
            )

        console.print(table)
        console.print()

    # --- Unreferenced files ---
    if report.unreferenced_files:
        console.print(Rule("[bold]Unreferenced Files[/bold]", style="yellow"))
        for uf in report.unreferenced_files:
            rel = uf.path.relative_to(root)
            console.print(f"  [yellow]●[/yellow] [bold]{rel}[/bold]  [grey50]{uf.reason}[/grey50]")
        console.print()

    # --- Summary ---
    total_dead = len(report.dead_symbols)
    pct = round(total_dead / report.total_symbols * 100) if report.total_symbols else 0
    console.print(
        f"[grey50]{total_dead} of {report.total_symbols} symbols appear dead "
        f"({pct}%) · {len(report.unreferenced_files)} unreferenced file(s)[/grey50]"
    )

    for w in report.warnings:
        console.print(f"[yellow]⚠  {w}[/yellow]")
