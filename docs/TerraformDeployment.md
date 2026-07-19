# Terraform deployment

DocuElevate can be installed declaratively on Kubernetes with Terraform. The
reference deployment composes two existing product interfaces:

1. Terraform manages the namespace and DocuElevate Helm release.
2. Helm runs migrations and, when enabled, a post-install setup Job.
3. The Job plans and applies the versioned `DocuElevateSetup` JSON manifest.
4. Settings are validated and stored through the same encrypted database path
   used by the browser setup journey; workers receive live invalidation events.

The runnable reference is in
[`examples/terraform/kubernetes`](https://github.com/christianlouis/DocuElevate/tree/main/examples/terraform/kubernetes).

## Prerequisites

- Terraform 1.6 or newer
- access to Kubernetes through the Helm and Kubernetes providers
- a PostgreSQL database and a suitable persistent storage class
- an existing namespace with two Kubernetes Secrets created by 1Password
  Connect with External Secrets, or an equivalent secret operator
- an immutable DocuElevate image tag

The runtime bootstrap Secret contains at least `DATABASE_URL` and
`SESSION_SECRET`. The optional setup Secret contains only environment keys
referenced from the setup manifest, such as initial user passwords. It is
mounted into the setup Job but never into the long-running API or workers.

The module therefore defaults to `create_namespace = false`. Let the platform
or GitOps layer create the namespace and reconcile its Secrets before applying
the DocuElevate application module. Creating the namespace in this module is an
explicit opt-in for environments where a separate controller can populate the
Secrets before Helm's atomic timeout.

Do not put secret values into Terraform variables, `tfvars`, Helm values or
provider command lines. Marking a Terraform variable as `sensitive` hides it
from normal output but does not keep it out of state.

## Deploy

Copy the example variables and manifest outside source control:

```bash
cd examples/terraform/kubernetes
cp terraform.tfvars.example preprod.auto.tfvars
cp ../../agentic-setup.preprod.json /secure/config/docuelevate-preprod.json
```

Use environment-qualified resource names containing `Preprod`, point at the
existing Secret names, and pin `image_tag` to an immutable version. Then run:

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

The Helm release is atomic. A migration failure, invalid setup manifest, failed
setup plan or failed setup apply causes the release to fail instead of leaving
Terraform reporting a healthy deployment.

Terraform also rejects ambiguous environment naming with exact hyphen-delimited
environment tokens, a floating `latest` image,
and an agentic manifest without its short-lived setup Secret. CI runs real
`terraform init` and `terraform validate` checks for the reference module on
every pull request. After apply, use the non-sensitive `readiness_url` and
`deployed_image` outputs as the start of the acceptance check.

## Acceptance contract for an AI operator

An AI may report the installation ready only after all of these checks pass:

- `terraform plan` was reviewed before the exact saved plan was applied;
- the Helm release and agentic setup Job completed successfully;
- `/api/diagnostic/healthz/ready` returns ready;
- a second `terraform plan` reports no infrastructure changes;
- a second manifest plan reports only unchanged application resources;
- every configured user can log in;
- documents uploaded for two different users remain separated by tenant and
  Tribe rules;
- OAuth integrations are either completed by the relevant user or explicitly
  listed as pending interactive actions;
- the deployed image tag and environment names match the intended target.

The current `v1alpha1` manifest reconciles settings, local users and Tribes.
It can seed the same isolated personal and optional shared Family/Team spaces
that users otherwise create in the onboarding journey; later onboarding is
idempotent and reuses those memberships rather than creating duplicates.
Pipelines, integration instances, routing rules and user-consent OAuth grants
are not silently approximated. Until those resource types are added to the
schema, configure them through their supported product journeys and keep them
as explicit acceptance actions.
