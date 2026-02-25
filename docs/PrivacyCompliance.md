# Privacy & GDPR Compliance Guide

This document details DocuElevate's privacy and data-protection compliance strategy for all supported markets.
It is intended as an internal reference for developers, legal reviewers, and compliance officers.

## Supported Markets

| Market | Primary Law(s) | Status |
|---|---|---|
| European Union (EU) / EEA | GDPR (Regulation 2016/679), ePrivacy Directive | ✅ Implemented |
| Germany | GDPR + BDSG (Federal Data Protection Act) | ✅ Implemented |
| United Kingdom | UK GDPR + Data Protection Act 2018 | ✅ Implemented |
| Switzerland | nFADP (revised Federal Act on Data Protection, in force Sep 2023) | ✅ Implemented |
| Ukraine | Law of Ukraine "On Personal Data Protection" No. 2297-VI | ✅ Implemented |
| United States | CCPA/CPRA (California), VCDPA, CPA, CTDPA, UCPA (other states) | ✅ Implemented |
| Canada | PIPEDA + Québec Law 25 (Bill 64) | ✅ Implemented |
| Latin America | Brazil LGPD, Argentina PDPA, Mexico LFPDPPP, Colombia Ley 1581 | ✅ Implemented |
| Asia-Pacific & Japan | Japan APPI, Australia Privacy Act 1988, South Korea PIPA, Singapore PDPA, India DPDP Act | ✅ Implemented |

> **Out of scope:** Countries subject to German export control embargoes, China, and Russia are explicitly excluded.

---

## Architecture & Data Minimization

DocuElevate is designed with privacy-by-design and data-minimization principles as core tenets:

1. **No advertising or tracking infrastructure.** The application loads no analytics scripts, tracking pixels,
   advertising networks, or third-party data-collection tools. CDN-hosted assets (Alpine.js, Tailwind CSS,
   Font Awesome) are loaded from `cdn.jsdelivr.net` and `cdnjs.cloudflare.com` for functionality only.

2. **Essential cookies only.** A single server-side session cookie is set. This cookie is strictly necessary
   for authentication and is exempt from prior-consent requirements under GDPR Art. 5(3) ePrivacy Directive
   and equivalent national laws. A dismissable cookie notice banner informs users of this on first visit.

3. **Purpose limitation.** Documents uploaded by users are processed only for the purposes they initiate
   (OCR, metadata extraction, cloud storage). Document content is not used for AI model training or secondary
   analytics purposes.

4. **Credential encryption.** All OAuth tokens and cloud storage credentials are stored encrypted at rest.

5. **Audit logs.** Logs contain action type, timestamp, and user identifier only — no document content.
   Default retention: 90 days.

---

## Cookie Strategy

### Cookie Classification

| Cookie / Storage | Classification | Legal Basis | Consent Required? |
|---|---|---|---|
| `session` (HTTP Cookie) | Strictly Necessary | Legitimate Interest / Contract Performance | No (ePrivacy Art. 5(3) exemption) |
| `cookieNoticeDismissed` (localStorage) | Strictly Necessary (UX preference) | Legitimate Interest | No |

### Cookie Notice Banner

A dismissable banner is displayed on every page on first visit (until dismissed via localStorage).
It informs users that only essential session cookies are used and links to the full Cookie Policy (`/cookies`)
and Privacy Notice (`/privacy`). Dismissal is stored in `localStorage` under the key `cookieNoticeDismissed`.

**Implementation:** `frontend/templates/base.html` — inline JavaScript in the `<body>` section.

---

## International Data Transfers

When DocuElevate is configured to use third-party AI services (e.g., OpenAI, Azure Document Intelligence)
or cloud storage providers hosted outside the EEA, data transfers must be governed by appropriate safeguards:

| Transfer Mechanism | Applicable To |
|---|---|
| **Standard Contractual Clauses (SCCs)** — EU Commission Decision 2021/914/EU | Transfers to US processors (OpenAI, Microsoft Azure, AWS, Google) |
| **UK International Data Transfer Agreements (IDTAs)** | Transfers from UK to non-adequate third countries |
| **Adequacy Decision** | UK ↔ EU (EU Commission decision C(2021) 4800), Switzerland ↔ EU, Japan ↔ EU (partial), Canada (commercial) |
| **Swiss SCCs / nFADP Art. 16** | Transfers from Switzerland to non-adequate third countries |

> **Action for deployers:** When configuring DocuElevate with US-based AI providers (OpenAI, Azure, AWS),
> ensure you have executed or accepted the provider's Data Processing Agreement (DPA) which incorporates SCCs.
> Links to major provider DPAs:
> - OpenAI: https://openai.com/policies/data-processing-addendum
> - Microsoft Azure: https://aka.ms/DPA
> - Google Cloud: https://cloud.google.com/terms/data-processing-addendum
> - AWS: https://aws.amazon.com/agreement/

---

## Data Subject Rights — Handling Process

All rights requests must be submitted to **docuelevate@christian-louis.de**.

| Right | GDPR | CCPA/CPRA | PIPEDA | LGPD | APPI |
|---|---|---|---|---|---|
| Access / Know | Art. 15 | ✅ | ✅ | Art. 18 | ✅ |
| Rectification / Correction | Art. 16 | ✅ | ✅ | Art. 18 | ✅ |
| Erasure / Deletion | Art. 17 | ✅ | Limited | Art. 18 | ✅ |
| Data Portability | Art. 20 | — | — | Art. 18 | — |
| Object / Opt-out of processing | Art. 21 | ✅ (sale/sharing) | Withdraw consent | — | ✅ |
| Restriction of Processing | Art. 18 | — | — | — | — |
| Complaint to DPA | Art. 77 | CPPA / State AG | OPC (Canada) | ANPD (Brazil) | PPC (Japan) |

### Response Timelines

| Jurisdiction | Standard Response Time | Extension |
|---|---|---|
| EU / EEA / UK / Switzerland | 1 calendar month | +2 months for complex requests |
| US (CCPA/CPRA) | 45 days | +45 days when reasonably necessary |
| Canada (PIPEDA) | 30 days | Extensions allowed with notice |
| Brazil (LGPD) | 15 days | — |
| Japan (APPI) | Without delay (reasonable period) | — |
| Australia | 30 days | — |

---

## Market-Specific Notes

### Germany (GDPR + BDSG)
- BDSG supplements GDPR with stricter rules on employee data, video surveillance, and credit score processing.
- An **Impressum** (legal notice per §5 TMG) is provided at `/imprint`.
- Online Dispute Resolution platform link is included in the Impressum per EU ODR Regulation.

### United Kingdom (UK GDPR + DPA 2018)
- Post-Brexit: UK GDPR mirrors EU GDPR with UK-specific adaptations via DPA 2018.
- Data transfers from the UK use IDTAs (UK equivalent of SCCs).
- ICO is the supervisory authority. Complaint rights are disclosed in the Privacy Notice.

### Switzerland (nFADP)
- Swiss revised Federal Act on Data Protection (nFADP) entered into force 1 September 2023.
- Substantially equivalent to GDPR. Swiss residents' rights mirror GDPR rights.
- FDPIC (Federal Data Protection and Information Commissioner) is the supervisory authority.

### United States (CCPA/CPRA and state laws)
- DocuElevate does **not** sell or share personal information for cross-context behavioural advertising.
- A "Do Not Sell or Share My Personal Information" link is therefore not required, but the Privacy Notice
  explicitly confirms this position.
- Sensitive personal information is not used beyond what is strictly necessary to provide the service.
- Privacy Notice includes the required CCPA/CPRA disclosures (categories collected, purposes, rights).

### Canada (PIPEDA + Québec Law 25)
- PIPEDA applies to commercial activities involving personal information in all Canadian provinces except
  those with substantially similar provincial legislation (Québec, Alberta, BC — which have their own).
- Québec Law 25 (Bill 64, in force Sep 2023) adds GDPR-like rights including data portability and
  de-indexation. Privacy impact assessments (PIAs) are required for high-risk processing.
- A designated Privacy Officer is available at the contact email.

### Brazil (LGPD)
- LGPD applies to any processing of personal data of individuals located in Brazil, regardless of where
  the controller is established.
- Legal bases used: performance of contract (Art. 7 VI) and legitimate interest (Art. 7 IX).
- ANPD (Autoridade Nacional de Proteção de Dados) is the supervisory authority.

### Japan (APPI)
- APPI amendments effective April 2022 introduced data portability, the right to opt out of third-party
  provision, and stricter requirements for sensitive personal information.
- Third-party disclosures require prior opt-in consent (with limited exceptions).
- The Personal Information Protection Commission (PPC) is the supervisory authority.

### Australia (Privacy Act 1988 + APPs)
- The Australian Privacy Principles (APPs) govern the handling of personal information.
- The Privacy Act review (2023) recommended GDPR-like reforms; further legislative changes are expected.
- OAIC (Office of the Australian Information Commissioner) is the supervisory authority.

---

## Periodic Review Schedule

| Activity | Frequency | Owner |
|---|---|---|
| Privacy Notice review | Annually or on material change | Legal / Compliance |
| Cookie audit | Annually | Engineering |
| Data transfer safeguard review (SCCs, IDTAs) | Annually or on legal change | Legal / Compliance |
| Dependency CVE scan (`safety check`) | On every PR | Engineering (CI) |
| Security audit | Annually | Security |
| DPA register review | Annually | Legal / Compliance |

---

## Related Documents

- [`frontend/templates/privacy.html`](../frontend/templates/privacy.html) — User-facing Privacy Notice
- [`frontend/templates/cookies.html`](../frontend/templates/cookies.html) — User-facing Cookie Policy
- [`frontend/templates/terms.html`](../frontend/templates/terms.html) — Terms of Service
- [`frontend/templates/imprint.html`](../frontend/templates/imprint.html) — Impressum / Legal Notice
- [`frontend/templates/base.html`](../frontend/templates/base.html) — Cookie notice banner implementation
- [`SECURITY_AUDIT.md`](../SECURITY_AUDIT.md) — Security audit findings and mitigations
- [`docs/AuthenticationSetup.md`](AuthenticationSetup.md) — OAuth and authentication configuration
