# Release Naming Guide

DocuElevate uses **automated semantic versioning** via [python-semantic-release](https://github.com/python-semantic-release/python-semantic-release) combined with **named release anchors** (codenames) for milestone releases. This guide explains how the two systems work together.

## How It Works

### Automated Versioning (Patch & Minor Releases)

Every merge to `main` is analyzed by `python-semantic-release`:

- **`feat:` commits** → minor version bump (e.g., 0.5.0 → 0.6.0)
- **`fix:` / `perf:` commits** → patch version bump (e.g., 0.5.0 → 0.5.1)
- **`docs:` / `chore:` / etc.** → no version bump

This happens automatically — no manual intervention needed.

### Named Release Anchors (Codenames)

Major milestone releases carry a **codename** that anchors the release in project history. Codenames:

- Are defined in [`release_names.json`](../release_names.json) at the project root
- Map to **minor version ranges** (e.g., all `0.5.x` releases share the codename "Foundation")
- Appear in the status dashboard, build metadata, and footer
- Do **not** interfere with automatic version numbering

### Current Release Names

| Version Range | Codename       | Description                                              |
|---------------|----------------|----------------------------------------------------------|
| 0.5.x         | **Foundation** | Core platform with multi-provider storage, AI, and UI    |
| 0.6.x         | **Clarity**    | Enhanced search, filtering, and improved UI/UX           |
| 0.7.x         | **Conductor**  | Workflow automation, custom pipelines, rule-based logic   |
| 1.0.x         | **Summit**     | Enterprise-ready: multi-tenancy, RBAC, horizontal scaling|
| 1.1.x         | **Bridge**     | Collaboration features, document sharing, analytics      |
| 2.0.x         | **Horizon**    | On-premise AI, advanced management, platform expansion   |

## Adding a New Release Name

1. **Edit `release_names.json`** at the project root:

```json
{
  "releases": {
    "0.8": {
      "codename": "YourCodename",
      "description": "Short description of what this release series focuses on",
      "milestone": "v0.8.0 - Your Milestone Name"
    }
  }
}
```

2. **Update `ROADMAP.md`** to include the codename in the appropriate milestone section.

3. **Update this documentation** to add the new entry to the table above.

The codename will automatically appear in:
- The application footer (all pages)
- The status dashboard (`/status`)
- Build metadata (`RUNTIME_INFO` file)

## How the Lookup Works

The application resolves codenames using a cascading lookup against the current version:

1. **Exact match**: Checks if the full version (e.g., `0.5.3`) has an entry
2. **Minor prefix**: Checks the minor version prefix (e.g., `0.5`)
3. **Major prefix**: Checks the major version prefix (e.g., `0`)

This means all patch releases within a minor version series inherit the same codename.

## Codename Naming Conventions

When choosing codenames, follow these guidelines:

- **Use single, evocative words** that relate to the release's theme
- **Keep names professional** — they appear in user-facing UI
- **Pick names that hint at the milestone's focus** (e.g., "Foundation" for core platform, "Conductor" for workflow automation)
- **Avoid names that could become dated** or reference external products
- **Ensure uniqueness** — no two releases should share a codename

## Integration with Milestones

Each codename maps to a GitHub milestone. The `milestone` field in `release_names.json` matches the milestone title used for issue tracking:

```
v0.7.0 - Workflow Automation  →  codename: "Conductor"
v1.0.0 - Enterprise           →  codename: "Summit"
```

This creates a clear link between planning (milestones), delivery (releases), and communication (codenames).

## Best Practices: Blending Automated and Named Releases

### Do

- ✅ Let semantic-release handle all version numbering automatically
- ✅ Use codenames for **milestone releases** (minor/major versions), not every patch
- ✅ Reference codenames in release notes and changelogs for major versions
- ✅ Keep `release_names.json` in sync with `ROADMAP.md`
- ✅ Announce codenames in GitHub Release descriptions for milestone versions

### Don't

- ❌ Manually edit the `VERSION` file — it's managed by semantic-release
- ❌ Create codenames for every patch release (0.5.1, 0.5.2, etc.)
- ❌ Use codenames that conflict with version numbers
- ❌ Skip updating `release_names.json` when adding a new milestone to the roadmap

## Where Codenames Appear

| Location                | Format                                  |
|-------------------------|-----------------------------------------|
| Status dashboard        | `App Version: 0.5.3 "Foundation"`       |
| Page footer             | `Version 0.5.3 "Foundation"`            |
| RUNTIME_INFO metadata   | `Release Name: Foundation`              |
| ROADMAP.md              | Section headers include codenames       |

## File Reference

| File                      | Purpose                                    |
|---------------------------|--------------------------------------------|
| `release_names.json`      | Source of truth for version-to-codename map|
| `app/config.py`           | `release_name` property reads the JSON     |
| `scripts/generate_build_metadata.sh` | Includes codename in RUNTIME_INFO |
| `app/views/base.py`       | Injects `release_name` into all templates  |
| `ROADMAP.md`              | Displays codenames alongside milestones    |
