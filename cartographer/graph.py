"""Dependency graph analysis."""
from __future__ import annotations
from pathlib import Path
from cartographer.models import FileMetrics

try:
    import networkx as nx
    _NX = True
except ImportError:
    _NX = False


def _resolve_import(imp: str, file_path: Path, root: Path) -> str | None:
    """Try to map an import string to a repo-relative module path."""
    # Skip path-style imports (JS/TS relative paths and scoped packages)
    if "/" in imp or imp.startswith("."):
        return None
    parts = [p for p in imp.split(".") if p]
    if not parts:
        return None
    for candidate in [
        root / Path(*parts).with_suffix(".py"),
        root / Path(*parts) / "__init__.py",
    ]:
        if candidate.exists():
            return str(candidate.relative_to(root))
    return None


def build_graph(files: list[FileMetrics], root: Path):
    """Return (edges, circular_deps) where edges are (src_rel, dst_rel) pairs."""
    if not _NX:
        return [], []

    G = nx.DiGraph()
    rel_paths = {str(f.path.relative_to(root)) for f in files}

    for f in files:
        src = str(f.path.relative_to(root))
        G.add_node(src)
        for imp in f.imports:
            resolved = _resolve_import(imp, f.path, root)
            if resolved and resolved in rel_paths and resolved != src:
                G.add_edge(src, resolved)

    edges = list(G.edges())
    try:
        cycles = list(nx.simple_cycles(G))
        circular = [c for c in cycles if len(c) > 1]
    except Exception:
        circular = []

    return edges, circular


def top_by_in_degree(edges: list[tuple[str, str]], n: int = 10) -> list[tuple[str, int]]:
    """Most-imported modules."""
    counts: dict[str, int] = {}
    for _, dst in edges:
        counts[dst] = counts.get(dst, 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])[:n]
