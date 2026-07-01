"""CLI entry point — `myth`."""
from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console

from myth.archaeologist import Artifact, dig
from myth.renderer import render, to_markdown

__version__ = "0.1.0"

err = Console(stderr=True)


def _artifact_to_dict(artifact: Artifact) -> dict:
    """Convert Artifact to a JSON-serialisable dict."""
    def _dt(dt: datetime | None) -> str | None:
        return dt.isoformat() if dt else None

    return {
        "path": artifact.path,
        "exists": artifact.exists,
        "born_at": _dt(artifact.born_at),
        "born_sha": artifact.born_sha,
        "born_message": artifact.born_message,
        "age_days": artifact.age_days,
        "total_commits": artifact.total_commits,
        "total_authors": sorted(artifact.total_authors),
        "bug_fix_count": len(artifact.bug_fix_commits),
        "top_contributors": [
            {"author": a, "commits": c} for a, c in artifact.top_contributors
        ],
        "change_velocity": artifact.change_velocity,
        "stability": artifact.stability,
        "total_insertions": artifact.total_insertions,
        "total_deletions": artifact.total_deletions,
        "renames": artifact.renames,
        "commits": [
            {
                "sha": fc.sha,
                "short_sha": fc.short_sha,
                "message": fc.message,
                "author": fc.author,
                "email": fc.email,
                "timestamp": _dt(fc.timestamp),
                "insertions": fc.insertions,
                "deletions": fc.deletions,
                "is_bug_fix": fc.is_bug_fix,
                "is_rename": fc.is_rename,
            }
            for fc in artifact.commits
        ],
    }


@click.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--json", "-j", "as_json", is_flag=True, help="Output raw JSON.")
@click.option("--out", "-o", "out_file", type=click.Path(), default=None,
              help="Write Markdown report to this file.")
@click.version_option(__version__, "--version")
def main(path: str, as_json: bool, out_file: str | None) -> None:
    """Code archaeology — trace the full history and story of any file."""
    err.print("[cyan]Digging through history…[/cyan]")

    artifact = dig(Path(path))

    if artifact is None:
        err.print(
            "[red]No git history found.[/red] "
            "Either this path is not inside a git repository, "
            "or it has never been committed."
        )
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(_artifact_to_dict(artifact), indent=2))
        return

    out_console = Console()
    render(artifact, out_console)

    if out_file:
        md = to_markdown(artifact)
        Path(out_file).write_text(md, encoding="utf-8")
        err.print(f"[green]Report written to[/green] {out_file}")
