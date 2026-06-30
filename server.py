"""mcp-cartographer — codebase intelligence MCP server."""
from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from cartographer.cartographer import run as _map
from cartographer.git_insights import build_heat_map, get_repo
from myth.archaeologist import dig
from sentinel.metrics import collect as _health
from ghost.analyzer import run as _ghost_run

mcp = FastMCP(
    "cartographer",
    instructions=(
        "Codebase intelligence for any local git repository. "
        "Use map_repo first to orient yourself, then drill into hot files, "
        "file history, health, or dead code as needed."
    ),
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _resolve(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise ValueError(f"Path does not exist: {path}")
    return p


def _jsonify(obj: Any) -> Any:
    """Recursively convert an object to a JSON-safe structure."""
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(i) for i in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return _jsonify(asdict(obj))
    return obj


# ── tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
async def map_repo(path: str) -> dict:
    """
    Map a repository — returns languages, module breakdown, hot files,
    dependency edges, circular deps, and complexity metrics.

    Use this first to orient yourself in an unfamiliar codebase.
    path: absolute or ~ path to the repository root.
    """
    root = _resolve(path)
    result = await asyncio.to_thread(_map, root)

    return {
        "repo": result.repo_name,
        "path": str(result.root),
        "scanned_files": result.scanned_files,
        "total_lines": result.total_lines,
        "dominant_language": result.dominant_language,
        "languages": result.languages,
        "has_git": result.has_git,
        "warnings": result.warnings,
        "modules": [
            {
                "name": m.name,
                "language": m.language,
                "summary": m.summary,
                "total_files": m.total_files,
                "total_lines": m.total_lines,
                "avg_complexity": m.avg_complexity,
                "todo_count": m.todo_count,
                "heat_score": m.heat_score,
            }
            for m in result.modules
        ],
        "hot_files": [
            {"path": str(p.relative_to(root)), "heat": round(score, 3)}
            for p, score in result.hot_files
        ],
        "circular_deps": result.circular_deps,
        "most_imported": _top_imported(result.dependency_edges, root),
    }


def _top_imported(edges: list, root: Path, n: int = 10) -> list:
    counts: dict[str, int] = {}
    for _, dst in edges:
        counts[dst] = counts.get(dst, 0) + 1
    return [
        {"module": mod, "import_count": count}
        for mod, count in sorted(counts.items(), key=lambda x: -x[1])[:n]
    ]


@mcp.tool()
async def hot_files(path: str, limit: int = 15) -> list:
    """
    Return the most frequently changed files ranked by git commit activity.

    High heat = frequently modified = likely important or unstable.
    path: repository root.
    limit: number of files to return (default 15).
    """
    root = _resolve(path)
    repo = await asyncio.to_thread(get_repo, root)
    if repo is None:
        return [{"error": "not a git repository"}]

    from cartographer.scanner import scan
    all_paths = list(await asyncio.to_thread(scan, root))
    heat_map = await asyncio.to_thread(build_heat_map, repo, all_paths, root)

    ranked = sorted(heat_map.items(), key=lambda x: -x[1])[:limit]
    return [
        {
            "file": str(p.relative_to(root)),
            "heat": round(score, 3),
        }
        for p, score in ranked
    ]


@mcp.tool()
async def file_history(path: str) -> dict:
    """
    Return the full git archaeology for a specific file — commit history,
    stability classification, bug fix commits, renames, top contributors,
    and change velocity.

    path: absolute path to a specific file (not a directory).
    """
    p = _resolve(path)
    if p.is_dir():
        raise ValueError("file_history expects a file path, not a directory")

    artifact = await asyncio.to_thread(dig, p)
    if artifact is None:
        return {"error": "no git history found for this file"}

    return {
        "path": artifact.path,
        "exists": artifact.exists,
        "age_days": artifact.age_days,
        "born_at": artifact.born_at.isoformat() if artifact.born_at else None,
        "born_message": artifact.born_message,
        "total_commits": artifact.total_commits,
        "unique_authors": sorted(artifact.total_authors),
        "stability": artifact.stability,
        "change_velocity_per_month": round(artifact.change_velocity, 2),
        "total_insertions": artifact.total_insertions,
        "total_deletions": artifact.total_deletions,
        "previous_names": artifact.renames,
        "top_contributors": [
            {"author": a, "commits": c} for a, c in artifact.top_contributors
        ],
        "bug_fix_commits": [
            {
                "sha": fc.short_sha,
                "message": fc.message,
                "author": fc.author,
                "date": fc.timestamp.isoformat(),
            }
            for fc in artifact.bug_fix_commits[:10]
        ],
        "recent_commits": [
            {
                "sha": fc.short_sha,
                "message": fc.message,
                "author": fc.author,
                "date": fc.timestamp.isoformat(),
                "insertions": fc.insertions,
                "deletions": fc.deletions,
                "is_bug_fix": fc.is_bug_fix,
            }
            for fc in artifact.commits[:20]
        ],
    }


@mcp.tool()
async def repo_health(path: str) -> dict:
    """
    Return a 0-100 health score for a project with a full breakdown.

    Scores factor in: uncommitted changes, days since last commit,
    failing tests, dead code density, stale/vulnerable dependencies.

    path: repository root.
    """
    root = _resolve(path)
    snap = await asyncio.to_thread(_health, root)

    return {
        "project": snap.project_name,
        "score": snap.score,
        "score_notes": snap.score_notes,
        "git": {
            "uncommitted_files": snap.uncommitted_files,
            "days_since_commit": round(snap.days_since_commit, 1),
        },
        "tests": {
            "found": snap.tests_found,
            "runner": snap.test_runner,
            "passed": snap.tests_passed,
            "failed": snap.tests_failed,
        },
        "dead_code": {
            "available": snap.ghost_available,
            "high_confidence": snap.dead_symbols_high,
            "total": snap.dead_symbols_total,
        },
        "dependencies": {
            "available": snap.drift_available,
            "stale": snap.stale_deps,
            "vulnerable": snap.vulnerable_deps,
        },
        "size": {
            "py_files": snap.py_file_count,
            "ts_files": snap.ts_file_count,
            "total_lines": snap.total_lines,
        },
        "timestamp": snap.timestamp,
    }


@mcp.tool()
async def dead_code(path: str, min_confidence: str = "medium") -> list:
    """
    Find potentially unused Python symbols (functions, classes, variables).

    Scans the repo for definitions that are never referenced elsewhere.
    Works on Python codebases only.

    path: repository root.
    min_confidence: 'high' for fewer but more certain results, 'medium' for broader sweep.
    """
    root = _resolve(path)

    def _scan() -> list[dict]:
        report = _ghost_run(root, include_private=False)
        if not report.dead_symbols:
            return []

        dead: list[dict] = []
        for sym in report.dead_symbols:
            if min_confidence == "high" and sym.confidence.value != "high":
                continue
            dead.append({
                "symbol": sym.name,
                "kind": sym.kind,
                "file": str(sym.path.relative_to(root)),
                "line": sym.line,
                "confidence": sym.confidence.value,
                "reason": sym.reason,
                "parent": sym.parent,
            })
        return dead

    result = await asyncio.to_thread(_scan)
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
