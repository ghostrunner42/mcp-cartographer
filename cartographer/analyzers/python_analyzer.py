"""Deep analysis for Python files via AST."""
from __future__ import annotations
import ast
import re
from pathlib import Path
from cartographer.models import FileMetrics

TODO_RE = re.compile(r"#\s*(TODO|FIXME|HACK|XXX|BUG|NOTE)\b", re.IGNORECASE)


def _cyclomatic(node: ast.AST) -> int:
    """McCabe complexity for a single function/method node."""
    count = 1
    for child in ast.walk(node):
        if isinstance(child, (
            ast.If, ast.While, ast.For, ast.ExceptHandler,
            ast.With, ast.Assert, ast.comprehension,
        )):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
        elif hasattr(ast, "match_case") and isinstance(child, ast.match_case):
            count += 1
    return count


def _module_docstring(tree: ast.Module) -> str | None:
    return ast.get_docstring(tree)


def _top_level_names(tree: ast.Module) -> list[str]:
    names = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


def _imports(tree: ast.Module) -> list[str]:
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return list(dict.fromkeys(imports))


def analyze(path: Path) -> FileMetrics | None:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lines = source.splitlines()
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(1 for l in lines if l.strip().startswith("#"))
    todos = len(TODO_RE.findall(source))

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return FileMetrics(
            path=path, language="Python",
            lines=len(lines), blank_lines=blank, comment_lines=comment,
            complexity=0.0, max_complexity=0.0, todo_count=todos,
        )

    funcs = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    complexities = [_cyclomatic(f) for f in funcs]
    avg_cc = sum(complexities) / len(complexities) if complexities else 0.0
    max_cc = max(complexities) if complexities else 0.0

    return FileMetrics(
        path=path,
        language="Python",
        lines=len(lines),
        blank_lines=blank,
        comment_lines=comment,
        complexity=round(avg_cc, 2),
        max_complexity=round(max_cc, 2),
        todo_count=todos,
        imports=_imports(tree),
        exports=_top_level_names(tree),
        docstring=_module_docstring(tree),
    )
