# Terraform deployment for DocuElevate

This example deploys the DocuElevate Helm chart and optionally converges the
application through the same `DocuElevateSetup` manifest used by the local
agentic installer. It is deliberately suitable for an automation agent: inputs,
secret boundaries, plan, apply and acceptance checks are explicit.

## Secret contract

Create the namespace and two Kubernetes Secrets before this application module
runs:

- the bootstrap Secret contains at least `DATABASE_URL` and `SESSION_SECRET`;
- the setup Secret contains the environment names referenced by `fromEnv` in
  the setup manifest, such as `DOCUELEVATE_SETUP_ADMIN_PASSWORD`.

Use 1Password Connect plus External Secrets, or an equivalent secret operator.
Terraform receives **only the Secret names**. Do not pass secret values through
variables, `tfvars`, Helm values or command-line `-var` arguments: Terraform
would retain them in state.

The default `create_namespace = false` is intentional: a platform or GitOps
layer normally creates the namespace and reconciles External Secrets first. Set
it to `true` only when another process can populate the Secrets before Helm's
atomic timeout; otherwise the migration and setup hooks correctly remain
unready rather than starting without credentials.

The setup Secret is injected only into the short-lived setup Job. It is not
available to the API or workers. OAuth user consent remains an interactive
post-install action.

## AI-readable runbook

1. Copy `terraform.tfvars.example` to a file outside source control and use an
   immutable image tag plus environment-qualified names.
2. Copy and edit `../agentic-setup.preprod.json`. Keep all sensitive values as
   `fromEnv` references.
3. Confirm that the namespace and both referenced Kubernetes Secrets exist in the target
   namespace and expose the required key names. Do not read their values.
4. Run `terraform init`, then save and review `terraform plan -out=tfplan`.
5. Apply only that reviewed plan with `terraform apply tfplan`.
6. The Helm hook first runs the manifest's safe `plan`, then its idempotent
   `apply`. A validation or setup failure makes the atomic Helm release fail.
7. Require a successful Helm release, a completed setup Job and a ready response
   from `/api/diagnostic/healthz/ready`.
8. Re-run `terraform plan`; a converged installation must show no changes.
9. Log in as every seeded user and prove document and Tribe isolation before
   treating the Canary as accepted.

Provider authentication is intentionally not defined here. Supply Kubernetes
and Helm provider credentials through your normal CI or workstation identity;
do not commit a kubeconfig or cluster token.
