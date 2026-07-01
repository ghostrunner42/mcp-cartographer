"""Generic analyzer for non-Python files — counts lines, TODOs, imports."""
from __future__ import annotations
import re
from pathlib import Path
from cartographer.models import FileMetrics
from cartographer.scanner import detect_language

TODO_RE = re.compile(r"(TODO|FIXME|HACK|XXX|BUG)\b", re.IGNORECASE)

# Very light import sniffers for common languages
_IMPORT_PATTERNS: dict[str, re.Pattern] = {
    "JavaScript": re.compile(
        r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\(['"]([^'"]+)['"]\))""",
        re.MULTILINE,
    ),
    "TypeScript": re.compile(
        r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\(['"]([^'"]+)['"]\))""",
        re.MULTILINE,
    ),
    "Go": re.compile(r'"([^"]+)"', re.MULTILINE),
    "Rust": re.compile(r"^use\s+([\w:]+)", re.MULTILINE),
}


def _sniff_imports(source: str, language: str) -> list[str]:
    pattern = _IMPORT_PATTERNS.get(language)
    if not pattern:
        return []
    matches = pattern.findall(source)
    results = []
    for m in matches:
        val = m if isinstance(m, str) else next((x for x in m if x), "")
        if val:
            results.append(val)
    return list(dict.fromkeys(results))


def analyze(path: Path) -> FileMetrics | None:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    lang = detect_language(path)
    lines = source.splitlines()
    blank = sum(1 for l in lines if not l.strip())
    comment = sum(
        1 for l in lines
        if l.strip().startswith(("#", "//", "--", "/*", "*", "<!--"))
    )
    todos = len(TODO_RE.findall(source))
    imports = _sniff_imports(source, lang)

    return FileMetrics(
        path=path,
        language=lang,
        lines=len(lines),
        blank_lines=blank,
        comment_lines=comment,
        complexity=0.0,
        max_complexity=0.0,
        todo_count=todos,
        imports=imports,
    )
