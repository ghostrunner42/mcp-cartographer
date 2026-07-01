"""Rich terminal renderer."""
from __future__ import annotations
from pathlib import Path
from cartographer.models import CartographyResult, ModuleNode
from cartographer.graph import top_by_in_degree

from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich import box
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns
from rich.rule import Rule

console = Console()


def _heat_bar(score: float, width: int = 10) -> Text:
    filled = round(score * width)
    bar = "█" * filled + "░" * (width - filled)
    if score >= 0.7:
        color = "red"
    elif score >= 0.4:
        color = "yellow"
    elif score >= 0.1:
        color = "green"
    else:
        color = "grey50"
    return Text(bar, style=color)


def _complexity_badge(cc: float) -> Text:
    if cc == 0:
        return Text("  —  ", style="grey50")
    if cc <= 5:
        return Text(f" {cc:4.1f} ", style="green")
    if cc <= 10:
        return Text(f" {cc:4.1f} ", style="yellow")
    return Text(f" {cc:4.1f} ", style="red bold")


def _lang_badge(lang: str) -> Text:
    colors = {
        "Python": "blue", "JavaScript": "yellow", "TypeScript": "cyan",
        "Go": "bright_cyan", "Rust": "red", "Ruby": "red",
        "Java": "yellow", "C": "white", "C++": "white",
        "Shell": "green", "Markdown": "grey70",
    }
    color = colors.get(lang, "white")
    return Text(lang, style=color)


def _render_header(result: CartographyResult) -> None:
    lang_str = " · ".join(
        f"{lang} ({count})"
        for lang, count in sorted(result.languages.items(), key=lambda x: -x[1])[:6]
    )
    git_str = "yes" if result.has_git else "no"
    summary = (
        f"[bold]{result.repo_name}[/bold]   "
        f"[grey50]{result.scanned_files} files · "
        f"{result.total_lines:,} lines · "
        f"{result.dominant_language} · "
        f"git: {git_str}[/grey50]"
    )
    console.print(Panel(summary, title="[bold cyan]Repo Cartographer[/bold cyan]", border_style="cyan"))
    console.print(f"[grey50]Languages: {lang_str}[/grey50]")
    console.print()


def _render_module_table(result: CartographyResult) -> None:
    console.print(Rule("[bold]Module Map[/bold]", style="cyan"))

    width = console.width or 100
    show_todo = width >= 100
    show_cc = width >= 90
    heat_width = 10 if result.has_git else 0
    # fixed cols: Module(18) Lang(10) Files(6) Lines(8) + separators(~16) + heat
    reserved = 18 + 10 + 6 + 8 + 16 + heat_width
    if show_cc:
        reserved += 6
    if show_todo:
        reserved += 5
    summary_width = max(16, width - reserved)

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Module", min_width=14, max_width=24, no_wrap=True, overflow="ellipsis")
    table.add_column("Lang", min_width=8, max_width=12, no_wrap=True, overflow="ellipsis")
    table.add_column("Files", justify="right", min_width=5, no_wrap=True)
    table.add_column("Lines", justify="right", min_width=7, no_wrap=True)
    if show_cc:
        table.add_column("CC", justify="center", min_width=4, no_wrap=True)
    if show_todo:
        table.add_column("TODO", justify="right", min_width=4, no_wrap=True)
    if result.has_git:
        table.add_column("Heat", min_width=10, no_wrap=True)
    table.add_column("Summary", min_width=16, max_width=summary_width, no_wrap=True, overflow="ellipsis")

    for node in sorted(result.modules, key=lambda n: (-n.heat_score, n.name)):
        heat = _heat_bar(node.heat_score) if result.has_git else None
        row = [
            Text(node.name, style="bold" if node.is_dir else ""),
            _lang_badge(node.language),
            str(node.total_files),
            f"{node.total_lines:,}",
        ]
        if show_cc:
            row.append(_complexity_badge(node.avg_complexity))
        if show_todo:
            row.append(str(node.todo_count) if node.todo_count else "—")
        if result.has_git:
            row.append(heat)
        row.append(Text(node.summary, style="grey70"))
        table.add_row(*row)

    console.print(table)
    console.print()


def _render_hot_files(result: CartographyResult) -> None:
    if not result.hot_files or not result.has_git:
        return
    console.print(Rule("[bold]Hottest Files[/bold] [grey50](most commits in last 200)[/grey50]", style="yellow"))
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold yellow")
    table.add_column("File", min_width=40)
    table.add_column("Heat", min_width=12)
    table.add_column("Score", justify="right", min_width=6)

    for path, score in result.hot_files[:15]:
        try:
            rel = str(path.relative_to(result.root))
        except ValueError:
            rel = str(path)
        table.add_row(rel, _heat_bar(score), f"{score:.3f}")

    console.print(table)
    console.print()


def _render_dependency_graph(result: CartographyResult) -> None:
    if not result.dependency_edges:
        return
    console.print(Rule("[bold]Dependency Insights[/bold]", style="blue"))

    top = top_by_in_degree(result.dependency_edges, n=8)
    if top:
        console.print("[bold]Most imported modules:[/bold]")
        for mod, count in top:
            bar = "▪" * min(count, 20)
            console.print(f"  [cyan]{mod}[/cyan]  [grey50]{bar}[/grey50]  ({count})")
        console.print()

    if result.circular_deps:
        n = len(result.circular_deps)
        console.print(f"[bold red]⚠  {n:,} circular dependency cycle(s) detected[/bold red]")
        for cycle in result.circular_deps[:3]:
            heads = [Path(p).name for p in cycle[:3]]
            tail = f" → … (+{len(cycle) - 3} more)" if len(cycle) > 3 else " → …"
            console.print(f"  [red]{' → '.join(heads)}[/red][grey50]{tail}[/grey50]")
        if n > 3:
            console.print(f"  [grey50]… and {n - 3:,} more[/grey50]")
        console.print()


def _render_warnings(result: CartographyResult) -> None:
    for w in result.warnings:
        console.print(f"[yellow]⚠  {w}[/yellow]")


def render(result: CartographyResult) -> None:
    _render_header(result)
    _render_module_table(result)
    _render_hot_files(result)
    _render_dependency_graph(result)
    _render_warnings(result)
    console.print(f"[grey50]Scanned {result.root}[/grey50]")
