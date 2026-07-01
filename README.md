# mcp-cartographer

Codebase intelligence MCP server for Claude. Point it at any local git repository and get instant structural understanding — no GitHub account required, works fully offline.

## Tools

| Tool | What it does |
|------|-------------|
| `map_repo` | Full repo overview: languages, modules, complexity, circular deps, hot files |
| `hot_files` | Most frequently changed files ranked by git commit frequency |
| `file_history` | Deep git archaeology for a specific file: stability, bug fixes, renames, velocity |
| `repo_health` | 0–100 health score: uncommitted files, test coverage, dead code, stale/vulnerable deps |
| `dead_code` | Unused Python symbols (functions, classes, variables) via static analysis |

## Why

[GitHub MCP](https://github.com/github/github-mcp-server) requires code to be on GitHub. mcp-cartographer works on **any local git repo**, offline, with no account. It's fully standalone — no external intelligence engine required.

## Install

**1. Clone this repo:**

```bash
git clone https://github.com/ghostrunner42/mcp-cartographer.git
cd mcp-cartographer
pip install -e .
```

**2. Register with Claude Code:**

```bash
claude mcp add cartographer -s user -- python3 /path/to/mcp-cartographer/server.py
```

Then restart Claude Code. The five tools will be available in every session.

## Usage

```
map_repo("/path/to/your/repo")
hot_files("/path/to/your/repo", limit=20)
file_history("/path/to/your/repo/some/file.py")
repo_health("/path/to/your/repo")
dead_code("/path/to/your/repo", min_confidence="high")
```

All paths accept `~` expansion and absolute paths.

## Notes

- `dead_code` works on Python codebases only. Decorator-registered functions (FastAPI, FastMCP) will show as "unreferenced" — this is a known static analysis limitation.
- `hot_files` and `file_history` require git history. Returns empty on repos with no commits.
- `repo_health` runs test suites if detected. On large repos this may take a few seconds.
- `repo_health`'s dependency check (`drift`) queries PyPI/npm and OSV.dev for version/CVE data — requires network access; degrades gracefully (marks `dependencies.available: false`) if offline.

## License

MIT
