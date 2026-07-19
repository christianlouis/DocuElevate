# DocuElevate Roadmap

**Last Updated:** 2026-07-19
**Version:** 2.3

## Vision

DocuElevate aims to be the premier open-source intelligent document processing platform, providing seamless integration with cloud storage providers, advanced AI-powered metadata extraction, and enterprise-grade security and scalability.

## How to Read This Roadmap

DocuElevate ships frequently (automated semantic versioning), so this roadmap is organized around **milestone outcomes** and **themes**, not exact build numbers.

- **P0** = required for the milestone to feel “done”
- **P1** = strongly desired; may slip if needed
- **P2** = nice-to-have / opportunistic

For the detailed milestone breakdown and target dates, see [MILESTONES.md](MILESTONES.md).

## Current Focus and Delivery Order

The automated release number (`0.188.2` at the time of this review) is independent
from the named planning anchors below. The team should execute work in dependency
order, not in numeric-anchor order:

1. **Close the active security and privacy gaps** — rotate the affected Preprod
   credentials (#1162), complete owner/Tribe assignment for legacy corpora, and
   keep secret values out of GitOps, diagnostics, and browser responses. The
   single-user privacy regression (#1170) is closed; its guardrails stay mandatory.
2. **Make a clean installation genuinely useful** — finish the disposable
   fresh-install journey (#1134, #1151), including integrations, a first processed
   document, a second isolated user, recovery paths, and browser E2E evidence.
3. **Complete Family/Tribe document separation** — deliver recipient profiles,
   explainable classification, per-user routing, review, invitations, delegated
   administration, and owner-controlled privacy (#1142–#1147).
4. **Finish retrieval quality rather than widening brute-force context** — tune
   hybrid ranking (#871), add an evaluation harness (#880), and only then close
   Chat with Library (#478) against cited-answer quality and latency targets.
5. **Remove operational single points of failure** — executable backup creation
   and restore acceptance are complete (#1062, #1102). Next, make credential
   monitor state transactional (#1190), verify protected archives before retention
   (#1191), account for abandoned partial archives (#1192), estimate first-backup
   capacity conservatively (#1193), harden maintenance monitors (#1103, #1121),
   and finish the single-host-loss resilience plan (#902).
6. **Build later enterprise and ecosystem layers on proven contracts** — workflow
   editing, RBAC, full organization management, audit, plugins, governance, MCP,
   and agent actions remain sequenced behind the user-facing foundations above.

GitHub issues and milestones are the source of truth for executable scope. This
document explains sequencing and product intent; it should not duplicate a sprint
backlog.

Production promotion is not implied by a merge or Preprod acceptance. The
production deployment remains pinned to its explicitly approved Evergreen legacy
image until a separate manual production approval is given.

The current issue inventory also contains post-merge follow-ups. Before starting
one, verify it against `main` and existing regression tests; close already-delivered
findings with evidence instead of carrying stale work forward.

## Preprod Pilot: DearConcierge Knowledge Bridge

The first agent-facing document retrieval pilot is deliberately isolated in the
new DocuElevate preprod line. Production remains pinned to the Evergreen legacy
release. Delivery is split into independently reversible slices:

1. **P0 — Authenticated document intake**
   - Accept a multipart document plus source metadata through a dedicated intake endpoint.
   - Reuse DocuElevate API Bearer tokens and OAuth sessions; optionally accept a
     separately configured shared intake secret for machine-to-machine migration.
   - Write to the existing work directory and enqueue the normal processing pipeline.
   - Make an idempotency key mandatory for automated senders so retries cannot create duplicates.
2. **P0 — Legacy document bridge**
   - Add an optional outbound destination that sends the completed document bytes and
     provenance metadata to the preprod intake endpoint.
   - Keep the bridge disabled by default and isolated from processing success: delivery
     failures are retryable and observable but never invalidate the legacy document.
   - Retrofit only this bounded sender into Evergreen after it passes preprod contract tests.
3. **P0 — Dropbox collection import**
   - Import an existing Dropbox tree recursively without deleting source files.
   - Persist a cursor/checkpoint and Dropbox revision per source object so the import is
     resumable and re-runs only changed content.
   - Route every downloaded file through the same authenticated intake/processing contract.
4. **P0 — Chunk-level vector index**
   - Split complete OCR text into overlapping token-aware chunks and store source-backed
     payloads in a private Qdrant collection.
   - Keep the existing whole-document embedding for duplicate detection; vector export is
     optional and idempotent.
   - Provide explicit backfill and health/status operations for the existing corpus.
5. **P0 — Complete lexical corpus index**
   - Reconcile every processed, non-duplicate document into Meilisearch without a
     fixed corpus-size ceiling.
   - Use bounded, resumable bulk updates on a dedicated worker and expose the
     remaining gap so exhaustive answers cannot silently claim incomplete coverage.
6. **P0 — DearConcierge retrieval contract**
   - Expose authenticated semantic search and cited full-text retrieval with DocuElevate's
     existing owner/share checks applied to every result.
   - Support OAuth browser sessions and personal Bearer tokens first; add an MCP adapter as
     a thin client over the same API rather than duplicating authorization logic.
7. **P0 — Preprod acceptance and promotion gate**
   - Prove retry/idempotency, owner isolation, Dropbox resume, vector backfill, citation
     retrieval, and end-to-end DearConcierge queries in preprod.
   - Do not change the production image or enable the Evergreen sender without a separate,
     explicit production approval.

The detailed contract, security boundaries, rollout order, and acceptance evidence are
maintained in [docs/DearConciergeKnowledgeBridge.md](docs/DearConciergeKnowledgeBridge.md).

## Release Naming

Selected delivery tracks carry codenames to mark key project moments. A planning
track is not automatically a release codename: runtime names appear only when the
actual semantic version matches an entry in `release_names.json`. Clarity,
Conductor, and Signal are currently planning-track names because their former
`0.6.x`–`0.8.x` version numbers have already shipped. For details, see
[docs/ReleaseNaming.md](docs/ReleaseNaming.md).

| Delivery Track | Codename        | Theme |
|----------|------------------|-------|
| Planning | **Clarity**      | Search, discovery, and modern UX |
| Planning | **Conductor**    | Workflows, orchestration, and integrations |
| Planning | **Signal**       | AI quality, multilingual, and “Chat with Library” foundations |
| v1.0.0   | **Summit**       | Enterprise readiness (multi-tenancy, RBAC, scaling) |
| v2.0.0   | **Horizon**      | Platform expansion and ecosystem maturity |
| v2.1.0+  | **Sentinel**     | Governance, compliance, and policy-driven automation |
| v3.0.0   | **Constellation**| Integration hub, agents, and interoperability |

## Current Product Capabilities (Today)

### Core Features ✅
- Multi-channel ingestion (web upload, IMAP email, watched folders, mobile, CLI, API)
- Multi-engine OCR + AI extraction with configurable providers
- Customizable processing pipelines and routing rules
- Full-text search and document discovery
- Multi-destination distribution (cloud providers, DMS, protocols, email)
- Admin UI for configuration (database-backed settings, encryption, setup wizard)
- [x] Tenant/Tribe document boundary foundation with canonical per-file `is_private` enforcement
- [x] Per-user onboarding creates an isolated personal Tribe and can create an initial shared Family/Team Tribe
- [ ] Tribe membership, invitations, delegated routing administration, and explicit shared-intake UI (#1146)
- Production hardening building blocks (CI/CD, security docs, deployment guides)

## Feature Landscape (Themes)

### 1) Search & Discovery
- **P0:** hybrid search (keyword + semantic), fast faceted filtering, saved searches
- **P1:** “explain results” (why a document matched), query suggestions, pinned results
- **P2:** entity search (people/companies/amounts/dates) and graph-style exploration

### 2) AI Quality & Trust
- **P0:** confidence scoring, human review/edit loop, extraction evaluation harness
- **P1:** per-document-type schemas/templates, active learning (feedback improves extraction)
- **P2:** multi-model routing (choose model by cost/latency/accuracy per step)

### 3) Workflow Automation & Orchestration
- **P0:** first-class workflow model (steps, state, retries), workflow-aware UI status
- **P1:** visual workflow builder, scheduling, webhooks, and event-driven triggers
- **P2:** agentic workflows (“autopilot” suggestions with approval gates)

### 4) Integrations & Ecosystem (Including MCP)
- **P0:** stable webhooks + outbound actions (Slack/Teams, email, DMS), bi-directional sync where supported
- **P1:** “Integration Hub” (Zapier/Make/n8n style), connector templates, secrets handling patterns
- **P2:** **MCP**: ship a DocuElevate MCP server (search, retrieve, summarize, route) + allow MCP tools as pipeline steps

### 5) Governance, Compliance, and Security
- **P0:** audit trails, tamper-evident logs, API key lifecycle/rotation, admin activity feed
- **P1:** retention policies, legal hold, PII detection + redaction, data residency controls
- **P2:** compliance packs (SOC2/GDPR/HIPAA), BYOK/KMS integration paths

### 6) Enterprise & Scale
- **P0:** multi-tenancy, RBAC, horizontal scaling reference architecture
- **P1:** SCIM provisioning, SAML/Okta/Azure AD hardening, quotas/billing at org level
- **P2:** multi-region deployment patterns and disaster recovery playbooks

## Release Plan (Extended)

This plan extends the existing milestone anchors with a clearer thematic arc and a forward-looking “beyond v2.0” horizon. The anchor labels are planning references, not promises that the automated semantic-release stream will stay numerically below them. Each milestone links to an epic issue that owns scope and sub-issues.

### Clarity (Search & UX)
- **Outcome:** users can reliably find, preview, and act on documents in seconds
- **P0:** semantic search + hybrid ranking, saved searches, fast filters, preview-first UX
- **P1:** bulk operations, query suggestions, accessibility/dark mode polish
- **Tracking:** GitHub milestone `Clarity - Enhanced Search & UI` (epic #863)

### Conductor (Workflows & Integrations)
- **Outcome:** workflows are explicit, inspectable, and automatable end-to-end
- **P0:** workflow object model + workflow-aware UI status, retries, pipeline definitions
- **P1:** workflow builder, scheduling, inbound/outbound webhooks
- **P2:** integration templates + “connector marketplace” concepts
- **Tracking:** GitHub milestone `Conductor - Workflow Automation` (epic #864)

### Signal (AI Quality + “Chat with Library” Foundations)
- **Outcome:** AI features are measurable, reviewable, and safe to trust
- **P0:** vector DB + embeddings pipeline, chat UI foundations, local AI options
- **P1:** confidence scoring and review loop, extraction evaluation harness
- **P2:** multilingual UX + localization expansion
- **Tracking:** GitHub milestone `Signal - Advanced AI & Multi-language` (epic #865)

### v1.0.0 — Summit (Enterprise Readiness)
- **Outcome:** teams can run DocuElevate with strong isolation, access control, and scale
- **P0:** multi-tenancy, RBAC, audit logging, scaling guidance
- **P1:** SSO hardening (SAML/LDAP), org-level quotas and billing hooks
- **P2:** enterprise admin experience (policies, approvals, reporting)
- **Tracking:** GitHub milestone `v1.0.0 - Enterprise Edition` (epic #866)

### v2.0.0 — Horizon (Platform Expansion)
- **Outcome:** DocuElevate becomes an extensible platform with a thriving ecosystem
- **P0:** plugin system foundations, SDK + templates, deeper integrations
- **P1:** marketplace patterns, app distribution, mobile/extension maturity
- **P2:** multi-workspace experiences (personal + org)
- **Tracking:** GitHub milestone `v2.0.0 - Platform Expansion` (epic #867)

### v2.1.0+ — Sentinel (Governance & Policy)
- **Outcome:** governance becomes a first-class layer (policy-driven automation)
- **P0:** retention + legal hold, PII detection/redaction, tamper-evident audit trails
- **P1:** BYOK/KMS integration patterns, advanced access policies, compliance reporting
- **P2:** “policy as code” for workflows + approvals (change management)
- **Tracking:** GitHub milestone `v2.1.0 - Governance & Policy (Sentinel)` (epic #868)

### v3.0.0 — Constellation (Integration Hub & Agent Platform)
- **Outcome:** DocuElevate plugs into modern automation and AI ecosystems as a first-class system of record
- **P0:** MCP server, durable event stream + production-grade webhooks
- **P1:** connector templates + curated catalog, agent-friendly permissioning and auditing
- **P2:** bring-your-own-agent patterns (sandboxing, scoped credentials)
- **Tracking:** GitHub milestone `v3.0.0 - Integration Hub & Agent Platform (Constellation)` (epic #869)

## Research Bets (Optional / Experimental)

These are longer-horizon bets that should only be productized if they prove real user value.

- Knowledge graph over extracted entities (contracts ↔ vendors ↔ invoices)
- Auto-generated “case files” (collections) from intent (“tax 2025”, “project alpha”)
- Privacy-preserving learning (federated patterns) to improve extraction quality
- Document provenance (signing, attestations) and tamper detection

## Community & Ecosystem

### Developer Experience
- [ ] Plugin system for custom processors
- [ ] Marketplace for extensions
- [ ] SDK for multiple languages (Python, JavaScript, Go)
- [ ] Template library for common workflows
- [ ] Video tutorials and courses

### Documentation
- [x] User guide
- [x] API documentation
- [x] Deployment guide
- [ ] Architecture deep-dive
- [ ] Contributing guide enhancements
- [ ] Video walkthroughs
- [ ] Internationalization (i18n) of docs

### Community Building
- [ ] Regular community calls
- [ ] Bug bounty program
- [ ] Ambassador program
- [ ] Annual conference/meetup
- [ ] Certification program

## Technology Debt

### Refactoring Needed
- [x] Migrate from PyPDF2 to pypdf (modern fork) - ✅ Completed 2026-02-12
- [ ] Standardize error handling across modules
- [ ] Consolidate configuration management
- [ ] Optimize database queries
- [ ] Reduce code duplication in storage providers

### Performance Optimization
- [ ] Profile and optimize hot paths
- [ ] Implement lazy loading for UI
- [ ] Add CDN for static assets
- [ ] Optimize Docker image size
- [ ] Database indexing strategy

## Deprecation Notice

### Planned Deprecations
- None currently planned

### Migration Guides
- Will be provided for any breaking changes

## How to Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines. Roadmap items are open for discussion and contributions!

### Priority Labels
- 🔴 Critical - Security, data loss, or major bugs
- 🟠 High - Important features or significant improvements
- 🟡 Medium - Nice-to-have features or minor improvements
- 🟢 Low - Future considerations or research items

## Feedback & Requests

- **GitHub Issues:** Feature requests and bug reports
- **GitHub Discussions:** General questions and ideas
- **Email:** [Maintainer contact from repository]

---

*This roadmap is a living document and may change based on community feedback, technical constraints, and strategic priorities.*
