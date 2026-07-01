"""Find all name references across the codebase."""
from __future__ import annotations
import ast
from pathlib import Path
from collections import defaultdict


def _collect_names(tree: ast.AST) -> set[str]:
    """All Name loads, attribute accesses, and call names in a file."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            names.add(node.attr)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _collect_all_exports(tree: ast.AST) -> set[str]:
    """Names listed in __all__."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        return {
                            elt.s for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.s, str)
                        }
    return set()


def _is_entry_point(tree: ast.AST, path: Path) -> bool:
    """True if the file has a __main__ guard or is a conftest/setup."""
    name = path.name
    if name in ("conftest.py", "setup.py", "manage.py"):
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
            ):
                return True
    return False


def build_reference_map(python_files: list[Path]) -> dict[str, set[str]]:
    """
    Return {symbol_name: {file_rel_path, ...}} mapping which files reference each name.
    Also folds in __all__ exports and entry-point markers.
    """
    refs: dict[str, set[str]] = defaultdict(set)

    for path in python_files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue

        file_key = str(path)
        for name in _collect_names(tree):
            refs[name].add(file_key)
        for name in _collect_all_exports(tree):
            refs[name].add(f"__all__:{file_key}")
        if _is_entry_point(tree, path):
            refs[f"__entry__:{path.name}"].add(file_key)

    return dict(refs)


def entry_point_files(python_files: list[Path]) -> set[str]:
    """File paths that are entry points."""
    result = set()
    for path in python_files:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        if _is_entry_point(tree, path):
            result.add(str(path))
    return result
