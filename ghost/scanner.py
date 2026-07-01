"""File system scanner — Python files only, respects .gitignore."""
from __future__ import annotations
from pathlib import Path
from typing import Iterator
import pathspec

ALWAYS_IGNORE = {
    ".git", "__pycache__", ".pytest_cache", "node_modules",
    ".venv", "venv", "env", ".env", "dist", "build", "target",
    ".mypy_cache", ".ruff_cache", ".tox", ".eggs",
}


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    gi = root / ".gitignore"
    if gi.exists():
        return pathspec.PathSpec.from_lines("gitignore", gi.read_text().splitlines())
    return None


def _should_skip(name: str) -> bool:
    return name in ALWAYS_IGNORE or name.endswith(".egg-info")


def scan_python(root: Path) -> Iterator[Path]:
    spec = _load_gitignore(root)

    def _walk(d: Path) -> Iterator[Path]:
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for entry in entries:
            if _should_skip(entry.name) or entry.is_symlink():
                continue
            rel = entry.relative_to(root)
            if spec and spec.match_file(str(rel)):
                continue
            if entry.is_dir():
                yield from _walk(entry)
            elif entry.suffix == ".py":
                yield entry

    yield from _walk(root)
