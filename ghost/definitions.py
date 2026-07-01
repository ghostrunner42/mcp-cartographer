"""Extract all symbol definitions from Python source files."""
from __future__ import annotations
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Symbol:
    name: str
    kind: str          # "function", "class", "method", "variable"
    path: Path
    line: int
    is_private: bool   # starts with _
    is_dunder: bool    # starts and ends with __
    parent: str | None # enclosing class name, if any
    decorators: list[str]


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    names = []
    for d in node.decorator_list:
        if isinstance(d, ast.Name):
            names.append(d.id)
        elif isinstance(d, ast.Attribute):
            names.append(d.attr)
        elif isinstance(d, ast.Call):
            func = d.func
            if isinstance(func, ast.Name):
                names.append(func.id)
            elif isinstance(func, ast.Attribute):
                names.append(func.attr)
    return names


def extract(path: Path) -> list[Symbol]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return []

    symbols: list[Symbol] = []

    def _visit(node: ast.AST, parent_class: str | None = None) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            decs = _decorator_names(node)
            symbols.append(Symbol(
                name=name,
                kind="method" if parent_class else "function",
                path=path,
                line=node.lineno,
                is_private=name.startswith("_") and not name.startswith("__"),
                is_dunder=name.startswith("__") and name.endswith("__"),
                parent=parent_class,
                decorators=decs,
            ))
            # visit nested functions but mark them as having a parent
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _visit(child, parent_class)

        elif isinstance(node, ast.ClassDef):
            name = node.name
            symbols.append(Symbol(
                name=name,
                kind="class",
                path=path,
                line=node.lineno,
                is_private=name.startswith("_"),
                is_dunder=False,
                parent=None,
                decorators=_decorator_names(node),
            ))
            for child in ast.iter_child_nodes(node):
                _visit(child, parent_class=name)

    for node in ast.iter_child_nodes(tree):
        _visit(node)

    return symbols
