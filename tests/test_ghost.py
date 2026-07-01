"""Tests for ghost's dead-code analysis."""
import textwrap
from pathlib import Path
from ghost.analyzer import run


def _names(report, confidence="high"):
    return {s.name for s in report.dead_symbols if s.confidence.value == confidence}


def test_flags_genuinely_unreferenced_function(tmp_path):
    (tmp_path / "mod.py").write_text("def unused():\n    return 1\n")
    report = run(tmp_path, include_private=False)
    assert "unused" in _names(report)


def test_registration_decorator_not_flagged_dead(tmp_path):
    """Functions registered via `@mcp.tool()` are called by the MCP runtime,
    not by name from within the codebase — ghost must not flag them."""
    (tmp_path / "server.py").write_text(textwrap.dedent("""\
        class FastMCP:
            def tool(self):
                def wrap(fn):
                    return fn
                return wrap

        mcp = FastMCP()

        @mcp.tool()
        def map_repo(path: str) -> dict:
            return {}
    """))
    report = run(tmp_path, include_private=False)
    assert "map_repo" not in _names(report)


def test_click_command_not_flagged_dead(tmp_path):
    (tmp_path / "cli.py").write_text(textwrap.dedent("""\
        import click

        @click.command()
        def run_scan():
            pass
    """))
    report = run(tmp_path, include_private=False)
    assert "run_scan" not in _names(report)
