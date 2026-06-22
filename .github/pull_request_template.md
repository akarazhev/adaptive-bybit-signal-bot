## Summary

-

## OpenSpec

- [ ] Change is covered by existing `openspec/specs/`
- [ ] New or changed behavior has an OpenSpec proposal/spec/design/tasks
- [ ] `openspec validate --all --strict --no-interactive` passes

## Safety Boundary

- [ ] Does not add Bybit order placement/cancel/amend/transfer/withdraw/leverage execution
- [ ] Keeps API changes GET/read-only, or includes explicit security review
- [ ] Does not read, print, or commit `.env` or real secrets
- [ ] Keeps market recorder opt-in

## Verification

- [ ] `PYTHONPATH=src pytest`
- [ ] `python -m compileall -q src tests`
- [ ] `ruff check .`
- [ ] `mypy src`

## Deployment Impact

- [ ] No deployment impact
- [ ] Container/compose changes verified with `podman build` and `podman compose config`
- [ ] Rollback, health, restart, resource, or storage impact documented
