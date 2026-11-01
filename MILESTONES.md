# DocuElevate Milestones

**Last updated:** 2026-10-30

This document summarizes planning anchors and their acceptance focus. GitHub milestone descriptions, issues, and current evidence are authoritative for executable scope and status. Issue closure or code availability alone does not establish that a product outcome is complete.

## Release and planning versioning

DocuElevate uses automated semantic versioning. The repository version verified for this update is **0.189.1**. Continuous release numbers are independent of named planning tracks and do not imply milestone completion or determine the next release version. The future `1.0.0` and later labels below are planning anchors, not guaranteed semantic-release tags.

The dates are the existing GitHub milestone targets, retained as planning targets rather than delivery promises. Clarity is due 2026-10-31; open relevance acceptance ([#871](https://github.com/christianlouis/DocuElevate/issues/871)) remains, so the target date is not a completion claim.

## Completed historical anchors

- **v0.3.2 (2026-02-06):** security and testing hardening.
- **v0.3.3 (2026-02-08):** drag-and-drop upload.
- **v0.5.0 (2026-02-08):** database-backed settings, encryption, and setup wizard.

These historical anchors do not describe the current release stream. Refer to GitHub Releases and generated release notes for the release history.

## Release process and compatibility

The historical release cadence is patch releases as needed for critical bugs/security, minor releases approximately every 6–8 weeks, and major releases approximately every 12–18 months. Automated semantic-release may vary this cadence according to merged changes; these intervals are planning guidance, not a schedule commitment.

Conventional commits drive automated versioning on merge to `main`: `feat` produces a minor bump and `fix`/`perf` a patch bump. Breaking-change handling follows [pyproject.toml](pyproject.toml); the current `major_on_zero = false` configuration means a breaking change during `0.x` does not automatically produce `1.0.0`. Other commit types without breaking changes do not bump the version. Automation updates `VERSION`, tags, release notes, GitHub Releases, and image builds. Do not edit `VERSION` or generated changelog output manually.

For breaking API or behavior changes, document the migration path and compatibility window. The existing planning guidance is to retain prior endpoint behavior for at least two minor milestones where applicable. Production promotion remains a separate explicitly approved action; merge, release, and pre-production acceptance do not constitute that approval.

Release readiness continues to require passing tests and security scans, completed code review, updated documentation and release notes, migration guidance for breaking changes, and built/tested Docker images. Published artifacts include source, Docker images, and documentation updates; PyPI distribution and Helm charts remain future distribution goals.

## Planning anchors

### Clarity — Enhanced Search & UI

- **Target:** 2026-10-31; **epic:** [#863](https://github.com/christianlouis/DocuElevate/issues/863); **recorded milestone state:** 14 closed, 2 open (including the epic).
- **Delivered foundations:** semantic/vector and hybrid search ([#477](https://github.com/christianlouis/DocuElevate/issues/477), [#480](https://github.com/christianlouis/DocuElevate/issues/480)); saved searches ([#870](https://github.com/christianlouis/DocuElevate/issues/870)); preview ([#872](https://github.com/christianlouis/DocuElevate/issues/872)); bulk operations ([#873](https://github.com/christianlouis/DocuElevate/issues/873)); ranking explanations and metadata fallback exist in code.
- **Remaining outcome:** tune and accept relevance/configuration and UX ([#871](https://github.com/christianlouis/DocuElevate/issues/871)), with reproducible evidence. Do not describe hybrid search as greenfield work or mark Clarity complete based on issue count.
- **Acceptance:** representative queries meet documented relevance and latency criteria; ranking explanations are understandable; search, filters, saved searches, previews, and bulk actions work together in the supported UI; coverage limitations are visible.

### Conductor — Workflow Automation

- **Target:** 2027-01-31; **epic:** [#864](https://github.com/christianlouis/DocuElevate/issues/864); **recorded milestone state:** 14 closed, 5 open.
- **Remaining outcome:** editable/versioned workflows and rollback ([#875](https://github.com/christianlouis/DocuElevate/issues/875)), general recurring/delayed scheduling ([#876](https://github.com/christianlouis/DocuElevate/issues/876)), reusable starter templates ([#877](https://github.com/christianlouis/DocuElevate/issues/877), [#885](https://github.com/christianlouis/DocuElevate/issues/885)), and bidirectional sync ([#481](https://github.com/christianlouis/DocuElevate/issues/481)). Existing service polling schedules do not satisfy general workflow scheduling.
- **Acceptance:** users can author, validate, publish, inspect, roll back, and safely retry workflows; scheduling and connector behavior is documented and tested for idempotency, failures, and recovery.

### Signal — AI Quality & Multi-language

- **Target:** 2027-04-30; **epic:** [#865](https://github.com/christianlouis/DocuElevate/issues/865); **recorded milestone state:** 5 closed, 8 open.
- **Delivered foundations:** semantic and lexical retrieval, search/chat/research APIs with citations and coverage; extraction evaluation harness and documentation ([#880](https://github.com/christianlouis/DocuElevate/issues/880)); LiteLLM/Ollama extraction option. Chat, evaluation, and local AI must not be described as wholly absent.
- **Remaining outcome:** retrieval and chat outcome acceptance ([#478](https://github.com/christianlouis/DocuElevate/issues/478), [#871](https://github.com/christianlouis/DocuElevate/issues/871)), representative extraction fixtures and CI quality reports/calibration/regression criteria ([#880](https://github.com/christianlouis/DocuElevate/issues/880)), review/feedback workflows, private local embedding/query acceptance ([#479](https://github.com/christianlouis/DocuElevate/issues/479)), multilingual expansion ([#198](https://github.com/christianlouis/DocuElevate/issues/198), [#881](https://github.com/christianlouis/DocuElevate/issues/881), [#1189](https://github.com/christianlouis/DocuElevate/issues/1189)), and large-document support ([#1066](https://github.com/christianlouis/DocuElevate/issues/1066), [#1090](https://github.com/christianlouis/DocuElevate/issues/1090), [#1091](https://github.com/christianlouis/DocuElevate/issues/1091)).
- **Acceptance:** reproducible evaluation sets report relevance, citation quality, coverage, latency, and extraction results against recorded criteria; regressions are gated; review/correction is usable; end-to-end local embedding and query behavior is proven before claiming private local RAG.

### Summit — Enterprise Edition (planning anchor `v1.0.0`)

- **Target:** 2027-09-30; **epic:** [#866](https://github.com/christianlouis/DocuElevate/issues/866); **recorded milestone state:** 12 closed, 16 open.
- **Delivered foundations:** tenant/Tribe fields, personal Tribes, quarantine, scoped SQL/Qdrant, optional shared Tribe onboarding, and per-file privacy enforcement ([#1155](https://github.com/christianlouis/DocuElevate/pull/1155), [#1168](https://github.com/christianlouis/DocuElevate/pull/1168), [#1147](https://github.com/christianlouis/DocuElevate/issues/1147)). These are not full organization administration or RBAC.
- **Remaining outcome:** complete shared Family/Tribe flow ([#1142](https://github.com/christianlouis/DocuElevate/issues/1142)–[#1147](https://github.com/christianlouis/DocuElevate/issues/1147)), organization/team administration ([#199](https://github.com/christianlouis/DocuElevate/issues/199)), RBAC ([#200](https://github.com/christianlouis/DocuElevate/issues/200)), scale ([#201](https://github.com/christianlouis/DocuElevate/issues/201)), SLA ([#211](https://github.com/christianlouis/DocuElevate/issues/211)), admin activity feed ([#882](https://github.com/christianlouis/DocuElevate/issues/882)), SSO ([#883](https://github.com/christianlouis/DocuElevate/issues/883)), and organization quotas ([#884](https://github.com/christianlouis/DocuElevate/issues/884)).
- **Acceptance:** tenant and member permissions are tested across isolation boundaries; administrators can manage organizations, identities, roles, quotas, and SSO; supported scale and recovery behavior have operational evidence.

### Horizon — Platform Expansion (planning anchor `v2.0.0`)

- **Target:** 2028-03-31; **epic:** [#867](https://github.com/christianlouis/DocuElevate/issues/867); **recorded milestone state:** 6 closed, 6 open.
- **Remaining outcome:** plugin foundations ([#220](https://github.com/christianlouis/DocuElevate/issues/220)), SDK ([#886](https://github.com/christianlouis/DocuElevate/issues/886)), marketplace ([#887](https://github.com/christianlouis/DocuElevate/issues/887)), desktop application ([#214](https://github.com/christianlouis/DocuElevate/issues/214)), connector templates, and mature multi-surface support.
- **Acceptance:** documented extension contracts have compatibility and security boundaries; a third-party sample extension installs, runs, upgrades, and is removed through supported flows.

### Sentinel — Governance & Policy (planning anchor `v2.1.0`)

- **Target:** 2028-09-30; **epic:** [#868](https://github.com/christianlouis/DocuElevate/issues/868); **recorded milestone state:** 0 closed, 7 open.
- **Remaining outcome:** retention ([#218](https://github.com/christianlouis/DocuElevate/issues/218)), legal hold ([#888](https://github.com/christianlouis/DocuElevate/issues/888)), PII controls ([#889](https://github.com/christianlouis/DocuElevate/issues/889)), tamper-evident audit ([#890](https://github.com/christianlouis/DocuElevate/issues/890)), KMS ([#891](https://github.com/christianlouis/DocuElevate/issues/891)), and policy management ([#892](https://github.com/christianlouis/DocuElevate/issues/892)).
- **Acceptance:** retention and holds are enforced and recoverably audited; PII policy behavior is validated; privileged changes are tamper-evident; key management and policy failures have documented safe behavior.

### Constellation — Integration Hub & Agent Platform (planning anchor `v3.0.0`)

- **Target:** 2029-03-31; **epic:** [#869](https://github.com/christianlouis/DocuElevate/issues/869); **recorded milestone state:** 0 closed, 5 open.
- **Delivered foundation:** PR [#1281](https://github.com/christianlouis/DocuElevate/pull/1281) added per-user Notion and Evernote destinations and a read-only MCP stdio adapter (`search_documents`, `get_document`) under contract v1.0 ([docs/MCP.md](docs/MCP.md)). MCP requires an enabled and healthy semantic index; code availability does not prove live acceptance.
- **Remaining outcome:** broader MCP interoperability ([#893](https://github.com/christianlouis/DocuElevate/issues/893)), including read-only API token scopes, summaries/actions/shared HTTP; durable signed webhooks ([#894](https://github.com/christianlouis/DocuElevate/issues/894)); audited permissioned actions ([#896](https://github.com/christianlouis/DocuElevate/issues/896)); and connector ecosystem work. Meetily remains deferred.
- **Acceptance:** live connector setup and delivery are verified per provider; MCP scope and authorization are documented and tested; action permissions are least-privilege and auditable; signed event delivery has retry, replay, and recovery evidence.

## Operational acceptance across tracks

Operational work cuts across all milestones. Monitor retry timing and transient database recovery were improved ([#1276](https://github.com/christianlouis/DocuElevate/pull/1276)); bounded OCR/IMAP resources and telemetry privacy were improved ([#1280](https://github.com/christianlouis/DocuElevate/pull/1280)). Remaining tracked areas include host-loss resilience ([#902](https://github.com/christianlouis/DocuElevate/issues/902)), atomic credential state ([#1190](https://github.com/christianlouis/DocuElevate/issues/1190)), archive integrity and partial archive accounting ([#1191](https://github.com/christianlouis/DocuElevate/issues/1191), [#1192](https://github.com/christianlouis/DocuElevate/issues/1192)), backup capacity ([#1193](https://github.com/christianlouis/DocuElevate/issues/1193)), monitor recovery ([#1121](https://github.com/christianlouis/DocuElevate/issues/1121)), credential rotation ([#1162](https://github.com/christianlouis/DocuElevate/issues/1162)), and explicit production approval ([#1201](https://github.com/christianlouis/DocuElevate/issues/1201)). Verify current evidence before treating any as complete.

Production deployment requires its own explicit approval. This document makes no assertion about the current production image, configuration, or live provider acceptance.

## References

- [ROADMAP.md](ROADMAP.md) — product sequencing and outcome acceptance.
- [TODO.md](TODO.md) — short prioritized view; GitHub remains the detailed work queue.
- [GitHub milestones](https://github.com/christianlouis/DocuElevate/milestones) — current scope, dates, and live issue state.

## Support & EOL Policy

### Active Support

- Current stable release: Full support (bug fixes, security patches, features)
- Previous minor release: Security patches only
- Older versions: Community support only

### End of Life (EOL)

- Minor versions: EOL when 2 newer minor versions released
- Major versions: EOL 18 months after next major version

### Security Patches

- Critical vulnerabilities: Patched within 48 hours
- High severity: Patched within 1 week
- Medium/Low: Included in next regular release
