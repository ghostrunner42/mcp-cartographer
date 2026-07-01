"""Tests for file analyzers."""
import textwrap
from pathlib import Path
from cartographer.analyzers.python_analyzer import analyze


def test_basic_metrics(tmp_path):
    f = tmp_path / "example.py"
    f.write_text(textwrap.dedent("""\
        \"\"\"Module docstring.\"\"\"

        def simple(x):
            if x > 0:
                return x
            return -x

        class Foo:
            pass
    """))
    m = analyze(f)
    assert m is not None
    assert m.language == "Python"
    assert m.lines == 9
    assert m.docstring == "Module docstring."
    assert "simple" in m.exports
    assert "Foo" in m.exports
    assert m.complexity > 0


def test_import_extraction(tmp_path):
    f = tmp_path / "imports.py"
    f.write_text("import os\nimport sys\nfrom pathlib import Path\n")
    m = analyze(f)
    assert m is not None
    assert "os" in m.imports
    assert "sys" in m.imports
    assert "pathlib" in m.imports


def test_todo_counting(tmp_path):
    f = tmp_path / "todos.py"
    f.write_text("x = 1  # TODO: fix this\n# FIXME: and this\n# HACK: ugly\n")
    m = analyze(f)
    assert m is not None
    assert m.todo_count == 3


def test_syntax_error_handled(tmp_path):
    f = tmp_path / "broken.py"
    f.write_text("def broken(\n")
    m = analyze(f)
    assert m is not None
    assert m.language == "Python"
