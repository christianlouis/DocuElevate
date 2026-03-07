# Billing Setup Guide

This guide covers how to configure Stripe billing and local user sign-up in DocuElevate.

## Table of Contents

- [Local User Sign-up](#local-user-sign-up)
- [Stripe Billing Integration](#stripe-billing-integration)
  - [Prerequisites](#prerequisites)
  - [Configuration](#configuration)
  - [Setting Up Plans](#setting-up-plans)
  - [Webhook Configuration](#webhook-configuration)
  - [Billing Flows](#billing-flows)
- [Compliance Notes](#compliance-notes)

---

## Local User Sign-up

By default, user accounts are created by an administrator. To allow users to self-register with an email address and password, set `ALLOW_LOCAL_SIGNUP=true`.

> **Note:** SMTP is **optional** for local sign-up. When SMTP is configured, new accounts require email verification before they can log in. Without SMTP, accounts are activated immediately upon registration — useful for self-hosted deployments without email infrastructure.

### Configuration

```bash
ALLOW_LOCAL_SIGNUP=true

# SMTP (optional — enables email verification and password reset)
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_USERNAME=noreply@example.com
EMAIL_PASSWORD=yourpassword
EMAIL_USE_TLS=true
EMAIL_SENDER=DocuElevate <noreply@example.com>
```

### Sign-up Flow

**With SMTP configured (recommended):**
1. User visits `/signup` and fills out the registration form.
2. DocuElevate sends a verification email with a 24-hour token link.
3. User clicks the link — their account is activated and they are signed in.
4. First-time users are redirected to the onboarding wizard.

**Without SMTP:**
1. User visits `/signup` and fills out the registration form.
2. Account is activated immediately — no email verification required.
3. User is redirected to the login page to sign in straight away.

### Admin-Created Accounts

Administrators can create local user accounts directly from the **Admin → User Management** page without requiring self-registration. Admin-created accounts are immediately active regardless of SMTP configuration.

### Password Reset Flow

1. User clicks "Forgot password?" on the login page.
2. User enters their email address.
3. DocuElevate sends a password reset email with a 24-hour token link.
4. User clicks the link, enters a new password, and is redirected to sign in.

### Security

- Passwords are hashed with bcrypt (12 rounds).
- Verification and reset tokens are 256-bit URL-safe random strings.
- All tokens expire after 24 hours.
- Sign-up and login endpoints return generic error messages to prevent user enumeration.

---

## Stripe Billing Integration

DocuElevate integrates with [Stripe](https://stripe.com) to handle subscription payments. Stripe acts as a data processor under a Data Processing Agreement (DPA) and is SOC 2 Type II certified.

### Prerequisites

- A Stripe account (sign up at [stripe.com](https://stripe.com))
- Products and prices created in the Stripe Dashboard for each paid plan
- A publicly reachable webhook endpoint (or use [Stripe CLI](https://stripe.com/docs/stripe-cli) for local testing)

### Configuration

```bash
STRIPE_SECRET_KEY=sk_live_...         # Your Stripe secret key
STRIPE_PUBLISHABLE_KEY=pk_live_...    # Your Stripe publishable key (for frontend)
STRIPE_WEBHOOK_SECRET=whsec_...       # Webhook signing secret
STRIPE_SUCCESS_URL=https://app.example.com/api/billing/success  # Optional override
STRIPE_CANCEL_URL=https://app.example.com/pricing               # Optional override
```

> **Security:** Never commit your Stripe secret key. Store it in your environment or secrets manager.

### Setting Up Plans

After starting DocuElevate, go to **Admin → Plans** to configure each plan:

1. Open the **Plan Designer** for a paid tier (e.g. Starter, Professional).
2. Enter the **Stripe Price ID (monthly)** from your Stripe Dashboard (e.g. `price_1OtAbc...`).
3. Optionally enter the **Stripe Price ID (yearly)** for annual billing.
4. Save the plan.

Stripe Price IDs look like `price_1OtAbcDefGhIjKlMnOpQrSt`. Find them in **Products** in your Stripe Dashboard.

### Webhook Configuration

Stripe webhooks allow DocuElevate to sync subscription status in real time.

#### Stripe Dashboard setup

1. Go to **Developers → Webhooks** in the Stripe Dashboard.
2. Click **Add endpoint**.
3. Set the endpoint URL to: `https://your-app-domain.com/api/billing/webhook`
4. Select the following events:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
5. Copy the **Signing secret** and set `STRIPE_WEBHOOK_SECRET` in your environment.

#### Local testing with Stripe CLI

```bash
# Install Stripe CLI and log in
stripe login

# Forward webhooks to your local server
stripe listen --forward-to http://localhost:8000/api/billing/webhook

# Trigger a test event
stripe trigger checkout.session.completed
```

### Billing Flows

#### Subscribe to a plan

1. User visits `/pricing`.
2. User clicks the **CTA button** on a paid plan.
3. DocuElevate calls `POST /api/billing/create-checkout-session`.
4. User is redirected to Stripe Checkout.
5. After payment, Stripe fires `checkout.session.completed`.
6. DocuElevate webhook handler activates the subscription tier.
7. User is redirected to `/api/billing/success`.

#### Manage or cancel subscription

1. User visits their account settings.
2. DocuElevate calls `POST /api/billing/create-portal-session`.
3. User is redirected to the Stripe Customer Portal.
4. User can update payment method, upgrade, downgrade, or cancel.
5. Stripe fires `customer.subscription.updated` or `customer.subscription.deleted`.
6. DocuElevate webhook handler syncs the change.

#### Cancellation

When a subscription is cancelled, Stripe fires `customer.subscription.deleted` and DocuElevate automatically downgrades the user to the free tier.

---

## Compliance Notes

| Topic | Details |
|-------|---------|
| **GDPR** | Stripe acts as a data processor. A Data Processing Agreement (DPA) is available in the Stripe Dashboard. Stripe supports EU data residency. |
| **SOC 2** | Stripe is SOC 2 Type II certified. |
| **EU VAT** | Configure [Stripe Tax](https://stripe.com/tax) in the Stripe Dashboard for automatic VAT collection. |
| **PCI DSS** | Card data is handled entirely by Stripe. DocuElevate never sees or stores card details. |

---

## Environment Variable Reference

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ALLOW_LOCAL_SIGNUP` | bool | `false` | Allow users to self-register with email/password |
| `STRIPE_SECRET_KEY` | string | — | Stripe API secret key |
| `STRIPE_PUBLISHABLE_KEY` | string | — | Stripe API publishable key |
| `STRIPE_WEBHOOK_SECRET` | string | — | Webhook signing secret from Stripe Dashboard |
| `STRIPE_SUCCESS_URL` | string | — | Override redirect URL after successful checkout |
| `STRIPE_CANCEL_URL` | string | — | Override redirect URL when checkout is cancelled |

See [ConfigurationGuide.md](./ConfigurationGuide.md) for the full environment variable reference.
