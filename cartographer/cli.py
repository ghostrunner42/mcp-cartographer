"""CLI entry point — `cart`."""
from __future__ import annotations
import sys
from pathlib import Path

import click
from rich.console import Console

err = Console(stderr=True)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "output_json", is_flag=True, help="Output compact JSON for LLM consumption.")
@click.option("--md", "output_md", is_flag=True, help="Output Markdown documentation.")
@click.option("--out", "-o", type=click.Path(), default=None, help="Write output to file instead of stdout.")
@click.option("--depth", default=12, show_default=True, help="Maximum directory depth to scan.")
@click.option("--no-git", is_flag=True, help="Skip git history analysis (faster).")
@click.option("--exclude", "-x", multiple=True, metavar="DIR", help="Directory name(s) to skip (repeatable).")
@click.version_option(package_name="repo-cartographer")
def main(path: str, output_json: bool, output_md: bool, out: str | None, depth: int, no_git: bool, exclude: tuple[str, ...]) -> None:
    """
    Cart — semantic cartography for codebases.

    Scans PATH (default: current directory) and produces a structured map
    showing module purposes, dependency relationships, complexity hotspots,
    and git activity heat.

    \b
    Output modes:
      (default)  Rich terminal report
      --json     Compact JSON — paste directly into an LLM context window
      --md       Markdown — suitable for README or project docs

    \b
    Examples:
      cart                        # map current directory
      cart ~/code/myproject       # map a specific project
      cart --json | pbcopy        # copy LLM context to clipboard
      cart --md --out MAP.md      # write markdown map to file
      cart --no-git               # skip git analysis for speed
    """
    from cartographer import cartographer as core
    from cartographer.renderers import terminal, llm

    root = Path(path).resolve()

    with err.status(f"[cyan]Scanning {root.name}…[/cyan]"):
        if no_git:
            import cartographer.git_insights as gi
            _orig = gi.get_repo
            gi.get_repo = lambda _: None  # type: ignore[assignment]

        result = core.run(root, max_depth=depth, exclude=frozenset(exclude))

        if no_git:
            gi.get_repo = _orig  # type: ignore[assignment]

    if output_json:
        text = llm.render_json(result)
    elif output_md:
        text = llm.render_markdown(result)
    else:
        text = None

    if text is not None:
        if out:
            Path(out).write_text(text)
            err.print(f"[green]Written to {out}[/green]")
        else:
            click.echo(text)
        return

    # Rich terminal mode
    if out:
        from rich.console import Console as RConsole
        file_console = RConsole(file=open(out, "w"), width=120)
        import cartographer.renderers.terminal as tr
        _orig_console = tr.console
        tr.console = file_console
        tr.render(result)
        tr.console = _orig_console
        err.print(f"[green]Written to {out}[/green]")
    else:
        terminal.render(result)
