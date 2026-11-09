---
name: generate-tasks
description: Turns a PRD or feature request into a checkbox task list using the ai-dev-tasks workflow. Generates parent tasks first, waits for "Go", then adds sub-tasks and relevant files, and saves tasks/tasks-[feature-name].md. Use when the user says "generate tasks", "/generate-tasks", "break this PRD into tasks", or after create-prd finishes.
---

# Generate Tasks

Read `External Repos/PRD/generate-tasks.md` (repo root) and follow it exactly. That file is the source of truth; this skill only points to it so it stays in sync with upstream (snarktank/ai-dev-tasks).

If the file is missing, the submodule is not checked out. Run `git submodule update --init "External Repos/PRD"` and read it again.

If the user names no input, use the newest `tasks/prd-*.md`.
