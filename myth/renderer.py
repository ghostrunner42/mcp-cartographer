"""Rich terminal rendering for Artifact."""
from __future__ import annotations
from myth.archaeologist import Artifact, FileCommit
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich import box
from datetime import datetime, timezone


def _stability_color(stability: str) -> str:
    return {"stable": "green", "active": "yellow", "volatile": "red"}.get(stability, "white")


def _fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _bar(count: int, max_count: int, width: int = 20) -> str:
    if max_count == 0:
        return ""
    filled = round((count / max_count) * width)
    return "█" * filled


def render(artifact: Artifact, console: Console) -> None:
    """Render the full archaeological report to the console."""
    stability_color = _stability_color(artifact.stability)
    born_date = _fmt_date(artifact.born_at) if artifact.born_at else "unknown"

    # ── 1. Header panel ──────────────────────────────────────────────────────
    header = Text()
    header.append(artifact.path, style="bold cyan")
    header.append("  ")
    header.append(
        f"[{artifact.stability.upper()}]",
        style=f"bold {stability_color}",
    )
    header.append(f"\n\nBorn {artifact.age_days} days ago  ({born_date})")
    if artifact.born_sha and artifact.born_message:
        header.append(f"\nBirth commit: ")
        header.append(artifact.born_sha, style="dim yellow")
        header.append(f"  {artifact.born_message}", style="dim")

    console.print(Panel(header, title="[bold]myth[/bold] — code archaeology", border_style="blue"))

    # ── 2. Stats row ─────────────────────────────────────────────────────────
    def stat_panel(label: str, value: str) -> Panel:
        return Panel(
            Text(value, style="bold white", justify="center"),
            title=f"[dim]{label}[/dim]",
            border_style="dim",
            expand=True,
        )

    vel_str = f"{artifact.change_velocity:.1f}/mo"

    ins_del_text = Text(justify="center")
    ins_del_text.append(f"+{artifact.total_insertions}", style="bold green")
    ins_del_text.append(" ")
    ins_del_text.append(f"-{artifact.total_deletions}", style="bold red")
    ins_del_panel = Panel(
        ins_del_text,
        title="[dim]lines changed[/dim]",
        border_style="dim",
        expand=True,
    )

    stats_panels = [
        stat_panel("commits", str(artifact.total_commits)),
        stat_panel("bug fixes", str(len(artifact.bug_fix_commits))),
        stat_panel("contributors", str(len(artifact.total_authors))),
        ins_del_panel,
        stat_panel("velocity", vel_str),
    ]
    console.print(Columns(stats_panels, equal=True, expand=True))

    # ── 3. Top contributors ───────────────────────────────────────────────────
    if len(artifact.top_contributors) > 1:
        tbl = Table(
            "Author",
            "Commits",
            "Activity",
            box=box.SIMPLE,
            show_header=True,
            header_style="bold magenta",
            title="Top Contributors",
        )
        max_count = artifact.top_contributors[0][1] if artifact.top_contributors else 1
        for author, count in artifact.top_contributors:
            bar = _bar(count, max_count)
            tbl.add_row(author, str(count), f"[cyan]{bar}[/cyan]")
        console.print(tbl)

    # ── 4. Bug fix commits ────────────────────────────────────────────────────
    if artifact.bug_fix_commits:
        console.print("\n[bold red]Bug Fixes[/bold red]")
        for fc in artifact.bug_fix_commits:
            line = Text()
            line.append(fc.short_sha, style="dim yellow")
            line.append(f"  {_fmt_date(fc.timestamp):12}", style="dim")
            line.append(f"  {fc.author:15}", style="dim")
            line.append(f"  — {fc.message}", style="red")
            console.print(line)

    # ── 5. Recent history (last 10) ───────────────────────────────────────────
    console.print("\n[bold]Recent History[/bold]")
    recent = artifact.commits[:10]
    for fc in recent:
        line = Text()
        line.append(fc.short_sha, style="dim yellow")
        line.append(f"  {_fmt_date(fc.timestamp):12}")
        line.append(f"  {fc.author[:15]:15}")
        msg = fc.message[:65]
        if fc.is_bug_fix:
            line.append(f"  {msg}", style="red")
        else:
            line.append(f"  {msg}")
        console.print(line)

    # ── 6. Renames ────────────────────────────────────────────────────────────
    if artifact.renames:
        names = ", ".join(artifact.renames)
        console.print(f"\n[dim]Previously known as:[/dim] [italic]{names}[/italic]")


def to_markdown(artifact: Artifact) -> str:
    """Render the archaeological report as Markdown."""
    born_date = _fmt_date(artifact.born_at) if artifact.born_at else "unknown"
    lines: list[str] = []

    lines.append(f"# myth — {artifact.path}")
    lines.append(f"\n**Stability:** {artifact.stability.upper()}")
    lines.append(f"**Born:** {artifact.age_days} days ago ({born_date})")
    if artifact.born_sha and artifact.born_message:
        lines.append(f"**Birth commit:** `{artifact.born_sha}` — {artifact.born_message}")

    lines.append("\n## Stats\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total commits | {artifact.total_commits} |")
    lines.append(f"| Bug fixes | {len(artifact.bug_fix_commits)} |")
    lines.append(f"| Contributors | {len(artifact.total_authors)} |")
    lines.append(f"| Lines inserted | +{artifact.total_insertions} |")
    lines.append(f"| Lines deleted | -{artifact.total_deletions} |")
    lines.append(f"| Velocity | {artifact.change_velocity:.1f}/month |")

    if artifact.top_contributors:
        lines.append("\n## Top Contributors\n")
        lines.append("| Author | Commits |")
        lines.append("|--------|---------|")
        for author, count in artifact.top_contributors:
            lines.append(f"| {author} | {count} |")

    if artifact.bug_fix_commits:
        lines.append("\n## Bug Fix Commits\n")
        for fc in artifact.bug_fix_commits:
            lines.append(f"- `{fc.short_sha}` {_fmt_date(fc.timestamp)} **{fc.author}** — {fc.message}")

    lines.append("\n## Recent History\n")
    for fc in artifact.commits[:10]:
        flag = " *(bug fix)*" if fc.is_bug_fix else ""
        lines.append(f"- `{fc.short_sha}` {_fmt_date(fc.timestamp)} **{fc.author}** — {fc.message}{flag}")

    if artifact.renames:
        lines.append("\n## Previously Known As\n")
        for name in artifact.renames:
            lines.append(f"- `{name}`")

    return "\n".join(lines) + "\n"
