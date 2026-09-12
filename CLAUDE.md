## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

### Setup on a new machine

`graphify-out/` is gitignored (build output, multi-megabyte, rebuilt wholesale on
every change). A fresh clone therefore has no graph until it is built:

```bash
py -m pip install --user "graphifyy[sql]"   # Windows; the [sql] extra parses .sql files
graphify extract . --code-only              # local AST, no API key, no token cost
```

Ensure pip's user script directory is on PATH, or the `hook-guard` hooks in
`.claude/settings.json` fail silently on every tool call. On Windows that is
`%APPDATA%\Python\Python3xx\Scripts`.

`.graphifyignore` is committed and defines the scope: it excludes `External Repos/`
(git submodules are gitlinks, so `.gitignore` does not cover them), virtual
environments, and `References/`. Without it the graph fills with vendored
third-party code.

Community names come from hub files, not an LLM — `graphify label` needs
`ANTHROPIC_API_KEY` (or Gemini/OpenAI) and is optional. The claude CLI's login
does not satisfy it.
