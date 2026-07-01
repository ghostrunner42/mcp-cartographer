"""Trace the full git history of a file or directory."""
from __future__ import annotations
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import git


@dataclass
class FileCommit:
    sha: str
    short_sha: str
    message: str
    author: str
    email: str
    timestamp: datetime
    insertions: int
    deletions: int
    is_bug_fix: bool       # commit message starts with "fix" or contains "bug"/"broken"/"crash"
    is_rename: bool        # file was renamed in this commit


@dataclass
class Artifact:
    """The archaeological record of a path."""
    path: str
    exists: bool
    born_at: Optional[datetime]        # timestamp of first commit
    born_sha: Optional[str]
    born_message: Optional[str]
    age_days: int
    total_commits: int
    total_authors: set[str]
    bug_fix_commits: list[FileCommit]  # commits that were bug fixes
    top_contributors: list[tuple[str, int]]  # (author, commit_count) top 5
    commits: list[FileCommit]          # all commits, most recent first
    change_velocity: float             # commits per month (last 3 months)
    stability: str                     # "stable" / "active" / "volatile"
    total_insertions: int
    total_deletions: int
    renames: list[str]                 # previous names of the file


def _is_bug_fix(message: str) -> bool:
    """Return True if the commit message indicates a bug fix."""
    msg_lower = message.lower().strip()
    if msg_lower.startswith("fix"):
        return True
    keywords = ("bug", "broken", "crash", "revert", "hotfix", "patch")
    return any(kw in msg_lower for kw in keywords)


def _stability(commits: list[FileCommit], age_days: int) -> str:
    """Classify file stability based on commit frequency."""
    months = max(age_days / 30, 1)
    cpm = len(commits) / months
    if cpm < 1:
        return "stable"
    elif cpm <= 4:
        return "active"
    else:
        return "volatile"


def dig(path: Path) -> Optional[Artifact]:
    """Dig through git history for the given path and return an Artifact."""
    try:
        repo = git.Repo(
            path if path.is_dir() else path.parent,
            search_parent_directories=True,
        )
    except git.InvalidGitRepositoryError:
        return None
    except git.NoSuchPathError:
        return None

    # Get path relative to repo root
    repo_root = Path(repo.working_tree_dir)
    try:
        rel_path = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return None

    # Run git log with follow to handle renames
    try:
        raw = repo.git.log(
            "--follow",
            "--diff-filter=ACDMRT",
            "--name-status",
            "--format=|||%H|%h|%s|%an|%ae|%aI",
            "--",
            str(rel_path),
        )
    except git.GitCommandError:
        return None

    if not raw.strip():
        return None

    commits: list[FileCommit] = []
    renames: list[str] = []
    seen_renames: set[str] = set()

    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("|||"):
            # Parse commit header: |||sha|short_sha|subject|author|email|timestamp
            parts = line.split("|")
            # parts[0]="" parts[1]="" parts[2]="" parts[3]=sha parts[4]=short_sha
            # parts[5]=subject parts[6]=author parts[7]=email parts[8]=timestamp
            if len(parts) < 9:
                i += 1
                continue
            sha = parts[3]
            short_sha = parts[4]
            message = parts[5]
            author = parts[6]
            email = parts[7]
            ts_str = parts[8]

            # Parse ISO8601 timestamp
            try:
                # Handle timezone offset like +05:30 or Z
                ts_str_clean = ts_str.strip()
                if ts_str_clean.endswith("Z"):
                    ts_str_clean = ts_str_clean[:-1] + "+00:00"
                timestamp = datetime.fromisoformat(ts_str_clean)
                # Ensure timezone-aware
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
            except ValueError:
                timestamp = datetime.now(timezone.utc)

            # Get insertions/deletions for this file in this commit
            insertions = 0
            deletions = 0
            is_rename = False

            # Look ahead for file status lines
            i += 1
            while i < len(lines) and not lines[i].startswith("|||"):
                status_line = lines[i].strip()
                if status_line:
                    status_parts = status_line.split("\t")
                    if status_parts:
                        status_code = status_parts[0]
                        # Rename detection: R100\told\tnew
                        if status_code.startswith("R") and len(status_parts) >= 3:
                            is_rename = True
                            old_name = status_parts[1]
                            if old_name not in seen_renames:
                                seen_renames.add(old_name)
                                renames.append(old_name)
                i += 1

            # Get stats from commit object
            try:
                commit_obj = repo.commit(sha)
                file_stats = commit_obj.stats.files
                # Try to find stats for our file (by current name or any rename)
                for fname, stats in file_stats.items():
                    fname_path = Path(fname)
                    if fname_path == rel_path or fname_path.name == rel_path.name:
                        insertions = stats.get("insertions", 0)
                        deletions = stats.get("deletions", 0)
                        break
            except Exception:
                pass

            fc = FileCommit(
                sha=sha,
                short_sha=short_sha,
                message=message,
                author=author,
                email=email,
                timestamp=timestamp,
                insertions=insertions,
                deletions=deletions,
                is_bug_fix=_is_bug_fix(message),
                is_rename=is_rename,
            )
            commits.append(fc)
        else:
            i += 1

    if not commits:
        return None

    # commits are most-recent-first (git log default order)
    # born_at = oldest commit = last in list
    oldest = commits[-1]
    born_at = oldest.timestamp
    born_sha = oldest.short_sha
    born_message = oldest.message

    now = datetime.now(timezone.utc)
    age_days = (now - born_at).days

    total_authors: set[str] = {c.author for c in commits}
    bug_fix_commits = [c for c in commits if c.is_bug_fix]

    author_counter = Counter(c.author for c in commits)
    top_contributors = author_counter.most_common(5)

    # Change velocity: commits in last 90 days / 3
    cutoff = now.timestamp() - (90 * 24 * 3600)
    recent_commits = [c for c in commits if c.timestamp.timestamp() >= cutoff]
    change_velocity = len(recent_commits) / 3.0

    stability = _stability(commits, age_days)

    total_insertions = sum(c.insertions for c in commits)
    total_deletions = sum(c.deletions for c in commits)

    return Artifact(
        path=str(path),
        exists=path.exists(),
        born_at=born_at,
        born_sha=born_sha,
        born_message=born_message,
        age_days=age_days,
        total_commits=len(commits),
        total_authors=total_authors,
        bug_fix_commits=bug_fix_commits,
        top_contributors=top_contributors,
        commits=commits,
        change_velocity=change_velocity,
        stability=stability,
        total_insertions=total_insertions,
        total_deletions=total_deletions,
        renames=renames,
    )
