"""File system scanner — walks a repo respecting .gitignore."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Iterator
import pathspec

LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python", ".pyi": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C", ".h": "C",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
    ".java": "Java",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".lua": "Lua",
    ".ex": "Elixir", ".exs": "Elixir",
    ".hs": "Haskell",
    ".ml": "OCaml", ".mli": "OCaml",
    ".cs": "C#",
    ".fs": "F#",
    ".toml": "TOML", ".yaml": "YAML", ".yml": "YAML",
    ".json": "JSON", ".jsonc": "JSON",
    ".md": "Markdown", ".mdx": "Markdown",
    ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "CSS", ".sass": "CSS",
    ".sql": "SQL",
    ".tf": "Terraform", ".hcl": "Terraform",
    ".dockerfile": "Docker",
}

ALWAYS_IGNORE = {
    ".git", "__pycache__", ".pytest_cache", "node_modules",
    ".venv", "venv", "env", ".env", "dist", "build", "target",
    ".mypy_cache", ".ruff_cache", ".cache", ".tox",
    "*.egg-info", ".eggs", "htmlcov", ".coverage",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".a", ".lib",
    ".wasm", ".pyc", ".pyo", ".class",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".ttf", ".woff", ".woff2", ".eot",
    ".db", ".sqlite", ".sqlite3",
    ".lock",
}


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    gitignore = root / ".gitignore"
    if gitignore.exists():
        return pathspec.PathSpec.from_lines("gitignore", gitignore.read_text().splitlines())
    return None


def detect_language(path: Path) -> str:
    name_lower = path.name.lower()
    if name_lower == "dockerfile":
        return "Docker"
    if name_lower in ("makefile", "gnumakefile"):
        return "Makefile"
    return LANGUAGE_MAP.get(path.suffix.lower(), "Other")


def is_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        chunk = path.read_bytes()[:1024]
        return b"\x00" in chunk
    except OSError:
        return True


def _should_skip(name: str) -> bool:
    for pattern in ALWAYS_IGNORE:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern:
            return True
    return False


def scan(root: Path, max_depth: int = 12, exclude: frozenset[str] = frozenset()) -> Iterator[Path]:
    """Yield all scannable files under root."""
    spec = _load_gitignore(root)

    def _walk(directory: Path, depth: int) -> Iterator[Path]:
        if depth > max_depth:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return

        for entry in entries:
            if _should_skip(entry.name):
                continue
            if entry.name in exclude:
                continue
            rel = entry.relative_to(root)
            if spec and spec.match_file(str(rel)):
                continue
            if entry.is_symlink():
                continue
            if entry.is_dir():
                yield from _walk(entry, depth + 1)
            elif entry.is_file() and not is_binary(entry):
                yield entry

    yield from _walk(root, 0)


def dominant_language(lang_counts: dict[str, int]) -> str:
    code_langs = {k: v for k, v in lang_counts.items()
                  if k not in ("Other", "Markdown", "TOML", "YAML", "JSON", "Docker", "Makefile")}
    if not code_langs:
        return max(lang_counts, key=lang_counts.get) if lang_counts else "Unknown"
    return max(code_langs, key=code_langs.get)
