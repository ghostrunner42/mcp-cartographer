"""Tests for the file scanner."""
import tempfile
from pathlib import Path
from cartographer.scanner import scan, detect_language, dominant_language


def test_detect_language():
    assert detect_language(Path("foo.py")) == "Python"
    assert detect_language(Path("foo.ts")) == "TypeScript"
    assert detect_language(Path("Dockerfile")) == "Docker"
    assert detect_language(Path("unknown.xyz")) == "Other"


def test_dominant_language_prefers_code_over_config():
    langs = {"Python": 10, "Markdown": 50, "YAML": 5}
    assert dominant_language(langs) == "Python"


def test_scan_respects_gitignore(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hello')")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("module.exports = {}")
    (tmp_path / ".gitignore").write_text("node_modules/\n")

    found = [p.name for p in scan(tmp_path)]
    assert "main.py" in found
    assert "pkg.js" not in found


def test_scan_skips_binary(tmp_path):
    (tmp_path / "real.py").write_text("x = 1")
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\x03")

    found = [p.name for p in scan(tmp_path)]
    assert "real.py" in found
    assert "binary.bin" not in found
