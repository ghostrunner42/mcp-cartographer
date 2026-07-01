"""Collect health metrics for a project."""
from __future__ import annotations
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class HealthSnapshot:
    timestamp: str          # ISO8601
    project_path: str
    project_name: str       # basename of path

    # Git
    uncommitted_files: int  # count of modified/untracked files
    days_since_commit: float

    # Tests (opportunistic — run pytest/npm test if detected)
    tests_found: bool
    tests_passed: Optional[int]
    tests_failed: Optional[int]
    test_runner: Optional[str]   # "pytest" / "npm" / None

    # Dead code (ghost)
    ghost_available: bool
    dead_symbols_high: Optional[int]
    dead_symbols_total: Optional[int]

    # Dependencies (drift)
    drift_available: bool
    stale_deps: Optional[int]
    vulnerable_deps: Optional[int]

    # Complexity proxy
    py_file_count: int
    ts_file_count: int
    total_lines: int        # rough line count of non-venv source files

    score: int              # 0-100 health score (computed)
    score_notes: list       # reasons for deductions


def _run(cmd: list, cwd: Path, timeout: int = 30) -> tuple:
    """Run a subprocess command, return (returncode, combined_output). Never raises."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        return (result.returncode, combined)
    except Exception as exc:
        return (1, str(exc))


def _git_stats(path: Path) -> tuple:
    """Return (uncommitted_files, days_since_commit)."""
    try:
        rc, out = _run(["git", "-C", str(path), "status", "--porcelain"], path)
        if rc != 0:
            return (0, 0.0)
        uncommitted = sum(1 for line in out.splitlines() if line.strip())

        rc2, out2 = _run(["git", "-C", str(path), "log", "-1", "--format=%aI"], path)
        if rc2 != 0 or not out2.strip():
            return (uncommitted, 0.0)

        ts_str = out2.strip()
        # Parse ISO8601 with timezone offset
        try:
            # Python 3.11+ handles this natively; for 3.10 we normalise the offset
            ts_str_norm = ts_str
            if ts_str_norm.endswith("+00:00") or ts_str_norm.endswith("Z"):
                commit_dt = datetime.fromisoformat(ts_str_norm.replace("Z", "+00:00"))
            else:
                commit_dt = datetime.fromisoformat(ts_str_norm)
        except ValueError:
            return (uncommitted, 0.0)

        now = datetime.now(timezone.utc)
        days = (now - commit_dt).total_seconds() / 86400.0
        return (uncommitted, days)
    except Exception:
        return (0, 0.0)


def _test_stats(path: Path) -> tuple:
    """Return (tests_found, passed, failed, runner)."""
    # Check for pytest
    pytest_detected = False
    if (path / "pytest.ini").exists() or (path / "tests").is_dir():
        pytest_detected = True
    elif (path / "pyproject.toml").exists():
        try:
            content = (path / "pyproject.toml").read_text()
            if "pytest" in content:
                pytest_detected = True
        except Exception:
            pass

    if pytest_detected:
        runner = "pytest"
        # Try venv pytest first, fall back to python -m pytest
        venv_pytest = path / ".venv" / "bin" / "pytest"
        if venv_pytest.exists():
            cmd = [str(venv_pytest), "--tb=no", "-q"]
        else:
            cmd = ["python", "-m", "pytest", "--tb=no", "-q"]

        rc, out = _run(cmd, path, timeout=60)
        passed = None
        failed = None
        for line in out.splitlines():
            # Match patterns like "3 passed, 1 failed" or "3 passed" or "1 failed"
            import re
            m = re.search(r"(\d+) passed", line)
            if m:
                passed = int(m.group(1))
            m2 = re.search(r"(\d+) failed", line)
            if m2:
                failed = int(m2.group(1))
        return (True, passed, failed, runner)

    # Check for npm
    if (path / "package.json").exists():
        runner = "npm"
        rc, out = _run(["npm", "test", "--if-present"], path, timeout=120)
        # npm test output varies widely; just report found
        return (True, None, None, runner)

    return (False, None, None, None)


def _ghost_stats(path: Path) -> tuple:
    """Return (ghost_available, high_count, total_count)."""
    try:
        from ghost import analyzer
        report = analyzer.run(path, include_private=False)
        high_count = sum(1 for s in report.dead_symbols if s.confidence.value == "high")
        total_count = len(report.dead_symbols)
        return (True, high_count, total_count)
    except Exception:
        return (False, None, None)


def _drift_stats(path: Path) -> tuple:
    """Return (drift_available, stale_deps, vulnerable_deps)."""
    try:
        from drift import parser, checker
        deps = parser.discover(path)
        if not deps:
            return (True, 0, 0)
        deps = [d for d in deps if not d.dev]
        results = checker.check_all(deps, {d.name: "pypi" for d in deps})
        stale = sum(1 for r in results if r.is_outdated)
        vulnerable = sum(1 for r in results if r.vulns)
        return (True, stale, vulnerable)
    except Exception:
        return (False, None, None)


def _file_stats(path: Path) -> tuple:
    """Return (py_file_count, ts_file_count, total_lines)."""
    skip_dirs = {".venv", ".git", "node_modules", "__pycache__", ".tox", "venv", "env"}
    py_count = 0
    ts_count = 0
    total_lines = 0

    def _walk(p: Path) -> None:
        nonlocal py_count, ts_count, total_lines
        try:
            for entry in p.iterdir():
                if entry.is_dir():
                    if entry.name in skip_dirs:
                        continue
                    _walk(entry)
                elif entry.is_file():
                    suffix = entry.suffix.lower()
                    if suffix == ".py":
                        py_count += 1
                        try:
                            total_lines += entry.read_text(errors="ignore").count("\n")
                        except Exception:
                            pass
                    elif suffix in (".ts", ".tsx"):
                        ts_count += 1
                        try:
                            total_lines += entry.read_text(errors="ignore").count("\n")
                        except Exception:
                            pass
        except PermissionError:
            pass

    _walk(path)
    return (py_count, ts_count, total_lines)


def _compute_score(snap: HealthSnapshot) -> tuple:
    """Return (score, notes) with deductions from 100."""
    score = 100
    notes = []

    if snap.uncommitted_files > 10:
        score -= 10
        notes.append(f"{snap.uncommitted_files} uncommitted files (>10)")
    elif snap.uncommitted_files > 0:
        score -= 5
        notes.append(f"{snap.uncommitted_files} uncommitted files")

    if snap.days_since_commit > 30:
        score -= 15
        notes.append(f"{snap.days_since_commit:.1f} days since last commit (>30)")

    if snap.tests_failed and snap.tests_failed > 0:
        score -= 20
        notes.append(f"{snap.tests_failed} test(s) failing")

    if snap.dead_symbols_high and snap.dead_symbols_high > 20:
        score -= 10
        notes.append(f"{snap.dead_symbols_high} high-confidence dead symbols (>20)")

    if snap.vulnerable_deps and snap.vulnerable_deps > 0:
        score -= 10
        notes.append(f"{snap.vulnerable_deps} vulnerable dep(s)")

    if snap.stale_deps and snap.stale_deps > 5:
        score -= 5
        notes.append(f"{snap.stale_deps} stale dep(s) (>5)")

    score = max(0, min(100, score))
    return (score, notes)


def collect(path: Path) -> HealthSnapshot:
    """Collect all health metrics and return a HealthSnapshot."""
    path = path.resolve()
    project_name = path.name
    timestamp = datetime.now(timezone.utc).isoformat()

    uncommitted_files, days_since_commit = _git_stats(path)
    tests_found, tests_passed, tests_failed, test_runner = _test_stats(path)
    ghost_available, dead_symbols_high, dead_symbols_total = _ghost_stats(path)
    drift_available, stale_deps, vulnerable_deps = _drift_stats(path)
    py_file_count, ts_file_count, total_lines = _file_stats(path)

    snap = HealthSnapshot(
        timestamp=timestamp,
        project_path=str(path),
        project_name=project_name,
        uncommitted_files=uncommitted_files,
        days_since_commit=days_since_commit,
        tests_found=tests_found,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        test_runner=test_runner,
        ghost_available=ghost_available,
        dead_symbols_high=dead_symbols_high,
        dead_symbols_total=dead_symbols_total,
        drift_available=drift_available,
        stale_deps=stale_deps,
        vulnerable_deps=vulnerable_deps,
        py_file_count=py_file_count,
        ts_file_count=ts_file_count,
        total_lines=total_lines,
        score=0,
        score_notes=[],
    )

    score, notes = _compute_score(snap)
    snap.score = score
    snap.score_notes = notes
    return snap
