"""Core data models."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class FileMetrics:
    path: Path
    language: str
    lines: int
    blank_lines: int
    comment_lines: int
    complexity: float          # avg cyclomatic complexity (code files)
    max_complexity: float
    todo_count: int
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)   # classes / top-level fns
    docstring: Optional[str] = None


@dataclass
class GitMetrics:
    path: Path
    commit_count: int
    last_commit_date: Optional[str]
    last_commit_message: Optional[str]
    unique_authors: int
    churn: int                 # total insertions + deletions across all commits


@dataclass
class ModuleNode:
    """A logical module — typically a directory or single file."""
    path: Path
    name: str
    is_dir: bool
    language: str              # dominant language, or "mixed" / "other"
    summary: str               # one-line human description
    files: list[FileMetrics] = field(default_factory=list)
    children: list["ModuleNode"] = field(default_factory=list)

    # rolled-up totals
    total_lines: int = 0
    total_files: int = 0
    avg_complexity: float = 0.0
    todo_count: int = 0

    # git
    git: Optional[GitMetrics] = None
    heat_score: float = 0.0    # normalised 0-1 commit frequency

    # graph
    imports: list[str] = field(default_factory=list)   # modules this one imports
    imported_by: list[str] = field(default_factory=list)


@dataclass
class CartographyResult:
    root: Path
    repo_name: str
    scanned_files: int
    total_lines: int
    dominant_language: str
    languages: dict[str, int]  # lang -> file count
    modules: list[ModuleNode]
    dependency_edges: list[tuple[str, str]]   # (importer, importee)
    circular_deps: list[list[str]]
    hot_files: list[tuple[Path, float]]       # top N by heat
    has_git: bool
    warnings: list[str] = field(default_factory=list)
