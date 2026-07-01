"""Git history mining for heat maps and churn metrics."""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from cartographer.models import GitMetrics

try:
    import git as gitpython
    _GIT_AVAILABLE = True
except ImportError:
    _GIT_AVAILABLE = False


def _open_repo(root: Path):
    if not _GIT_AVAILABLE:
        return None
    try:
        return gitpython.Repo(root, search_parent_directories=True)
    except Exception:
        return None


def get_repo(root: Path):
    return _open_repo(root)


def file_metrics(repo, path: Path, root: Path) -> Optional[GitMetrics]:
    if repo is None:
        return None
    try:
        rel = str(path.relative_to(root))
        commits = list(repo.iter_commits(paths=rel, max_count=500))
        if not commits:
            return None

        authors = {c.author.email for c in commits}
        last = commits[0]
        churn = 0
        try:
            for c in commits:
                stats = c.stats.files.get(rel, {})
                churn += stats.get("insertions", 0) + stats.get("deletions", 0)
        except Exception:
            pass

        return GitMetrics(
            path=path,
            commit_count=len(commits),
            last_commit_date=last.committed_datetime.strftime("%Y-%m-%d"),
            last_commit_message=last.message.strip().splitlines()[0][:80],
            unique_authors=len(authors),
            churn=churn,
        )
    except Exception:
        return None


def build_heat_map(
    repo, files: list[Path], root: Path, window_commits: int = 200
) -> dict[Path, float]:
    """Return normalised heat score (0-1) per file based on recent commit activity."""
    if repo is None:
        return {}

    counts: dict[Path, int] = {}
    try:
        for commit in repo.iter_commits(max_count=window_commits):
            for f in commit.stats.files:
                p = root / f
                if p in set(files):
                    counts[p] = counts.get(p, 0) + 1
    except Exception:
        return {}

    if not counts:
        return {}

    max_count = max(counts.values())
    return {p: round(c / max_count, 3) for p, c in counts.items()}
