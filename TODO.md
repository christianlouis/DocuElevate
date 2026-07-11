# DocuElevate Work Queue

**Last Updated:** 2026-07-11

GitHub issues and milestones are the single source of truth for actionable work.
This file intentionally does not duplicate issue checklists, which previously
drifted behind the implementation and release stream.

## Current order

1. **Correctness and resilience:** #1007, #388, #902
2. **Search UX:** #870, #872, #873
3. **Retrieval foundation:** #477, #480, #871
4. **Workflow authoring:** #875, #876, #877 (after #388)
5. **AI quality:** #880, then #878 and #879

See [ROADMAP.md](ROADMAP.md) for the dependency-led product sequence and
[MILESTONES.md](MILESTONES.md) for the named planning anchors. Check `VERSION` or
GitHub Releases for the current semantic-release version.

## Maintenance rule

- Put new executable work in a GitHub issue with acceptance criteria, an area
  label, one priority label, and a milestone when it belongs to a named track.
- Keep architectural intent in the roadmap and detailed implementation work in
  issues.
- Do not manually edit `VERSION` or generated changelog output.
