"""Result models."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum


class Confidence(str, Enum):
    HIGH = "high"      # never referenced anywhere
    MEDIUM = "medium"  # referenced only within same file
    LOW = "low"        # referenced externally but never called


@dataclass
class DeadSymbol:
    name: str
    kind: str
    path: Path
    line: int
    confidence: Confidence
    reason: str
    is_private: bool
    parent: str | None = None    # enclosing class if method


@dataclass
class UnreferencedFile:
    path: Path
    reason: str


@dataclass
class GhostReport:
    root: Path
    scanned_files: int
    total_symbols: int
    dead_symbols: list[DeadSymbol] = field(default_factory=list)
    unreferenced_files: list[UnreferencedFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def dead_count(self) -> int:
        return len(self.dead_symbols)

    @property
    def high_confidence(self) -> list[DeadSymbol]:
        return [s for s in self.dead_symbols if s.confidence == Confidence.HIGH]

    @property
    def medium_confidence(self) -> list[DeadSymbol]:
        return [s for s in self.dead_symbols if s.confidence == Confidence.MEDIUM]
