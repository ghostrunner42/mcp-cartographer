"""CLI entry point — `drift`."""
from __future__ import annotations
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from rich import box

err = Console(stderr=True)
out = Console()

_SEVERITY_STYLE = {
    "CRITICAL": "bold red",
    "HIGH": "red",
    "MEDIUM": "yellow",
    "LOW": "grey70",
    "UNKNOWN": "grey50",
    "none": "green",
}


def _outdated_badge(result) -> Text:
    if result.majors_behind >= 2:
        return Text(f"  {result.majors_behind} major{'s' if result.majors_behind != 1 else ''} behind  ", style="bold red")
    if result.majors_behind == 1:
        return Text("  1 major behind  ", style="yellow")
    if result.is_outdated:
        return Text("  patch/minor  ", style="cyan")
    return Text("  up to date  ", style="green")


def _vuln_badge(result) -> Text:
    if not result.vulns:
        return Text("  —  ", style="grey50")
    count = len(result.vulns)
    style = _SEVERITY_STYLE.get(result.severity, "white")
    return Text(f"  {count} ({result.severity})  ", style=style)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--no-vulns", is_flag=True, help="Skip CVE lookup (faster).")
@click.option("--no-usage", is_flag=True, help="Skip source usage scan.")
@click.option("--dev", "include_dev", is_flag=True, help="Include dev dependencies.")
@click.option("--json", "output_json", is_flag=True, help="Output JSON.")
@click.version_option(package_name="jarvis-suite")
def main(
    path: str,
    no_vulns: bool,
    no_usage: bool,
    include_dev: bool,
    output_json: bool,
) -> None:
    """
    Drift — dependency health scanner.

    Checks declared dependencies for outdated versions, known CVEs,
    and whether they're actually used in the source code.

    \b
    Examples:
      drift                       # scan current directory
      drift ~/code/myproject      # scan a project
      drift --no-vulns            # skip CVE lookup (faster)
      drift --dev                 # include dev dependencies
      drift --json                # machine-readable output
    """
    import json as jsonlib
    from drift import parser, checker, usage

    root = Path(path).resolve()

    with err.status("[cyan]Parsing manifests…[/cyan]"):
        deps = parser.discover(root)

    if not deps:
        err.print("[yellow]No dependency manifests found (pyproject.toml, requirements*.txt, package.json)[/yellow]")
        return

    if not include_dev:
        deps = [d for d in deps if not d.dev]

    # Determine ecosystem per package
    pkg_json = root / "package.json"
    npm_names: set[str] = set()
    if pkg_json.exists():
        import json as _j
        try:
            pj = _j.loads(pkg_json.read_text())
            npm_names = set(pj.get("dependencies", {}).keys()) | set(pj.get("devDependencies", {}).keys())
        except Exception:
            pass

    ecosystem_map = {d.name: ("npm" if d.name in npm_names else "pypi") for d in deps}

    with err.status(f"[cyan]Checking {len(deps)} dependencies…[/cyan]"):
        results = checker.check_all(deps, ecosystem_map)

    if not no_usage:
        with err.status("[cyan]Scanning source for import usage…[/cyan]"):
            used = usage.build_usage_set(root)
        for r in results:
            r.used_in_source = r.name in used or r.name.replace("-", "_") in used

    if output_json:
        data = [
            {
                "name": r.name,
                "declared": r.declared_version,
                "latest": r.latest_version,
                "outdated": r.is_outdated,
                "majors_behind": r.majors_behind,
                "vulns": [{"id": v.id, "severity": v.severity, "summary": v.summary} for v in r.vulns],
                "used": r.used_in_source if not no_usage else None,
                "dev": r.dev,
            }
            for r in results
        ]
        click.echo(jsonlib.dumps(data, indent=2))
        return

    _render(results, root, no_usage)


def _render(results, root: Path, no_usage: bool) -> None:
    vulns_total = sum(len(r.vulns) for r in results)
    outdated = sum(1 for r in results if r.is_outdated)
    unused = sum(1 for r in results if not r.used_in_source and not no_usage)

    header = (
        f"[bold]{root.name}[/bold]   "
        f"[grey50]{len(results)} deps · "
        f"[{'red' if outdated else 'green'}]{outdated} outdated[/{'red' if outdated else 'green'}] · "
        f"[{'red' if vulns_total else 'green'}]{vulns_total} CVE{'s' if vulns_total != 1 else ''}[/{'red' if vulns_total else 'green'}]"
        + (f" · [yellow]{unused} unused[/yellow]" if not no_usage else "")
        + "[/grey50]"
    )
    out.print(Panel(header, title="[bold cyan]Drift[/bold cyan]", border_style="cyan"))
    out.print()

    # Sort: vulns first, then most outdated, then alphabetical
    def _sort_key(r):
        sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4, "none": 5}
        return (sev_order.get(r.severity, 5), -r.majors_behind, r.name)

    sorted_results = sorted(results, key=_sort_key)

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan", expand=True)
    table.add_column("Package", min_width=16, max_width=26, no_wrap=True, overflow="ellipsis")
    table.add_column("Declared → Latest", min_width=18, max_width=22, no_wrap=True)
    table.add_column("Version", min_width=14, no_wrap=True)
    table.add_column("CVEs", min_width=14, no_wrap=True)
    if not no_usage:
        table.add_column("Used", min_width=4, no_wrap=True)

    for r in sorted_results:
        latest_str = r.latest_version or "?"
        ver_col = Text(f"{r.declared_version or 'any'} → {latest_str}", style="grey50")
        used_str = Text("yes", style="green") if r.used_in_source else Text("no ", style="yellow")
        row = [
            Text(r.name, style="bold" if r.vulns else ""),
            ver_col,
            _outdated_badge(r),
            _vuln_badge(r),
        ]
        if not no_usage:
            row.append(used_str)
        table.add_row(*row)

    out.print(table)

    # Show CVE details for anything with high/critical
    important_vulns = [r for r in results if any(v.severity in ("CRITICAL", "HIGH") for v in r.vulns)]
    if important_vulns:
        out.print()
        out.print(Rule("[bold red]Critical / High Vulnerabilities[/bold red]", style="red"))
        for r in important_vulns:
            for v in r.vulns:
                if v.severity in ("CRITICAL", "HIGH"):
                    style = "bold red" if v.severity == "CRITICAL" else "red"
                    out.print(f"  [{style}]{v.id}[/{style}]  [bold]{r.name}[/bold]  [grey50]{v.summary}[/grey50]")
