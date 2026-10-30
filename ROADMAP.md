# DocuElevate Roadmap

**Last updated:** 2026-10-30

## Vision and planning rules

DocuElevate helps people and teams ingest, understand, find, and safely route documents. This roadmap describes product outcomes and sequencing; GitHub issues and milestones remain authoritative for scoped work and current status. A merged change or available code is evidence of a foundation, not proof that a complete user journey is accepted. Track implementation, acceptance, and live operational verification separately.

The project ships through automated semantic versioning. The verified repository version for this review is **0.189.1**; it does not indicate completion of any named planning track or predict the next release. Dates below are the existing GitHub milestone targets, retained as planning targets rather than delivery promises.

## Cross-cutting security and recovery gate

Credential exposure, security/privacy gaps, and recovery risks are always active gates, not work deferred until after product features. Protect and rotate affected credentials ([#1162](https://github.com/christianlouis/DocuElevate/issues/1162)); maintain tenant/privacy boundaries; address single-host loss and backup integrity ([#902](https://github.com/christianlouis/DocuElevate/issues/902), [#1190](https://github.com/christianlouis/DocuElevate/issues/1190)–[#1193](https://github.com/christianlouis/DocuElevate/issues/1193)); and require the separate explicit production approval ([#1201](https://github.com/christianlouis/DocuElevate/issues/1201)). Prioritize product work below after or alongside these gates, based on impact and evidence. Do not infer current live deployment state from this roadmap.

## Delivery sequence

### 1. Useful fresh installation

Make a new installation usable from setup through the first successfully processed and retrievable document ([#1134](https://github.com/christianlouis/DocuElevate/issues/1134), [#1151](https://github.com/christianlouis/DocuElevate/issues/1151)).

**Acceptance:** a clean install can configure, test, skip, and resume optional integrations; configure AI or choose no AI; ingest and process a first document; create a second user with verified isolation; recover from interrupted setup; and complete the journey in browser E2E. Record a repeatable result against a supported deployment profile.

### 2. Complete the Family/Tribe shared-intake journey

Tenant/Tribe fields, personal Tribes, quarantine, scoped SQL/Qdrant access, and optional shared Family/Team onboarding exist ([#1155](https://github.com/christianlouis/DocuElevate/pull/1155), [#1168](https://github.com/christianlouis/DocuElevate/pull/1168)). Canonical `is_private` enforcement, owner override, privacy controls for filename/OCR/metadata, preview and retroactive application, link revocation, and index reconciliation are also implemented ([#1147](https://github.com/christianlouis/DocuElevate/issues/1147), [#1152](https://github.com/christianlouis/DocuElevate/pull/1152), [#1155](https://github.com/christianlouis/DocuElevate/pull/1155)). These foundations do not yet establish a complete shared workflow.

Complete invitations and consent, membership, shared-intake administration, recipient profiles and explainable classification, authorized per-member destinations, delegated routing, review and historical-document handling, and multi-identity browser acceptance ([#1142](https://github.com/christianlouis/DocuElevate/issues/1142)–[#1147](https://github.com/christianlouis/DocuElevate/issues/1147)). Broader natural-language matching remains a product goal; do not claim universal matching quality without evaluation.

**Acceptance:** an owner can invite members, collect consent, ingest or review a shared document, explain its proposed recipient, route it only to authorized destinations, correct/review the result, and revoke access. Tests and browser E2E cover personal/shared boundaries, privacy choices, existing documents, and multiple identities; access revocation is reflected in retrieval/index behavior.

### 3. Measurable retrieval, chat, and AI quality

Search, hybrid scoring, ranking explanations, metadata fallback, semantic and lexical retrieval, chat/research APIs, citations, coverage reporting, and an extraction evaluation harness already exist ([#477](https://github.com/christianlouis/DocuElevate/issues/477), [#478](https://github.com/christianlouis/DocuElevate/issues/478), [#480](https://github.com/christianlouis/DocuElevate/issues/480), [#880](https://github.com/christianlouis/DocuElevate/issues/880)). Saved searches, preview, and bulk operations are tracked as delivered in the Clarity epic ([#870](https://github.com/christianlouis/DocuElevate/issues/870), [#872](https://github.com/christianlouis/DocuElevate/issues/872), [#873](https://github.com/christianlouis/DocuElevate/issues/873)). Local AI support also exists through LiteLLM/Ollama for extraction; broader private local embedding and query flows remain ([#479](https://github.com/christianlouis/DocuElevate/issues/479)). These capabilities still need representative acceptance and quality evidence.

Complete relevance tuning and user-facing explanations/configuration ([#871](https://github.com/christianlouis/DocuElevate/issues/871)); measure cited chat outcomes, latency, and corpus coverage ([#478](https://github.com/christianlouis/DocuElevate/issues/478)); and extend extraction evaluation with representative fixtures, CI quality reports, calibration, and regression criteria ([#880](https://github.com/christianlouis/DocuElevate/issues/880)). Add per-field confidence ([#878](https://github.com/christianlouis/DocuElevate/issues/878)) and extraction review ([#879](https://github.com/christianlouis/DocuElevate/issues/879)), then feedback workflows where issue scope requires. Stabilize the versioned tenant-scoped consumer contract ([#1082](https://github.com/christianlouis/DocuElevate/issues/1082)). Continue multilingual and large-document work ([#198](https://github.com/christianlouis/DocuElevate/issues/198), [#881](https://github.com/christianlouis/DocuElevate/issues/881), [#1189](https://github.com/christianlouis/DocuElevate/issues/1189), [#1066](https://github.com/christianlouis/DocuElevate/issues/1066), [#1090](https://github.com/christianlouis/DocuElevate/issues/1090), [#1091](https://github.com/christianlouis/DocuElevate/issues/1091)).

**Acceptance:** published, reproducible retrieval and extraction evaluation sets report baseline and changed results; regressions have agreed thresholds; chat answers cite source documents and disclose incomplete coverage; latency and relevance targets are recorded; representative users can inspect why results matched and review/correct extraction. Local private embeddings/query acceptance is separately documented before claiming end-to-end local AI.

### 4. Operational reliability and security gates

Operational foundations include executable backup/restore work and monitor retry/transient database recovery ([#1062](https://github.com/christianlouis/DocuElevate/issues/1062), [#1102](https://github.com/christianlouis/DocuElevate/issues/1102), [#1276](https://github.com/christianlouis/DocuElevate/pull/1276)), bounded OCR/IMAP resources and telemetry privacy ([#1280](https://github.com/christianlouis/DocuElevate/pull/1280)), plus shared archive and credential improvements. Follow-up work remains in host-loss resilience ([#902](https://github.com/christianlouis/DocuElevate/issues/902)), atomic credential state ([#1190](https://github.com/christianlouis/DocuElevate/issues/1190)), archive integrity and partial-archive accounting ([#1191](https://github.com/christianlouis/DocuElevate/issues/1191), [#1192](https://github.com/christianlouis/DocuElevate/issues/1192)), initial backup sizing ([#1193](https://github.com/christianlouis/DocuElevate/issues/1193)), and monitor recovery ([#1121](https://github.com/christianlouis/DocuElevate/issues/1121)). Credential rotation ([#1162](https://github.com/christianlouis/DocuElevate/issues/1162)) and explicit production approval ([#1201](https://github.com/christianlouis/DocuElevate/issues/1201)) remain tracked. Verify current evidence before closing any item; do not repeat already-remediated monitor defects as absent.

**Acceptance:** documented restore and host-loss exercises meet recorded recovery objectives; backup integrity and capacity checks pass; credential rotation and recovery are evidenced; telemetry and diagnostic output meet privacy constraints; deployment promotion has a named, explicit approval and a read-back of the selected artifact/configuration. This roadmap makes no claim about the currently deployed production image or configuration.

### 5. Workflow authoring and integration

Existing processing pipelines and service polling are not a general workflow authoring or scheduling product. Deliver editable, versioned workflows with execution status, retry/recovery, recurring and delayed triggers, and reusable starter templates ([#875](https://github.com/christianlouis/DocuElevate/issues/875)–[#877](https://github.com/christianlouis/DocuElevate/issues/877), [#885](https://github.com/christianlouis/DocuElevate/issues/885)). Complete bidirectional sync where supported ([#481](https://github.com/christianlouis/DocuElevate/issues/481)), and add a stable event/webhook contract ([#894](https://github.com/christianlouis/DocuElevate/issues/894)) with delivery observability and retries.

**Acceptance:** an administrator can author, validate, version, publish, inspect, roll back, and safely retry a workflow; scheduled and event-triggered runs have documented idempotency and failure behavior; a starter template works end-to-end; connector sync can reconcile changes without silent loss or duplicate actions.

### 6. Enterprise, governance, and ecosystem

Build on proven tenant contracts: organization/team administration ([#199](https://github.com/christianlouis/DocuElevate/issues/199)), RBAC ([#200](https://github.com/christianlouis/DocuElevate/issues/200)), scale ([#201](https://github.com/christianlouis/DocuElevate/issues/201)), SLA ([#211](https://github.com/christianlouis/DocuElevate/issues/211)), admin activity feed ([#882](https://github.com/christianlouis/DocuElevate/issues/882)), SSO ([#883](https://github.com/christianlouis/DocuElevate/issues/883)), and organization quotas ([#884](https://github.com/christianlouis/DocuElevate/issues/884)). Basic audit capabilities, Stripe integration, user quotas, and Tribe boundaries are not equivalent to the full enterprise outcomes. Governance follows with retention ([#218](https://github.com/christianlouis/DocuElevate/issues/218)), legal hold ([#888](https://github.com/christianlouis/DocuElevate/issues/888)), PII controls ([#889](https://github.com/christianlouis/DocuElevate/issues/889)), tamper-evident audit ([#890](https://github.com/christianlouis/DocuElevate/issues/890)), KMS ([#891](https://github.com/christianlouis/DocuElevate/issues/891)), and policy management ([#892](https://github.com/christianlouis/DocuElevate/issues/892)).

Per-user Notion and Evernote destinations are implemented; live setup and delivery acceptance with real provider accounts remains to be recorded. Read-only MCP stdio tools for document search and retrieval are delivered in contract v1.0 ([#1281](https://github.com/christianlouis/DocuElevate/pull/1281); [docs/MCP.md](docs/MCP.md)). Broader MCP scope remains: read-only API token scopes, summaries/actions/shared HTTP interoperability ([#893](https://github.com/christianlouis/DocuElevate/issues/893)). Durable signed webhooks ([#894](https://github.com/christianlouis/DocuElevate/issues/894)) and audited action permissions ([#896](https://github.com/christianlouis/DocuElevate/issues/896)) belong to the later interoperability layer. Plugin infrastructure, SDK, marketplace, and desktop application remain future ecosystem work ([#220](https://github.com/christianlouis/DocuElevate/issues/220), [#886](https://github.com/christianlouis/DocuElevate/issues/886), [#887](https://github.com/christianlouis/DocuElevate/issues/887), [#214](https://github.com/christianlouis/DocuElevate/issues/214)).

**Acceptance:** enterprise isolation and permissions have cross-tenant tests and operational scale evidence; governance actions are auditable and policy enforcement is tested; integrations document supported scopes and recovery; MCP and agent actions have least-privilege authorization, revocation, and audit evidence. Do not equate basic audit/quotas or a read-only adapter with these broader outcomes.

### Longer-horizon product ambitions

These themes remain part of the product vision beyond near-term acceptance work. Sequence them through GitHub issues as needs and evidence develop.

- **Search:** query suggestions, pinned results, entity search for people/companies/amounts/dates, and graph-style exploration.
- **AI quality:** per-document-type schemas/templates, feedback-driven active learning, and multi-model routing by cost, latency, or accuracy.
- **Enterprise and scale:** SCIM provisioning, deeper SAML/Okta/Azure AD support, organization billing, multi-region deployment, and disaster-recovery playbooks.
- **Governance:** data residency controls, compliance packs (SOC 2/GDPR/HIPAA), and BYOK/KMS integration paths.
- **Automation:** approval-gated agentic workflows, integration hub patterns, connector templates, and MCP tools as workflow steps.

## Planning tracks

| Track | GitHub milestone | Target date | Product emphasis |
|---|---|---:|---|
| Clarity | `Clarity - Enhanced Search & UI` ([#863](https://github.com/christianlouis/DocuElevate/issues/863)) | 2026-10-31 | Search relevance, discovery UX, and acceptance of delivered foundations |
| Conductor | `Conductor - Workflow Automation` ([#864](https://github.com/christianlouis/DocuElevate/issues/864)) | 2027-01-31 | Workflow authoring, scheduling, and integrations |
| Signal | `Signal - Advanced AI & Multi-language` ([#865](https://github.com/christianlouis/DocuElevate/issues/865)) | 2027-04-30 | Measurable retrieval, extraction quality, review, and localization |
| Summit | `v1.0.0 - Enterprise Edition` ([#866](https://github.com/christianlouis/DocuElevate/issues/866)) | 2027-09-30 | Organization administration, access control, scale |
| Horizon | `v2.0.0 - Platform Expansion` ([#867](https://github.com/christianlouis/DocuElevate/issues/867)) | 2028-03-31 | Plugins, SDK, connector and surface maturity |
| Sentinel | `v2.1.0 - Governance & Policy (Sentinel)` ([#868](https://github.com/christianlouis/DocuElevate/issues/868)) | 2028-09-30 | Retention, legal hold, privacy, policy and audit |
| Constellation | `v3.0.0 - Integration Hub & Agent Platform (Constellation)` ([#869](https://github.com/christianlouis/DocuElevate/issues/869)) | 2029-03-31 | Interoperability, event delivery, governed agent actions |

Clarity's target is 2026-10-31; the open [#871](https://github.com/christianlouis/DocuElevate/issues/871) acceptance work means the date itself is not evidence of completion. Track names and future version anchors are planning labels, not guaranteed semantic-release versions. See [MILESTONES.md](MILESTONES.md) for recorded dates and status context.

## Research bets

Evaluate knowledge graphs, intent-based case files, privacy-preserving learning, and document provenance only when a measurable user benefit and safe operating model are established.

## Release Naming

Planning tracks are distinct from runtime release codenames. A runtime name appears only when the actual semantic version matches an entry in `release_names.json`. Clarity, Conductor, and Signal remain planning-track names because their former `0.6.x`–`0.8.x` versions have already shipped. See [docs/ReleaseNaming.md](docs/ReleaseNaming.md).

## Community & Ecosystem

### Developer experience

- Plugin system for custom processors; marketplace for extensions; SDKs for Python, JavaScript, and Go; workflow template library; video tutorials and courses.

### Documentation and community

- Maintain user guide, API documentation, and deployment guide; add architecture deep-dive, contributor improvements, video walkthroughs, and translated documentation.
- Consider community calls, a bug bounty, an ambassador program, annual events, and certification as the project and support model mature.

## Technology Debt

Track through issues: standardize error handling, consolidate configuration management, optimize database queries, reduce storage-provider duplication, profile hot paths, add UI lazy loading where useful, evaluate CDN/static asset delivery, reduce image size, and maintain a database indexing strategy. PyPDF2-to-pypdf migration is complete (2026-02-12).

## Deprecation Notice

No specific deprecations are currently planned. Breaking changes require migration guidance and a documented compatibility window; where applicable, preserve previous endpoint behavior for at least two minor milestones.

## How to Contribute

See [CONTRIBUTING.md](CONTRIBUTING.md). Propose roadmap work through GitHub issues with user need, scope, and acceptance evidence; keep implementation tasks and status in GitHub.

## Feedback & Requests

Use [GitHub Issues](https://github.com/christianlouis/DocuElevate/issues) for feature requests and bugs, and [GitHub Discussions](https://github.com/christianlouis/DocuElevate/discussions) for questions and broader product ideas.

---

*This roadmap is a living document and may change with community feedback, technical constraints, and product evidence.*
