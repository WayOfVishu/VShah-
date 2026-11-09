---
name: create-prd
description: Writes a Product Requirements Document (PRD) for a feature using the ai-dev-tasks workflow. Asks 3-5 lettered clarifying questions first, then saves tasks/prd-[feature-name].md written for a junior developer. Use when the user says "create a PRD", "write a PRD", "/create-prd", or wants a PRD before generating a task list. Pairs with generate-tasks.
---

# Create PRD

Read `External Repos/PRD/create-prd.md` (repo root) and follow it exactly. That file is the source of truth; this skill only points to it so it stays in sync with upstream (snarktank/ai-dev-tasks).

If the file is missing, the submodule is not checked out. Run `git submodule update --init "External Repos/PRD"` and read it again.

Do not start implementing. When the PRD is saved, offer the `generate-tasks` skill as the next step.
