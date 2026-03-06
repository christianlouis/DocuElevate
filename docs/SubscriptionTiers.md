# Subscription Tiers

DocuElevate operates as a SaaS platform with four subscription tiers. When
`MULTI_USER_ENABLED=True` each user is assigned a tier that controls how many
documents they can process and how many storage destinations they can use.

---

## Tier Overview

| | Free | Starter | Professional | Business |
|---|---|---|---|---|
| **Price / month** | $0 | $9 | $29 | $79 |
| **Price / year** | $0 | $90 | $290 | $790 |
| **Lifetime file limit** | 25 files (total, ever) | Unlimited | Unlimited | Unlimited |
| **Files per day** | Unlimited* | 10 | 50 | Unlimited |
| **Files per month** | Unlimited* | 100 | 500 | Unlimited |
| **Storage destinations** | 1 | 3 | 10 | Unlimited |
| **OCR pages / month** | 50 | 500 | 2 500 | Unlimited |
| **Max file size** | 10 MB | 50 MB | 200 MB | Unlimited |
| **API access** | ✗ | ✓ | ✓ | ✓ |
| **Email ingestion** | ✗ | ✓ | ✓ | ✓ |
| **Webhooks** | ✗ | ✗ | ✓ | ✓ |
| **Support** | Community | Email | Priority email | Dedicated |

\* Free tier is capped by the **lifetime** limit of 25 files; there is no
separate daily or monthly cap on top of that.

---

## Free Tier

The Free tier is designed for exploration. It allows up to **25 documents
processed in total across the lifetime of the account** — this is enforced
strictly; once 25 documents have been processed the upload endpoint returns
HTTP 402 and invites the user to upgrade.

There is no per-day or per-month cap: the user can use all 25 files in a
single day if they wish.

---

## Paid Tiers

### Starter — $9/month (or $90/year)

Good for individuals or small teams getting started with automated document
processing. Provides a meaningful step up from the free tier without a high
price commitment.

- 10 documents/day, 100 documents/month
- 3 storage destinations (e.g. Dropbox + Google Drive + Nextcloud)
- 500 OCR pages/month
- Email ingestion and API access included

### Professional — $29/month (or $290/year) *(Most Popular)*

Better for growing teams that need higher volume and more integration
flexibility.

- 50 documents/day, 500 documents/month
- 10 storage destinations
- 2 500 OCR pages/month
- All processing steps, webhooks, and priority email support

### Business — $79/month (or $790/year)

Best for organisations that need truly unlimited throughput with dedicated
support.

- Unlimited documents and storage destinations
- Unlimited OCR pages
- Unlimited file size
- Custom integrations and dedicated support

> **Contact Sales** for the Business tier — email
> `sales@docuelevate.io` with subject "Business Plan Enquiry".

---

## Limit Enforcement

Limits are enforced in real-time at the upload endpoint
(`POST /api/ui-upload`). When a user exceeds any quota:

1. The uploaded file is discarded.
2. The endpoint returns **HTTP 402 Payment Required** with a human-readable
   `detail` message explaining which limit was hit and how to upgrade.
3. The upload UI displays the error message to the user.

Quota checks run in order:

1. Lifetime file limit (free tier only)
2. Daily file limit
3. Monthly file limit

---

## Admin Management

Administrators can view and change each user's subscription tier from the
**Admin → Users** page (`/admin/users`).

1. Click **Edit** next to any user.
2. Change the **Subscription Plan** dropdown.
3. Click **Save Changes**.

The new limits take effect immediately on the user's next upload attempt.

### API

Admins can also manage tiers via the REST API:

```bash
# Update a user's subscription tier
curl -X PUT /api/admin/users/user@example.com \
  -H 'Content-Type: application/json' \
  -d '{"subscription_tier": "professional", "is_blocked": false}'
```

---

## Platform Statistics

Admins can view platform-wide statistics via:

- **Dashboard** (`/`) — shows total files, today, this month, unique users
  when `MULTI_USER_ENABLED=True`.
- **API** — `GET /api/subscriptions/platform` returns aggregate file counts
  and per-tier user distribution.

---

## Configuration

Subscription tiers are defined in `app/utils/subscription.py` in the `TIERS`
dictionary. Pricing, limits, and feature lists are all set there.

Single-user mode (`MULTI_USER_ENABLED=False`) bypasses all quota checks
entirely — the instance behaves as if every request is on the Business tier.

---

## Pricing Page

The public pricing page is available at `/pricing` and requires no
authentication. It shows the interactive tier comparison table with an
annual/monthly toggle and an FAQ section.

Individual users can view their own subscription status, usage progress bars,
and upgrade options at `/subscription` (requires login).
