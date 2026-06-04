# Evergreen 0.30 Release Line

`release-evergreen-0.30` is the maintained 0.30.x production line.

This branch starts from the production-proven 0.30.2 codebase and carries only
targeted operational backports:

- security patches
- dependency and runtime compatibility fixes
- selected production features that are explicitly approved for the 0.30 line
- observability and status-page improvements that do not change product flows

Do not use this branch for broad mainline upgrades. Backports should stay small,
reviewable, and production-oriented.

Images are built automatically on every push to this branch. The expected image
tags are:

- `ghcr.io/christianlouis/docuelevate:release-evergreen-0.30`
- `ghcr.io/christianlouis/docuelevate:release-evergreen-0.30-<shortsha>`

