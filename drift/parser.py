"""Parse dependency manifests across package managers."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class Dependency:
    name: str
    declared_version: str   # raw constraint string, e.g. ">=1.2,<3"
    source: str             # "pyproject.toml", "requirements.txt", "package.json"
    dev: bool = False


def _normalise_pypi(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _strip_version_spec(spec: str) -> str:
    """Return just the constraint, stripping extras like [security]."""
    spec = re.sub(r"\[.*?\]", "", spec).strip()
    return spec


def parse_pyproject(path: Path) -> list[Dependency]:
    try:
        data = tomllib.loads(path.read_text())
    except Exception:
        return []

    deps: list[Dependency] = []
    project = data.get("project", {})

    for raw in project.get("dependencies", []):
        # "click>=8.1" or "httpx" or "tomli>=2.0; python_version < '3.11'"
        raw = raw.split(";")[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)(.*)", raw)
        if m:
            deps.append(Dependency(
                name=_normalise_pypi(m.group(1)),
                declared_version=_strip_version_spec(m.group(2).strip()),
                source=str(path),
                dev=False,
            ))

    optional = project.get("optional-dependencies", {})
    for group, pkgs in optional.items():
        for raw in pkgs:
            raw = raw.split(";")[0].strip()
            m = re.match(r"^([A-Za-z0-9_.\-]+)(.*)", raw)
            if m:
                deps.append(Dependency(
                    name=_normalise_pypi(m.group(1)),
                    declared_version=_strip_version_spec(m.group(2).strip()),
                    source=str(path),
                    dev=True,
                ))

    return deps


def parse_requirements(path: Path) -> list[Dependency]:
    deps = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []

    for line in lines:
        line = line.strip()
        if not line or line.startswith(("#", "-r", "-c", "--")):
            continue
        line = line.split(";")[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)(.*)", line)
        if m:
            deps.append(Dependency(
                name=_normalise_pypi(m.group(1)),
                declared_version=m.group(2).strip(),
                source=str(path),
                dev=False,
            ))
    return deps


def parse_package_json(path: Path) -> list[Dependency]:
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []

    deps = []
    for name, ver in data.get("dependencies", {}).items():
        deps.append(Dependency(name=name, declared_version=ver, source=str(path), dev=False))
    for name, ver in data.get("devDependencies", {}).items():
        deps.append(Dependency(name=name, declared_version=ver, source=str(path), dev=True))
    return deps


def discover(root: Path) -> list[Dependency]:
    deps: list[Dependency] = []
    seen: set[str] = set()  # deduplicate by (name, source filename)

    for candidate in [
        root / "pyproject.toml",
        root / "setup.cfg",
    ]:
        if candidate.exists():
            for d in parse_pyproject(candidate) if candidate.suffix == ".toml" else []:
                key = (d.name, candidate.name)
                if key not in seen:
                    seen.add(key)
                    deps.append(d)

    for req in root.glob("requirements*.txt"):
        for d in parse_requirements(req):
            key = (d.name, req.name)
            if key not in seen:
                seen.add(key)
                deps.append(d)

    pkg_json = root / "package.json"
    if pkg_json.exists():
        for d in parse_package_json(pkg_json):
            key = (d.name, "package.json")
            if key not in seen:
                seen.add(key)
                deps.append(d)

    return deps
