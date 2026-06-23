## 1. Planning

- [x] 1.1 Confirm scope: remove legacy skill files and active references completely.
- [x] 1.2 Preserve `.codex/` as project-local Codex configuration.
- [x] 1.3 Prepare local issue draft instead of creating a remote GitHub issue.

## 2. Documentation And Configuration

- [x] 2.1 Replace legacy skill wording in `AGENTS.md` with Superpowers guidance.
- [x] 2.2 Replace the old configuration spec with a Superpowers/Codex configuration spec.
- [x] 2.3 Update `doc/spec/00_INDEX.md`.
- [x] 2.4 Delete the project-local legacy skill directory.

## 3. Verification

- [x] 3.1 Search for active legacy skill references.
- [x] 3.2 Parse TOML project configuration.
- [x] 3.3 Run `openspec validate --all --strict --no-interactive` if available.
- [x] 3.4 Review diffs before handoff.
