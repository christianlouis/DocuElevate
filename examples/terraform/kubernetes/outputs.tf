output "namespace" {
  value = var.namespace
}

output "release_name" {
  value = helm_release.docuelevate.name
}

output "application_url" {
  value = "https://${var.external_hostname}"
}

output "agentic_setup_enabled" {
  value = local.agentic_setup_enabled
}
