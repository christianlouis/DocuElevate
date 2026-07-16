# Agentic setup

DocuElevate can be configured declaratively by an automation agent. The agent
describes the desired instance in a versioned JSON manifest, previews the exact
changes, applies them idempotently, and verifies the resulting state. This uses
the same validation, encrypted database storage and live worker invalidation as
the browser wizard.

The intended prompt is therefore practical: “Install DocuElevate as a Preprod
Canary, create Christian and Julia, place both in the family Tribe, configure
the AI provider and leave only interactive OAuth approvals for me.”

## Safety contract

- Always run `plan` before `apply`.
- `DATABASE_URL` and `SESSION_SECRET` remain deployment bootstrap values. A
  manifest cannot move them into the database it is trying to open.
- Sensitive values are rejected when written directly into JSON. Use a
  `fromEnv` reference and let the authorised process receive the value from a
  secret manager.
- Plans and apply reports never print resolved secret values.
- Settings and their audit history are encrypted at rest. If encryption is not
  available, a sensitive setting is rejected instead of falling back to
  plaintext.
- Reapplying the same manifest is a no-op. User passwords are verified, not
  needlessly re-hashed on every run.
- A manifest may create local users, their isolated personal Tribes and shared
  Tribes. Documents are still bound to one tenant and one Tribe; this command
  does not weaken document access rules.
- User-consent OAuth grants cannot be faked by an agent. They are returned as
  explicit next actions and completed through the normal browser OAuth flow.

## Manifest format

Start from
[`examples/agentic-setup.preprod.json`](https://github.com/christianlouis/DocuElevate/blob/main/examples/agentic-setup.preprod.json).
The current schema is `docuelevate.org/v1alpha1` with kind
`DocuElevateSetup`. Unknown fields and unsupported resources fail validation;
they are never silently ignored.

Automation can validate structure and generate forms from the published
[`v1alpha1` JSON Schema](https://github.com/christianlouis/DocuElevate/blob/main/schemas/docuelevate-setup-v1alpha1.schema.json).
The application additionally validates setting names, types, allowed values,
secret handling, uniqueness and database conflicts at plan time.

`spec.settings` accepts normal setting names. Non-sensitive scalars can be
written directly. Sensitive values must use an environment reference:

```json
{
  "openai_api_key": {
    "fromEnv": "DOCUELEVATE_SETUP_OPENAI_API_KEY"
  }
}
```

`spec.users` creates or reconciles active local accounts. Passwords must use
`fromEnv` and contain at least 12 characters. Every user receives a personal
Tribe with an admin membership.

`spec.tribes` reconciles shared Tribe membership by email. Removing a member
from the manifest removes that membership from the named shared Tribe, but does
not delete the user, personal Tribe or documents.

## Agent workflow

1. Clone DocuElevate and create a disposable, environment-qualified Compose
   project as described in the deployment guide.
2. Copy the example manifest outside the repository and change only the desired
   non-secret parameters.
3. Inject the referenced environment variables into the authorised process.
   A secret manager may do this without revealing the values to the agent.
4. Preview the exact desired-state change:

   ```bash
   docker-compose run --rm \
     -v "$PWD/agentic-setup.preprod.json:/config/setup.json:ro" \
     api python -m app.agentic_setup plan /config/setup.json
   ```

5. Review the JSON result. It reports `create`, `update` and `unchanged` items
   and uses `<resolved-secret>` for credentials.
6. Apply the same manifest:

   ```bash
   docker-compose run --rm \
     -v "$PWD/agentic-setup.preprod.json:/config/setup.json:ro" \
     api python -m app.agentic_setup apply /config/setup.json
   ```

7. Require `success: true` and `setup_completed: true`. Treat
   `missing_required_settings`, `restart_required`, and `next_actions` as work
   still to perform, not as a successful finished installation.
8. Re-run `plan`. A converged instance reports only `unchanged` resources.
9. Check `/api/diagnostic/healthz/ready`, log in as each configured user, upload
   distinct documents, and prove that personal/private documents do not leak
   across users or Tribes.

## Terraform and Kubernetes

The reference module in
[`examples/terraform/kubernetes`](https://github.com/christianlouis/DocuElevate/tree/main/examples/terraform/kubernetes) deploys
the Helm chart and can mount this same manifest into a post-install Job. Helm
runs the DocuElevate `plan` first and only applies a valid plan. The Job is
idempotent, so a later `terraform apply` converges instead of creating duplicate
users or Tribes.

Terraform receives only the names of two existing Kubernetes Secrets: a runtime
bootstrap Secret and an optional short-lived setup Secret for the manifest's
`fromEnv` values. This prevents database passwords, session keys, API keys and
initial user passwords from being copied into Terraform state. See the
[Terraform deployment guide](TerraformDeployment.md) for the complete contract.

## What remains interactive

OAuth application credentials can be supplied as settings or deployment
secrets. A user's Dropbox, Google Drive or OneDrive consent still requires that
user to authenticate with the provider. An agent should open or hand off those
flows, then continue validation after the callback has stored the encrypted
grant in the database. It must never invent, scrape or copy a user's OAuth
grant from another installation.
