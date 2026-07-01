"""Check versions against PyPI/npm and CVEs against OSV.dev."""
from __future__ import annotations
import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional
import httpx

PYPI_URL = "https://pypi.org/pypi/{package}/json"
NPM_URL = "https://registry.npmjs.org/{package}/latest"
OSV_URL = "https://api.osv.dev/v1/query"

_TIMEOUT = httpx.Timeout(10.0)


@dataclass
class VersionInfo:
    latest: Optional[str]
    is_outdated: bool
    majors_behind: int


@dataclass
class Vuln:
    id: str
    summary: str
    severity: str       # "CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"
    aliases: list[str] = field(default_factory=list)


async def _fetch_pypi_latest(client: httpx.AsyncClient, name: str) -> Optional[str]:
    try:
        r = await client.get(PYPI_URL.format(package=name), timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json().get("info", {}).get("version")
    except Exception:
        pass
    return None


async def _fetch_npm_latest(client: httpx.AsyncClient, name: str) -> Optional[str]:
    try:
        r = await client.get(NPM_URL.format(package=name), timeout=_TIMEOUT)
        if r.status_code == 200:
            return r.json().get("version")
    except Exception:
        pass
    return None


async def _fetch_vulns(client: httpx.AsyncClient, name: str, ecosystem: str) -> list[Vuln]:
    try:
        payload = {"package": {"name": name, "ecosystem": ecosystem}}
        r = await client.post(OSV_URL, json=payload, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        vulns = []
        for v in r.json().get("vulns", []):
            severity = "UNKNOWN"
            for s in v.get("severity", []):
                score = s.get("score", "")
                if "CRITICAL" in score:
                    severity = "CRITICAL"
                    break
                elif "HIGH" in score:
                    severity = "HIGH"
                elif "MEDIUM" in score and severity not in ("HIGH",):
                    severity = "MEDIUM"
                elif "LOW" in score and severity == "UNKNOWN":
                    severity = "LOW"
            vulns.append(Vuln(
                id=v.get("id", ""),
                summary=v.get("summary", "")[:120],
                severity=severity,
                aliases=v.get("aliases", [])[:3],
            ))
        return vulns
    except Exception:
        return []


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in re.split(r"[.\-]", v.lstrip("^~>=<! ").split(",")[0])[:3])
    except Exception:
        return (0,)


def _majors_behind(declared: str, latest: str) -> int:
    d = _parse_version(declared)
    l = _parse_version(latest)
    if not d or not l:
        return 0
    return max(0, l[0] - d[0])


def _is_outdated(declared: str, latest: str) -> bool:
    d = _parse_version(declared)
    l = _parse_version(latest)
    return l > d


@dataclass
class DepResult:
    name: str
    declared_version: str
    latest_version: Optional[str]
    is_outdated: bool
    majors_behind: int
    vulns: list[Vuln]
    used_in_source: bool
    dev: bool
    ecosystem: str   # "pypi" or "npm"

    @property
    def severity(self) -> str:
        if not self.vulns:
            return "none"
        order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
        for s in order:
            if any(v.severity == s for v in self.vulns):
                return s
        return "none"


async def _check_one(
    client: httpx.AsyncClient,
    name: str,
    declared: str,
    ecosystem: str,
    dev: bool,
) -> DepResult:
    if ecosystem == "pypi":
        latest = await _fetch_pypi_latest(client, name)
    else:
        latest = await _fetch_npm_latest(client, name)

    vulns = await _fetch_vulns(client, name, "PyPI" if ecosystem == "pypi" else "npm")

    current_ver = re.sub(r"[^0-9.]", "", declared.split(",")[0]) or "0"
    outdated = _is_outdated(current_ver, latest) if latest else False
    maj = _majors_behind(current_ver, latest) if latest else 0

    return DepResult(
        name=name,
        declared_version=declared,
        latest_version=latest,
        is_outdated=outdated,
        majors_behind=maj,
        vulns=vulns,
        used_in_source=False,   # filled in by usage scanner
        dev=dev,
        ecosystem=ecosystem,
    )


async def check_all_async(deps, ecosystem_map: dict[str, str]) -> list[DepResult]:
    async with httpx.AsyncClient() as client:
        tasks = [
            _check_one(client, d.name, d.declared_version, ecosystem_map.get(d.name, "pypi"), d.dev)
            for d in deps
        ]
        return await asyncio.gather(*tasks)


def check_all(deps, ecosystem_map: dict[str, str]) -> list[DepResult]:
    return asyncio.run(check_all_async(deps, ecosystem_map))
