"""LLM-optimised output — compact JSON and Markdown for pasting into context."""
from __future__ import annotations
import json
from pathlib import Path
from cartographer.models import CartographyResult
from cartographer.graph import top_by_in_degree


def to_dict(result: CartographyResult) -> dict:
    modules = []
    for node in sorted(result.modules, key=lambda n: (-n.heat_score, n.name)):
        entry: dict = {
            "name": node.name,
            "language": node.language,
            "files": node.total_files,
            "lines": node.total_lines,
            "summary": node.summary,
        }
        if node.avg_complexity:
            entry["avg_complexity"] = node.avg_complexity
        if node.todo_count:
            entry["todos"] = node.todo_count
        if node.heat_score:
            entry["heat"] = node.heat_score
        modules.append(entry)

    top_imports = top_by_in_degree(result.dependency_edges, n=10)

    return {
        "repo": result.repo_name,
        "stats": {
            "files": result.scanned_files,
            "lines": result.total_lines,
            "dominant_language": result.dominant_language,
            "languages": result.languages,
            "has_git": result.has_git,
        },
        "modules": modules,
        "most_imported": [{"module": m, "count": c} for m, c in top_imports],
        "circular_deps": result.circular_deps[:10],
        "hot_files": [
            {"path": str(p.relative_to(result.root)), "heat": s}
            for p, s in result.hot_files[:10]
        ],
        "warnings": result.warnings,
    }


def render_json(result: CartographyResult) -> str:
    return json.dumps(to_dict(result), indent=2)


def render_markdown(result: CartographyResult) -> str:
    d = to_dict(result)
    lines = [
        f"# Codebase Map: {d['repo']}",
        "",
        "## Overview",
        f"- **Files:** {d['stats']['files']}",
        f"- **Lines:** {d['stats']['lines']:,}",
        f"- **Primary language:** {d['stats']['dominant_language']}",
        f"- **Git history:** {'yes' if d['stats']['has_git'] else 'no'}",
        "",
        "## Module Map",
        "",
        "| Module | Language | Files | Lines | Summary |",
        "|--------|----------|------:|------:|---------|",
    ]
    for m in d["modules"]:
        lines.append(
            f"| `{m['name']}` | {m['language']} | {m['files']} | {m['lines']:,} | {m['summary']} |"
        )

    if d["hot_files"]:
        lines += ["", "## Hottest Files (most active in git history)", ""]
        for hf in d["hot_files"]:
            lines.append(f"- `{hf['path']}` (heat: {hf['heat']:.2f})")

    if d["most_imported"]:
        lines += ["", "## Most Imported Modules", ""]
        for mi in d["most_imported"]:
            lines.append(f"- `{mi['module']}` — imported by {mi['count']} file(s)")

    if d["circular_deps"]:
        lines += ["", "## ⚠ Circular Dependencies", ""]
        for cycle in d["circular_deps"]:
            lines.append("- " + " → ".join(cycle))

    if d["warnings"]:
        lines += ["", "## Warnings", ""]
        for w in d["warnings"]:
            lines.append(f"- {w}")

    return "\n".join(lines)
