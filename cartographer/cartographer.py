"""Main orchestrator — ties scanner, analyzers, git, graph, summarizer together."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path

from cartographer.models import CartographyResult, FileMetrics, ModuleNode
from cartographer.scanner import scan, detect_language, dominant_language
from cartographer.analyzers import analyze_file
from cartographer import git_insights, graph, summarizer


def _build_module_tree(
    files: list[FileMetrics],
    root: Path,
    heat_map: dict[Path, float],
    git_map: dict[Path, git_insights.GitMetrics | None],
) -> list[ModuleNode]:
    """
    Build a two-level module tree:
    - top-level directories become ModuleNodes with children
    - files directly under root become their own ModuleNodes
    """
    buckets: dict[Path, list[FileMetrics]] = defaultdict(list)
    for f in files:
        rel = f.path.relative_to(root)
        parts = rel.parts
        if len(parts) == 1:
            buckets[root].append(f)
        else:
            buckets[root / parts[0]].append(f)

    nodes: list[ModuleNode] = []

    for bucket_path, bucket_files in sorted(buckets.items()):
        lang_counts: dict[str, int] = defaultdict(int)
        total_lines = 0
        total_todos = 0
        complexities = []

        for f in bucket_files:
            lang_counts[f.language] += 1
            total_lines += f.lines
            total_todos += f.todo_count
            if f.complexity:
                complexities.append(f.complexity)

        dom_lang = dominant_language(dict(lang_counts))
        avg_cc = round(sum(complexities) / len(complexities), 2) if complexities else 0.0
        avg_heat = (
            sum(heat_map.get(f.path, 0.0) for f in bucket_files) / len(bucket_files)
            if bucket_files else 0.0
        )

        is_root_level = bucket_path == root
        node = ModuleNode(
            path=bucket_path,
            name="." if is_root_level else bucket_path.name,
            is_dir=True,
            language=dom_lang,
            summary="",
            files=bucket_files,
            total_lines=total_lines,
            total_files=len(bucket_files),
            avg_complexity=avg_cc,
            todo_count=total_todos,
            heat_score=round(avg_heat, 3),
            imports=list({imp for f in bucket_files for imp in f.imports}),
        )
        node.summary = summarizer.summarize_dir(node)
        nodes.append(node)

    return nodes


def run(root: Path, max_depth: int = 12, exclude: frozenset[str] = frozenset()) -> CartographyResult:
    root = root.resolve()
    warnings: list[str] = []

    # --- scan ---
    all_paths = list(scan(root, max_depth=max_depth, exclude=exclude))

    # --- git ---
    repo = git_insights.get_repo(root)
    has_git = repo is not None
    heat_map = git_insights.build_heat_map(repo, all_paths, root) if has_git else {}

    # --- analyze ---
    all_metrics: list[FileMetrics] = []
    lang_counts: dict[str, int] = defaultdict(int)

    for path in all_paths:
        m = analyze_file(path)
        if m:
            all_metrics.append(m)
            lang_counts[m.language] += 1

    # --- git per-file (sampled for speed — only top hot files) ---
    hot_paths = sorted(heat_map, key=heat_map.get, reverse=True)[:50]
    git_map: dict[Path, git_insights.GitMetrics | None] = {}
    for p in hot_paths:
        git_map[p] = git_insights.file_metrics(repo, p, root)

    # --- dependency graph ---
    edges, circular = graph.build_graph(all_metrics, root)
    # circular_deps surfaced in renderer; no separate warning needed

    # --- module tree ---
    modules = _build_module_tree(all_metrics, root, heat_map, git_map)

    # --- hot files list ---
    hot_files = sorted(
        [(p, s) for p, s in heat_map.items()],
        key=lambda x: -x[1],
    )[:20]

    dom_lang = dominant_language(dict(lang_counts))
    total_lines = sum(m.lines for m in all_metrics)

    return CartographyResult(
        root=root,
        repo_name=root.name,
        scanned_files=len(all_metrics),
        total_lines=total_lines,
        dominant_language=dom_lang,
        languages=dict(lang_counts),
        modules=modules,
        dependency_edges=edges,
        circular_deps=circular,
        hot_files=hot_files,
        has_git=has_git,
        warnings=warnings,
    )
