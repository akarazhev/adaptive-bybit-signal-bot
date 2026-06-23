# Replace Legacy Agent Skills With Superpowers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the legacy local agent skill bundle from the repository and document Superpowers as the active agent workflow surface.

**Architecture:** This is a documentation and governance cleanup. It deletes the legacy local skill directory, updates active instructions, replaces the legacy configuration spec with a Superpowers/Codex configuration spec, and records the migration through OpenSpec.

**Tech Stack:** Markdown, OpenSpec, Codex project config, Superpowers skills.

---

### Task 1: Record Governance Migration

**Files:**
- Create: `openspec/changes/replace-ecc-with-superpowers/proposal.md`
- Create: `openspec/changes/replace-ecc-with-superpowers/design.md`
- Create: `openspec/changes/replace-ecc-with-superpowers/tasks.md`
- Create: `openspec/changes/replace-ecc-with-superpowers/issue-draft.md`
- Create: `openspec/changes/replace-ecc-with-superpowers/specs/production-governance/spec.md`

- [ ] **Step 1: Add OpenSpec proposal**

Write a proposal that states the legacy skill surface is being removed from active project configuration and Superpowers becomes the active skill workflow.

- [ ] **Step 2: Add OpenSpec design**

Write the design with scope, non-goals, safety boundary, and rollback.

- [ ] **Step 3: Add OpenSpec tasks and issue draft**

Record the implementation checklist and a local issue draft because remote GitHub issue writes require approval.

### Task 2: Update Active Instructions

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Replace legacy daily skills section**

Replace the legacy daily-skills section with Superpowers usage guidance while keeping OpenSpec, SDD, issue-history, review, safety, development workflow, and verification rules.

### Task 3: Replace Configuration Spec

**Files:**
- Delete: old configuration spec
- Create: `doc/spec/10_SUPERPOWERS_CODEX_CONFIGURATION.md`
- Modify: `doc/spec/00_INDEX.md`

- [ ] **Step 1: Replace spec document**

Write a Superpowers/Codex configuration document that describes `.codex/`, Superpowers skills, and retained project safety rules.

- [ ] **Step 2: Update index**

Point the document list and description at `10_SUPERPOWERS_CODEX_CONFIGURATION.md`.

### Task 4: Remove Legacy Skill Files

**Files:**
- Delete: legacy local skill files

- [ ] **Step 1: Delete project-local legacy skills**

Remove the legacy local skill directory from the repository.

### Task 5: Verify

**Files:**
- Read-only verification across repository.

- [ ] **Step 1: Search for active legacy references**

Run `rg -n "<old legacy-skill markers>" AGENTS.md doc openspec .github .codex pyproject.toml .gitignore`.
Expected: no matches.

- [ ] **Step 2: Parse TOML**

Run `python3 -c 'import tomllib; from pathlib import Path; [tomllib.loads(Path(f).read_text()) for f in ["pyproject.toml", ".codex/config.toml", ".codex/agents/docs-researcher.toml", ".codex/agents/explorer.toml", ".codex/agents/reviewer.toml"]]; print("toml ok")'`.
Expected: `toml ok`.

- [ ] **Step 3: Validate OpenSpec**

Run `openspec validate --all --strict --no-interactive`.
Expected: validation passes, or report that `openspec` is unavailable.
