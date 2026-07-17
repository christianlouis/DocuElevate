output "namespace" {
  value = var.namespace
}

output "release_name" {
  value = helm_release.docuelevate.name
}

output "application_url" {
  value = "https://${var.external_hostname}"
}

output "readiness_url" {
  description = "Acceptance endpoint that must report database and Redis ready before the deployment is complete."
  value       = "https://${var.external_hostname}/api/diagnostic/healthz/ready"
}

output "deployed_image" {
  description = "Pinned application image selected by the reviewed Terraform plan."
  value       = "${var.image_repository}:${var.image_tag}"
}

output "agentic_setup_enabled" {
  value = local.agentic_setup_enabled
}
