# DocuElevate as a hosted SaaS product

Status: product proposal and MVP boundary

Evidence baseline: branch `user-config-hardening-20261101` / PR #1294, reviewed 2026-11-01

## Executive decision

DocuElevate is commercially plausible as a hosted document-intake and processing service, but the current repository is not yet a complete multi-customer SaaS product. The strongest near-term offer is a focused managed service:

> Connect a customer's personal or team sources, normalize and enrich documents in a centrally operated processing pipeline, and deliver the result into the customer's chosen destinations.

The hosted product should initially sell convenience, reliability, and secure connector management. It should not promise enterprise organization administration, arbitrary workflow automation, or compliance certifications until the existing enterprise work is delivered and independently accepted.

This document is intentionally a product boundary, not a new feature backlog. Existing issues own the implementation work; no duplicate issue is proposed here.

## What already exists

| SaaS concern | Evidence in the current tree | Product interpretation |
| --- | --- | --- |
| Document processing | `README.md`; `app/tasks/process_document.py` | A coherent ingestion/OCR/metadata/delivery engine exists. |
| Personal isolation | `app/models.py` (`Tenant`, `Tribe`, `TribeMembership`, `FileRecord`); `app/utils/user_scope.py` | Tenant/Tribe and owner/privacy checks are real foundations, but need end-to-end acceptance across every index, task, and API. |
| Self-registration/onboarding | `app/views/onboarding.py`; `docs/BillingSetup.md`; `UserProfile` onboarding fields | A user journey exists and is resumable, but fresh-install completion still depends on the open setup/onboarding work. |
| Personal sources and destinations | `UserIntegration`; `app/views/integrations.py`; `docs/DropboxSetup.md`; `docs/StorageArchitecture.md` | The personal-connector model is suitable for SaaS and supports encrypted per-user credentials. |
| OAuth connection model | Dropbox, Google Drive, OneDrive, and shared integration routes/docs | The basic pattern exists; provider parity and a single folder-picker/reconnect contract remain incomplete. |
| API and automation | REST/GraphQL docs, API tokens, MCP adapter | A hosted API surface exists, but the retrieval contract and tenant-filtered indexing still need the versioned contract in #1082. |
| Billing primitives | `SubscriptionPlan`, `UserProfile.subscription_tier`, Stripe routes/docs | Stripe checkout and plan limits exist at user level; this is not yet organization-level usage metering or a durable SaaS entitlement system. |
| Operations | Docker/Helm, Celery, Redis, deployment and Sentry docs | A deployable application exists; a provider-operated service still needs explicit SLOs, quotas, release channels, support boundaries, and recovery evidence. |

## Product boundary for the first hosted offer

### Included

- A hosted web application with browser upload and a personal/team workspace.
- Centrally operated OCR, metadata extraction, indexing, and delivery workers.
- User-owned sources and destinations, including OAuth where the provider supports it.
- Encrypted storage of user grants and connector settings; deployment credentials remain operator-managed.
- A small number of plans with explicit document, page/token, source, destination, retention, and API limits.
- Export and deletion controls, connection revocation, processing status, and a supportable audit trail.
- A documented API for upload, status, search, retrieval, and delivery results.

### Deliberately excluded from the first hosted MVP

- Customer-managed Kubernetes or arbitrary deployment topologies.
- Customer-visible raw provider secrets or shared credentials.
- Cross-customer search, shared global corpora, or admin access to private documents.
- Full enterprise organization lifecycle, SCIM, SAML/LDAP, and advanced delegated administration.
- Compliance certification claims (SOC 2, HIPAA, etc.) before the controls and evidence exist.
- Guaranteed AI accuracy; extracted metadata remains reviewable output, not a factual warranty.

## Customer journey

1. Choose a plan and create an account through email/OIDC.
2. Create a personal workspace, or join an explicitly invited team/Tribe.
3. Connect one source and one destination with a provider OAuth flow; client secrets are never requested from the end user.
4. Select folders through a provider-aware picker and run a non-destructive connection test.
5. Upload a neutral sample document and see each processing stage and delivery result.
6. Add more sources/destinations, API tokens, or an approved team member within the plan limits.
7. Manage billing, revoke connections, export data, or delete the account without operator intervention.

The connection flow must distinguish three states: not connected, connected and healthy, and authorization expired/revoked. A saved connector must never be presented as healthy merely because configuration fields exist.

## Hosted service architecture contract

The hosted service should expose a stable control plane and a centrally operated data plane:

- **Control plane:** identity, workspace/Tribe membership, plans, quotas, connector metadata, encrypted grants, API tokens, audit events, and user-visible status.
- **Data plane:** upload intake, malware/file validation, OCR, extraction, normalization, indexing, routing, and delivery workers.
- **Boundary:** every request, queued task, search/index record, vector payload, notification, export, and destination lookup carries the effective tenant/workspace scope. Workers must re-check authorization at execution time because access, privacy, and connector state can change after enqueueing.
- **Personal destinations:** delivery uses the resolved user's encrypted integration, not a global environment credential or the shared source's credential.
- **Operations:** plans and release channels are service-level concerns; connector configuration is customer-level concern. A provider release must not silently change customer routing or delete source data.

## Monetizable MVP packages

The exact currency and price should be validated commercially; the product contract can be fixed independently.

| Package | Intended buyer | Entitlement shape |
| --- | --- | --- |
| Personal | One person | One workspace, bounded monthly pages/documents, one or two destinations, web upload, basic API, standard retention. |
| Team | Small household or team | Multiple invited members, shared Tribe intake, per-member destinations, higher quotas, delivery history, priority support. |
| Business | Operational teams | Organization-level quotas, audit export, stronger retention controls, SSO/RBAC path, higher API limits, defined SLO and support response. |

Usage should be metered in customer-understandable units (processed pages/documents, AI-token class, storage, and connector count). Hard limits must fail before expensive work starts where possible; overage, if offered, must be explicit and bounded.

## MVP acceptance criteria

The hosted MVP is marketable only when all of the following are demonstrated in a disposable environment and a production-like canary:

1. Two independent tenants and two Tribes in one deployment cannot see or influence one another through web UI, REST, GraphQL, search, vector retrieval, downloads, notifications, exports, or background tasks.
2. A new customer can register, create their personal workspace, connect a source and destination, and process a first sample without editing runtime environment variables or restarting API/workers.
3. OAuth-backed connectors store only encrypted renewable user grants plus non-secret folder/provider identifiers; expired or revoked grants produce an actionable reconnect state.
4. A customer can see processing stage, retry state, delivery result, and failure reason without seeing another customer's metadata or counts.
5. Personal delivery uses the authenticated owner's destination and honors revocation/privacy changes before a queued delivery executes.
6. Plan limits cover at least storage, processed pages/documents, sources, destinations, API rate, and retention; enforcement and usage reporting are tenant-scoped.
7. Account export, connector revocation, and account deletion have documented behavior, including queued work and retained backups.
8. Releases are versioned and rollbackable, with an operator runbook for backup/restore, worker drain, connector outages, and data-processing incidents.
9. The public product copy states the supported providers, data regions, retention, subprocessors, support channel, and the limits of AI-generated metadata.
10. Automated isolation tests and browser E2E cover the happy path plus at least one recovery path for each external dependency class.

## Roadmap alignment and non-duplication

This proposal groups existing work into a shippable hosted-product sequence. It does not replace or duplicate those issues:

| Product outcome | Existing owner |
| --- | --- |
| Tenant/org and complete scope propagation | [#199](https://github.com/christianlouis/DocuElevate/issues/199), [#866](https://github.com/christianlouis/DocuElevate/issues/866) |
| Fresh-install and end-user onboarding | [#1151](https://github.com/christianlouis/DocuElevate/issues/1151), [#1134](https://github.com/christianlouis/DocuElevate/issues/1134) |
| Team/Tribe roles, invitations, and delegated routing | [#1146](https://github.com/christianlouis/DocuElevate/issues/1146), [#1142](https://github.com/christianlouis/DocuElevate/issues/1142) |
| Provider-neutral OAuth folder picker and reconnect | [#1040](https://github.com/christianlouis/DocuElevate/issues/1040) |
| Organization quotas and usage/billing hooks | [#884](https://github.com/christianlouis/DocuElevate/issues/884) |
| Tenant-scoped retrieval/API contract | [#1082](https://github.com/christianlouis/DocuElevate/issues/1082) |
| Audit trail and activity feed | [#882](https://github.com/christianlouis/DocuElevate/issues/882) |
| Enterprise SSO | [#883](https://github.com/christianlouis/DocuElevate/issues/883) |
| Durable eventing and webhook guarantees | [#894](https://github.com/christianlouis/DocuElevate/issues/894) |

Recommended sequencing is: complete the fresh-install/customer journey and isolation proof; then unify OAuth connector UX and usage metering; then add team administration, audit/export, and enterprise SSO; finally add durable eventing and broader platform integrations. The existing roadmap's Summit/Enterprise and Conductor milestones remain the correct homes for this work.

## Release and operating separation

- **Open-source/self-hosted release:** installation, configuration, upgrade, backup, and operator responsibilities are documented for the repository.
- **Hosted SaaS release:** provider-owned deployment, data region, quotas, SLOs, support, incident communication, retention, and pricing are published per service plan.
- **Feature flags:** hosted-only capabilities must not be implied by the self-hosted README. A capability is “available” only when its acceptance evidence exists for the relevant release channel.
- **Pricing changes:** never infer entitlement from a UI label alone; the service must use a versioned plan/entitlement contract and an auditable usage record.

## Decision

Proceed with a hosted Personal/Team MVP built on the existing personal-integration and tenant/Tribe foundations. Treat organization-grade isolation, quotas, onboarding, OAuth parity, retrieval contracts, and auditability as release gates, not marketing copy. Keep the current PR #1294 focused on personal destination safety; this document is a separate product boundary and roadmap-alignment PR.
