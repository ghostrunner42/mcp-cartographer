"""Save and load health snapshots."""
from __future__ import annotations
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sentinel.metrics import HealthSnapshot

MEMORY_DIR = (
    Path.home()
    / ".claude"
    / "projects"
    / "-home-jessman"
    / "memory"
    / "sentinel"
)

FLAGS_DIR = (
    Path.home()
    / ".claude"
    / "projects"
    / "-home-jessman"
    / "memory"
    / "flags"
)


def save(snap: HealthSnapshot, project_name: str) -> Path:
    """Persist a snapshot to MEMORY_DIR/<project_name>/<date>.json."""
    dest_dir = MEMORY_DIR / project_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = snap.timestamp[:10] + ".json"  # YYYY-MM-DD
    dest = dest_dir / filename
    dest.write_text(json.dumps(asdict(snap), indent=2))
    return dest


def load_history(project_name: str, limit: int = 30) -> list:
    """Load up to `limit` snapshots for project_name, newest first."""
    project_dir = MEMORY_DIR / project_name
    if not project_dir.is_dir():
        return []

    snapshots = []
    for f in sorted(project_dir.glob("*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(f.read_text())
            snap = HealthSnapshot(**data)
            snapshots.append(snap)
        except Exception:
            continue
    return snapshots


def latest(project_name: str) -> Optional[HealthSnapshot]:
    """Return the most recent snapshot, or None if no history."""
    history = load_history(project_name, limit=1)
    return history[0] if history else None


def _flag_path(project_name: str, flag_type: str) -> Path:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return FLAGS_DIR / project_name / f"{today}-{flag_type}.flag"


def write_flags(snap: HealthSnapshot) -> list:
    """Write flag files for crossed thresholds; clear resolved ones.

    Returns list of Paths that were written (not deleted).
    """
    project_name = snap.project_name
    flag_dir = FLAGS_DIR / project_name
    flag_dir.mkdir(parents=True, exist_ok=True)

    written: list = []

    def _write(flag_type: str, level: str, message: str, detail: str) -> None:
        path = _flag_path(project_name, flag_type)
        payload = {
            "level": level,
            "type": flag_type,
            "message": message,
            "detail": detail,
            "project": project_name,
            "written_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2))
        written.append(path)

    def _clear(flag_type: str) -> None:
        # Remove any existing flags of this type (any date) to avoid stale flags
        for stale in flag_dir.glob(f"*-{flag_type}.flag"):
            try:
                stale.unlink()
            except FileNotFoundError:
                pass

    # tests-failing
    if snap.tests_failed and snap.tests_failed > 0:
        _clear("tests-failing")
        detail = (
            f"test_runner: {snap.test_runner} | "
            f"passed: {snap.tests_passed} | "
            f"failed: {snap.tests_failed}"
        )
        _write("tests-failing", "critical", f"{snap.tests_failed} tests failing", detail)
    else:
        _clear("tests-failing")

    # vulnerable-deps
    if snap.vulnerable_deps and snap.vulnerable_deps > 0:
        _clear("vulnerable-deps")
        detail = f"drift_available: {snap.drift_available} | vulnerable: {snap.vulnerable_deps}"
        _write(
            "vulnerable-deps",
            "critical",
            f"{snap.vulnerable_deps} vulnerable dependencies",
            detail,
        )
    else:
        _clear("vulnerable-deps")

    # health-critical / health-warning (mutually exclusive)
    score = snap.score
    if score < 60:
        _clear("health-critical")
        _clear("health-warning")
        _write(
            "health-critical",
            "critical",
            f"Health score dropped to {score}/100",
            f"score: {score} | notes: {'; '.join(snap.score_notes)}",
        )
    elif score < 80:
        _clear("health-warning")
        _clear("health-critical")
        _write(
            "health-warning",
            "attention",
            f"Health score {score}/100",
            f"score: {score} | notes: {'; '.join(snap.score_notes)}",
        )
    else:
        _clear("health-critical")
        _clear("health-warning")

    # stale-deps
    if snap.stale_deps is not None and snap.stale_deps > 5:
        _clear("stale-deps")
        detail = f"drift_available: {snap.drift_available} | stale: {snap.stale_deps}"
        _write(
            "stale-deps",
            "attention",
            f"{snap.stale_deps} stale dependencies",
            detail,
        )
    else:
        _clear("stale-deps")

    # stale-repo
    if snap.days_since_commit > 14:
        _clear("stale-repo")
        _write(
            "stale-repo",
            "attention",
            f"No commits in {int(snap.days_since_commit)} days",
            f"days_since_commit: {snap.days_since_commit:.1f}",
        )
    else:
        _clear("stale-repo")

    return written
