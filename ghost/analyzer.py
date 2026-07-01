"""Core analysis — cross-reference definitions against usages."""
from __future__ import annotations
from pathlib import Path
from ghost.models import DeadSymbol, Confidence, GhostReport, UnreferencedFile
from ghost.definitions import Symbol, extract
from ghost.references import build_reference_map, entry_point_files
from ghost.scanner import scan_python

# Symbols we never flag regardless of reference count
_ALWAYS_LIVE_DECORATORS = {
    "property", "staticmethod", "classmethod", "abstractmethod",
    "override", "pytest", "fixture", "mark",
    "app", "router", "blueprint", "mcp",  # web frameworks / FastMCP
    "task", "shared_task", "periodic",  # Celery
    "command", "group", "option", "argument",  # Click
    "signal_handler",
}

_ALWAYS_LIVE_NAMES = {
    "__init__", "__new__", "__repr__", "__str__", "__eq__", "__hash__",
    "__len__", "__iter__", "__next__", "__enter__", "__exit__",
    "__getitem__", "__setitem__", "__delitem__", "__contains__",
    "__call__", "__del__", "__class_getitem__", "__post_init__",
    "__all__", "__version__", "__author__", "main",
    "setup", "teardown", "setUp", "tearDown",  # unittest
}

_ALWAYS_LIVE_PREFIXES = ("test_", "Test")


def _is_always_live(sym: Symbol) -> bool:
    if sym.is_dunder:
        return True
    if sym.name in _ALWAYS_LIVE_NAMES:
        return True
    for prefix in _ALWAYS_LIVE_PREFIXES:
        if sym.name.startswith(prefix):
            return True
    if any(d in _ALWAYS_LIVE_DECORATORS for d in sym.decorators):
        return True
    return False


def _find_unreferenced_files(
    python_files: list[Path],
    root: Path,
    ref_map: dict[str, set[str]],
    entry_files: set[str],
) -> list[UnreferencedFile]:
    """Files that are never imported by any other file."""
    # build set of all files that appear as importees
    imported_files: set[str] = set()
    for refs in ref_map.values():
        for r in refs:
            if not r.startswith("__all__:"):
                imported_files.add(r)

    unreferenced = []
    for path in python_files:
        key = str(path)
        name = path.name
        if name in ("__init__.py", "conftest.py", "setup.py", "manage.py"):
            continue
        if key in entry_files:
            continue
        # check if this file is imported by checking if its module name appears as a reference
        module_name = path.stem
        if module_name in ref_map:
            continue
        # also check by file path
        if key in imported_files:
            continue
        unreferenced.append(UnreferencedFile(
            path=path,
            reason="never imported or referenced by any other file",
        ))
    return unreferenced


def run(root: Path, include_private: bool = False) -> GhostReport:
    root = root.resolve()
    python_files = list(scan_python(root))
    warnings: list[str] = []

    if not python_files:
        return GhostReport(
            root=root,
            scanned_files=0,
            total_symbols=0,
            warnings=["No Python files found"],
        )

    # Extract all definitions
    all_symbols: list[Symbol] = []
    for path in python_files:
        all_symbols.extend(extract(path))

    # Build reference map across entire codebase
    ref_map = build_reference_map(python_files)
    entry_files = entry_point_files(python_files)

    dead: list[DeadSymbol] = []

    for sym in all_symbols:
        if _is_always_live(sym):
            continue
        if sym.is_private and not include_private:
            continue

        file_key = str(sym.path)
        refs = ref_map.get(sym.name, set())

        # Filter out self-references (the file defining the symbol)
        external_refs = {r for r in refs if not r.startswith(file_key) and not r.startswith("__all__:")}
        all_refs_count = len(refs)

        if all_refs_count == 0:
            confidence = Confidence.HIGH
            reason = "never referenced anywhere in the codebase"
        elif not external_refs:
            confidence = Confidence.MEDIUM
            reason = "only referenced within its own file"
        else:
            continue  # referenced externally — likely live

        dead.append(DeadSymbol(
            name=sym.name,
            kind=sym.kind,
            path=sym.path,
            line=sym.line,
            confidence=confidence,
            reason=reason,
            is_private=sym.is_private,
            parent=sym.parent,
        ))

    # Sort: high confidence first, then by file path
    dead.sort(key=lambda s: (s.confidence != Confidence.HIGH, str(s.path), s.line))

    unreferenced = _find_unreferenced_files(python_files, root, ref_map, entry_files)

    return GhostReport(
        root=root,
        scanned_files=len(python_files),
        total_symbols=len(all_symbols),
        dead_symbols=dead,
        unreferenced_files=unreferenced,
        warnings=warnings,
    )
