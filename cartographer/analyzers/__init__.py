"""File analyzers — dispatch by language."""
from pathlib import Path
from cartographer.models import FileMetrics
from cartographer.scanner import detect_language
from . import python_analyzer, generic_analyzer


def analyze_file(path: Path) -> FileMetrics | None:
    lang = detect_language(path)
    if lang == "Python":
        return python_analyzer.analyze(path)
    return generic_analyzer.analyze(path)
