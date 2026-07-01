"""CLI entry point — `ghost`."""
from __future__ import annotations
from pathlib import Path
import click
from rich.console import Console

err = Console(stderr=True)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--private", is_flag=True, help="Include private (_prefixed) symbols.")
@click.option("--high-only", is_flag=True, help="Only show high-confidence dead code.")
@click.option("--json", "output_json", is_flag=True, help="Output JSON.")
@click.version_option(package_name="jarvis-suite")
def main(path: str, private: bool, high_only: bool, output_json: bool) -> None:
    """
    Ghost — find dead code in Python projects.

    Scans PATH (default: current directory) for functions, methods, and classes
    that are never referenced anywhere in the codebase.

    \b
    Confidence levels:
      HIGH    Never referenced anywhere — almost certainly dead
      MEDIUM  Only referenced within the same file — likely dead

    \b
    Examples:
      ghost                     # scan current directory
      ghost ~/code/myproject    # scan a project
      ghost --high-only         # only show definite dead code
      ghost --private           # include _private symbols
      ghost --json              # machine-readable output
    """
    import json
    from ghost import analyzer, renderer

    root = Path(path).resolve()

    with err.status(f"[red]Hunting ghosts in {root.name}…[/red]"):
        report = analyzer.run(root, include_private=private)

    if output_json:
        data = {
            "root": str(root),
            "scanned_files": report.scanned_files,
            "total_symbols": report.total_symbols,
            "dead_symbols": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "confidence": s.confidence.value,
                    "path": str(s.path.relative_to(root)),
                    "line": s.line,
                    "reason": s.reason,
                    "parent": s.parent,
                }
                for s in report.dead_symbols
                if not high_only or s.confidence.value == "high"
            ],
            "unreferenced_files": [
                str(f.path.relative_to(root)) for f in report.unreferenced_files
            ],
        }
        click.echo(json.dumps(data, indent=2))
        return

    renderer.render(report, root, show_medium=not high_only)
