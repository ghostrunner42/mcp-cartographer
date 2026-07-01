"""Scan source files to determine which declared deps are actually imported."""
from __future__ import annotations
import ast
import re
from pathlib import Path

ALWAYS_IGNORE = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    "dist", "build", ".pytest_cache", ".mypy_cache",
}


def _python_files(root: Path):
    for entry in root.rglob("*.py"):
        if any(p in ALWAYS_IGNORE for p in entry.parts):
            continue
        yield entry


def _js_files(root: Path):
    for ext in ("*.js", "*.ts", "*.jsx", "*.tsx", "*.mjs"):
        for entry in root.rglob(ext):
            if any(p in ALWAYS_IGNORE for p in entry.parts):
                continue
            yield entry


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def python_imports(root: Path) -> set[str]:
    """All top-level module names imported in Python source."""
    names: set[str] = set()
    for path in _python_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0].lower())
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0].lower())
    return names


_JS_REQUIRE = re.compile(r"""require\(['"]([^'"@][^'"]*)['"]\)""")
_JS_IMPORT = re.compile(r"""from\s+['"]([^'"@./][^'"]*)['"]\s""")
_JS_IMPORT2 = re.compile(r"""import\s+['"]([^'"@./][^'"]*)['"]\s""")


def js_imports(root: Path) -> set[str]:
    names: set[str] = set()
    for path in _js_files(root):
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in (_JS_REQUIRE, _JS_IMPORT, _JS_IMPORT2):
            for m in pattern.finditer(source):
                pkg = m.group(1).split("/")[0]
                names.add(pkg.lower())
    return names


# Common PyPI name → import name mismatches
_PYPI_TO_IMPORT: dict[str, str] = {
    "gitpython": "git",
    "pillow": "PIL",
    "beautifulsoup4": "bs4",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "pyyaml": "yaml",
    "python-dotenv": "dotenv",
    "psycopg2-binary": "psycopg2",
    "mysqlclient": "MySQLdb",
    "python-dateutil": "dateutil",
    "antlr4-python3-runtime": "antlr4",
    "pyzmq": "zmq",
    "aiohttp": "aiohttp",
    "httpx": "httpx",
    "attrs": "attr",
    "protobuf": "google.protobuf",
}


def build_usage_set(root: Path) -> set[str]:
    raw = python_imports(root) | js_imports(root)
    normalised = {_normalise(n) for n in raw}
    # also add pypi package names for known import-name mismatches
    reverse = {v: k for k, v in _PYPI_TO_IMPORT.items()}
    for imp in list(raw):
        pkg = reverse.get(imp.lower())
        if pkg:
            normalised.add(pkg)
    return normalised
