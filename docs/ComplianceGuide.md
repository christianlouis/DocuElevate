# Compliance Templates Guide

DocuElevate includes pre-built compliance templates for **GDPR**, **HIPAA**, and **SOC 2** that help you configure your instance to meet regulatory requirements. This guide covers how to use the compliance dashboard, apply templates, and monitor your compliance status.

## Overview

The compliance templates feature provides:

- **Pre-built configurations** for GDPR, HIPAA, and SOC 2
- **One-click apply** to configure all required settings at once
- **Compliance status dashboard** to monitor your regulatory posture
- **Individual check results** showing which settings are compliant and which need attention

## Accessing the Dashboard

The compliance dashboard is available to **admin users only**.

1. Log in as an administrator
2. Click **Admin** in the navigation bar
3. Select **Compliance** from the dropdown menu

Or navigate directly to: `/admin/compliance`

## Available Templates

### GDPR (General Data Protection Regulation)

The European Union regulation for data protection and privacy. The GDPR template enforces:

| Setting | Value | Purpose |
|---------|-------|---------|
| `AUTH_ENABLED` | `True` | Controls access to personal data |
| `SENTRY_SEND_DEFAULT_PII` | `False` | Prevents PII leaking to external services |
| `SECURITY_HEADERS_ENABLED` | `True` | Protects against common web vulnerabilities |
| `SECURITY_HEADER_HSTS_ENABLED` | `True` | Ensures encrypted connections |
| `SECURITY_HEADER_CSP_ENABLED` | `True` | Prevents XSS and injection attacks |
| `SECURITY_HEADER_X_FRAME_OPTIONS_ENABLED` | `True` | Prevents clickjacking |
| `ENABLE_DEDUPLICATION` | `True` | Data minimisation — avoids duplicate storage |

### HIPAA (Health Insurance Portability and Accountability Act)

United States regulation for protecting health information. The HIPAA template includes all GDPR settings plus:

| Setting | Value | Purpose |
|---------|-------|---------|
| `MULTI_USER_ENABLED` | `True` | Individual accounts for access accountability |

### SOC 2 (Service Organization Control 2)

Trust Service Criteria framework for service organisations. The SOC 2 template includes the same settings as HIPAA, mapped to SOC 2 Trust Service Criteria (CC6.x, PI1.x).

## Applying a Template

1. Navigate to the **Compliance** dashboard (`/admin/compliance`)
2. Find the template you want to apply (GDPR, HIPAA, or SOC 2)
3. Click **Apply Template**
4. Confirm the action in the dialog
5. The template settings are written to the database immediately

> **Note:** Applying a template writes configuration values to the database. Some settings (e.g., security headers) may require a restart to take effect. Check the Settings page for restart indicators.

## Understanding Compliance Status

Each template shows one of four statuses:

| Status | Badge | Meaning |
|--------|-------|---------|
| **Compliant** | Green | All checks are passing |
| **Partial** | Yellow | Some checks are passing, others are not |
| **Non-Compliant** | Red | No checks are passing |
| **Not Applied** | Grey | Template has never been applied |

### Individual Checks

Click **Show Details** on any template card to see individual check results:

- ✅ **Passing** — The setting matches the expected compliance value
- ❌ **Failing** — The setting does not match; the current and expected values are shown

## API Endpoints

The compliance feature exposes the following API endpoints under `/api/compliance/`:

### List Templates

```bash
GET /api/compliance/templates
```

Returns all compliance templates with their current status.

### Get Single Template

```bash
GET /api/compliance/templates/{name}
```

Returns a single template by name (`gdpr`, `hipaa`, or `soc2`).

### Apply Template

```bash
POST /api/compliance/templates/{name}/apply
```

Applies a compliance template, writing all its settings to the database.

### Get Template Status

```bash
GET /api/compliance/templates/{name}/status
```

Evaluates the live compliance status of a template against current settings.

**Response example:**

```json
{
  "status": "partial",
  "total": 7,
  "passed": 5,
  "failed": 2,
  "check_results": [
    {
      "key": "auth_enabled",
      "label": "Authentication enabled",
      "description": "User authentication must be enabled to control access to personal data.",
      "expected": "True",
      "actual": "True",
      "passing": true
    }
  ]
}
```

### Compliance Summary

```bash
GET /api/compliance/summary
```

Returns an overall compliance summary across all templates.

**Response example:**

```json
{
  "overall_status": "partial",
  "total_checks": 22,
  "total_passed": 18,
  "total_failed": 4,
  "templates": [
    {
      "name": "gdpr",
      "display_name": "GDPR (General Data Protection Regulation)",
      "enabled": true,
      "status": "compliant",
      "total": 7,
      "passed": 7,
      "failed": 0,
      "applied_at": "2026-03-09T12:00:00+00:00",
      "applied_by": "admin@example.com"
    }
  ]
}
```

> **Note:** All API endpoints require admin authentication.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPLIANCE_ENABLED` | `True` | Enable the compliance templates dashboard. Set to `False` to hide the feature. |

## Best Practices

1. **Apply templates before going live** — Set up compliance before processing real documents
2. **Monitor status regularly** — Check the compliance dashboard after configuration changes
3. **Use the refresh button** — After changing settings elsewhere, refresh the compliance page to see updated status
4. **Combine templates** — You can apply multiple templates; settings overlap is handled automatically
5. **Review after updates** — After upgrading DocuElevate, review your compliance status as new checks may be added

## Related Documentation

- [Configuration Guide](./ConfigurationGuide.md) — Full list of configuration options
- [Privacy & Compliance Guide](./PrivacyCompliance.md) — Privacy notice and GDPR compliance details
- [Deployment Guide](./DeploymentGuide.md) — Production deployment with security best practices
- [Security Audit](../SECURITY_AUDIT.md) — Security findings and mitigations
