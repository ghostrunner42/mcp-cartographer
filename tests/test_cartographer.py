"""Integration test — run the full pipeline on a synthetic repo."""
import textwrap
from pathlib import Path
from cartographer.cartographer import run
from cartographer.renderers.llm import render_json, render_markdown
import json


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()

    (tmp_path / "src" / "main.py").write_text(textwrap.dedent("""\
        \"\"\"Application entry point.\"\"\"
        import os
        from src import utils

        def main():
            if os.getenv("DEBUG"):
                print("debug")
            utils.run()
    """))
    (tmp_path / "src" / "utils.py").write_text(textwrap.dedent("""\
        \"\"\"Utility helpers.\"\"\"
        # TODO: add more helpers

        def run():
            pass
    """))
    (tmp_path / "tests" / "test_main.py").write_text(textwrap.dedent("""\
        from src import main

        def test_smoke():
            assert True
    """))
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'synth'\n")
    return tmp_path


def test_full_pipeline(tmp_path):
    root = _make_repo(tmp_path)
    result = run(root)

    assert result.scanned_files == 4
    assert result.dominant_language == "Python"
    assert result.total_lines > 0
    assert not result.has_git
    assert len(result.modules) > 0


def test_json_output(tmp_path):
    result = run(_make_repo(tmp_path))
    j = json.loads(render_json(result))
    assert j["repo"] == tmp_path.name
    assert j["stats"]["dominant_language"] == "Python"
    assert isinstance(j["modules"], list)


def test_markdown_output(tmp_path):
    result = run(_make_repo(tmp_path))
    md = render_markdown(result)
    assert "# Codebase Map" in md
    assert "## Module Map" in md
    assert "| Module |" in md
