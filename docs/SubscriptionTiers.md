# Subscription Tiers

DocuElevate uses database-backed subscription plans that are fully configurable by admins via the **Plan Designer** at `/admin/plans`. Four default tiers are seeded automatically on first startup.

## Default Plans

| Plan | Monthly | Yearly | Docs/Month | Lifetime Docs | OCR Pages/Mo | Max File | Mailboxes | Destinations |
|------|---------|--------|-----------|---------------|--------------|----------|-----------|--------------|
| **Free** | $0 | $0 | — | 50 total | 150 total | 5 MB | 0 | 1 |
| **Starter** | $2.99 | $28.99 | 50 | — | 300 | 25 MB | 1 | 2 |
| **Professional** | $5.99 | $57.99 | 150 | — | 750 | 100 MB | 3 | 5 |
| **Business** | $7.99 | $76.99 | 300 | — | 1,500 | Unlimited | Unlimited | 10 |

> Prices ex-VAT. German customers add 19% MwSt.

All paid plans include a **30-day free trial**.

## How Plans Are Stored

Plans are stored in the `subscription_plans` database table. On application startup, `seed_default_plans()` is called automatically — if the table is empty, the four built-in defaults are inserted. If plans already exist, the seed is a no-op.

Users are assigned a plan via `UserProfile.subscription_tier` (stores the `plan_id` string). The subscription utility functions (`get_tier`, `get_all_tiers`) query the database first and fall back to the hard-coded `TIER_DEFAULTS` dict if the database is unavailable or the plan doesn't exist.

## Overage Buffer

### Announced vs. Enforced Limit

DocuElevate uses a **soft-limit overage buffer** that is invisible to users:

- The **announced limit** is what appears on the pricing page (e.g., "150 docs/month").
- The **enforced limit** = announced × (1 + overage_percent / 100).
  - With the default 20% buffer: a 150-doc plan enforces at **180 docs**.
  - This prevents hard cutoffs at the exact announced limit, giving users a graceful landing.

### Per-Plan vs. Global Buffer

Each plan has its own `overage_percent` field (set in the Plan Designer). There is also a global fallback: `settings.subscription_overage_percent` (default: 20, range: 0–200), which applies when a plan does not have an explicit value.

Set `subscription_overage_percent=0` in your `.env` to enforce exactly at the announced limit with no buffer.

## Yearly Billing & Carry-Over

When a user's `subscription_billing_cycle` is set to `yearly`:

- Unused quota from earlier months **rolls forward automatically**.
- Enforcement = `monthly_limit × months_elapsed × overage_factor` (cumulative budget from the subscription start date).
- Example: A 50-doc/month Starter plan in month 3 of its annual period has a cumulative budget of 150 docs (plus overage buffer). If the user only used 20 docs in months 1–2, they can use 130 docs in month 3.
- The `subscription_period_start` field on `UserProfile` tracks the start of the annual period.

## No Daily Cap

`daily_upload_limit` is kept for display and future reference only — it is **never enforced**. All enforcement is lifetime (free tier) or monthly/cumulative-yearly (paid tiers).

## allow_overage Flag

Setting `UserProfile.allow_overage = True` bypasses monthly quota checks entirely for that user. Usage is still tracked so future billing integrations can charge retroactively. This field is not yet exposed in the admin UI.

## Plan Designer

Navigate to `/admin/plans` (admin only) to:

1. **View** all plans (active and inactive) with key stats.
2. **Create** a new plan with a custom `plan_id` slug.
3. **Edit** any plan's pricing, limits, overage buffer, features, and display settings.
4. **Reorder** plans using the up/down arrows (order reflects pricing page display order).
5. **Delete** a plan (does not affect existing users assigned to it).
6. **Restore Defaults** — seeds the four built-in plans (no-op if plans already exist).

### Overage Designer

The Plan Designer includes an overage slider (0–100%). The live preview shows:

> "Announce **X** docs, enforce at **Y** docs"

Overage billing and per-doc overage pricing are planned future features (currently disabled in the UI).

## API Endpoints

All plan endpoints are under `/api/plans/`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/plans/` | Public | List active plans in sort order |
| `GET` | `/api/plans/admin` | Admin | List all plans including inactive |
| `POST` | `/api/plans/?plan_id=<id>` | Admin | Create a new plan |
| `GET` | `/api/plans/{plan_id}` | Public | Get a single active plan |
| `PUT` | `/api/plans/{plan_id}` | Admin | Update an existing plan |
| `DELETE` | `/api/plans/{plan_id}` | Admin | Delete a plan |
| `POST` | `/api/plans/seed` | Admin | Seed default plans (no-op if non-empty) |
| `POST` | `/api/plans/reorder` | Admin | Update sort order; body: `{"order": ["free", "starter", ...]}` |

### Example: List Active Plans

```bash
curl http://localhost:8000/api/plans/
```

### Example: Update a Plan's Monthly Limit

```bash
curl -X PUT http://localhost:8000/api/plans/starter \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Starter",
    "monthly_upload_limit": 75,
    "overage_percent": 15,
    ...
  }'
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SUBSCRIPTION_OVERAGE_PERCENT` | `20` | Global overage buffer (0–200). Per-plan setting overrides this. |

See `docs/ConfigurationGuide.md` for all available settings.
