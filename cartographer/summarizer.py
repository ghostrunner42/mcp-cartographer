"""Infer one-line module summaries from code structure."""
from __future__ import annotations
from pathlib import Path
from cartographer.models import FileMetrics, ModuleNode
from cartographer.scanner import detect_language

# Well-known filenames → instant summary
_KNOWN: dict[str, str] = {
    "main.py": "application entry point",
    "app.py": "application factory / entry point",
    "server.py": "HTTP server entry point",
    "cli.py": "command-line interface",
    "config.py": "configuration loading",
    "settings.py": "project settings",
    "models.py": "data models / schemas",
    "schema.py": "data schema definitions",
    "schemas.py": "data schema definitions",
    "db.py": "database connection / session",
    "database.py": "database connection / session",
    "routes.py": "HTTP route definitions",
    "views.py": "view handlers",
    "controllers.py": "request controllers",
    "middleware.py": "middleware pipeline",
    "auth.py": "authentication / authorisation",
    "utils.py": "utility helpers",
    "helpers.py": "utility helpers",
    "constants.py": "shared constants",
    "exceptions.py": "custom exception types",
    "errors.py": "error definitions",
    "tests.py": "test suite",
    "test_main.py": "main test suite",
    "conftest.py": "pytest fixtures",
    "setup.py": "package setup script",
    "manage.py": "Django management CLI",
    "wsgi.py": "WSGI entry point",
    "asgi.py": "ASGI entry point",
    "celery.py": "Celery worker configuration",
    "tasks.py": "background task definitions",
    "signals.py": "event signals",
    "admin.py": "admin panel registration",
    "migrations": "database migration scripts",
    "serializers.py": "data serialisers",
    "types.py": "shared type definitions",
    "index.ts": "module entry point",
    "index.js": "module entry point",
    "index.tsx": "React app root",
    "App.tsx": "root React component",
    "App.jsx": "root React component",
    "store.ts": "state store",
    "store.js": "state store",
    "router.ts": "client-side router",
    "router.js": "client-side router",
    "Dockerfile": "container build definition",
    "docker-compose.yml": "multi-service container orchestration",
    "Makefile": "build / task runner targets",
    "README.md": "project documentation",
    ".env.example": "environment variable template",
    "pyproject.toml": "Python project metadata and tooling config",
    "package.json": "Node.js project metadata and scripts",
    "go.mod": "Go module definition",
    "Cargo.toml": "Rust crate manifest",
}

# Directory names → hint
_DIR_HINTS: dict[str, str] = {
    "tests": "test suite",
    "test": "test suite",
    "__tests__": "test suite",
    "spec": "test suite",
    "docs": "documentation",
    "scripts": "utility scripts",
    "migrations": "database migrations",
    "fixtures": "test fixtures / seed data",
    "static": "static assets",
    "assets": "static assets",
    "public": "publicly served files",
    "templates": "HTML templates",
    "components": "UI components",
    "pages": "page-level components",
    "hooks": "React hooks",
    "context": "React context providers",
    "store": "state management",
    "services": "external service integrations",
    "api": "API layer",
    "handlers": "request handlers",
    "middleware": "middleware pipeline",
    "models": "data models",
    "schemas": "data schemas",
    "utils": "utility helpers",
    "helpers": "utility helpers",
    "lib": "shared library code",
    "core": "core business logic",
    "config": "configuration files",
    "cli": "command-line interface",
    "cmd": "command entry points",
    "pkg": "reusable packages",
    "internal": "internal packages (not exported)",
    "vendor": "vendored dependencies",
    "deploy": "deployment configuration",
    "infra": "infrastructure-as-code",
    "terraform": "Terraform configuration",
    "k8s": "Kubernetes manifests",
    "helm": "Helm chart",
    "ansible": "Ansible playbooks",
    "jobs": "background jobs",
    "workers": "background workers",
    "tasks": "task definitions",
    "events": "event definitions / handlers",
    "types": "shared type definitions",
    "interfaces": "interface definitions",
    "constants": "shared constants",
    "mocks": "test mocks",
    "stubs": "test stubs / generated stubs",
    "generated": "auto-generated code",
    "gen": "auto-generated code",
    "proto": "Protocol Buffer definitions",
    "graphql": "GraphQL schema / resolvers",
}


def _from_docstring(metrics: FileMetrics) -> str | None:
    if not metrics.docstring:
        return None
    first_line = metrics.docstring.strip().splitlines()[0].strip().rstrip(".")
    if first_line and len(first_line) < 120:
        return first_line
    return None


def _from_exports(metrics: FileMetrics) -> str | None:
    exports = metrics.exports[:5]
    if not exports:
        return None
    if len(exports) == 1:
        return f"defines {exports[0]}"
    return f"defines {', '.join(exports[:-1])} and {exports[-1]}"


def summarize_file(metrics: FileMetrics) -> str:
    name = metrics.path.name
    if name in _KNOWN:
        return _KNOWN[name]
    doc = _from_docstring(metrics)
    if doc:
        return doc
    exp = _from_exports(metrics)
    if exp:
        return exp
    lang = metrics.language.lower()
    return f"{lang} source ({metrics.lines} lines)"


def summarize_dir(node: ModuleNode) -> str:
    name = node.path.name.lower()

    # Root-level bucket holds config/misc files at project root
    if node.name == ".":
        langs = {f.language for f in node.files}
        config_langs = langs & {"TOML", "YAML", "JSON", "Docker", "Makefile", "Other"}
        if langs == config_langs or not (langs - config_langs):
            return "project root — config and tooling files"
        return "project root — mixed source and config files"

    if name in _DIR_HINTS:
        return _DIR_HINTS[name]
    if name in _KNOWN:
        return _KNOWN[name]

    if node.total_files == 0:
        return "empty directory"

    # Try the primary file: the one named after the directory (e.g. foo/foo.py)
    for f in node.files:
        if f.path.stem.lower() == name:
            doc = _from_docstring(f)
            if doc:
                return doc

    # Try __init__.py docstring
    for f in node.files:
        if f.path.name == "__init__.py":
            doc = _from_docstring(f)
            if doc:
                return doc

    # Try any non-cli file docstring (often more descriptive than cli.py)
    _skip = {"cli.py", "__init__.py", "__main__.py", "conftest.py"}
    _generic_prefixes = ("cli entry", "entry point", "command-line")
    for f in sorted(node.files, key=lambda x: x.path.name):
        if f.path.name in _skip:
            continue
        doc = _from_docstring(f)
        if doc and not doc.lower().startswith(_generic_prefixes):
            return doc

    # Compose from anchor files and known child subdirs
    parts: list[str] = []
    for f in node.files:
        if f.path.name in _KNOWN:
            parts.append(_KNOWN[f.path.name])
    for child in node.children:
        child_name = child.path.name.lower()
        if child_name in _DIR_HINTS:
            parts.append(_DIR_HINTS[child_name])
    if parts:
        seen: set[str] = set()
        unique = [p for p in parts if not (p in seen or seen.add(p))]  # type: ignore[func-returns-value]
        return unique[0] if len(unique) == 1 else f"{unique[0]} — {', '.join(unique[1:3])}"

    lang = node.language
    return f"{lang} module ({node.total_files} file{'s' if node.total_files != 1 else ''})"
