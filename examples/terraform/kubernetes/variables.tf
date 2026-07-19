variable "release_name" {
  description = "Helm release name. Include the environment in the name."
  type        = string
  default     = "docuelevate-preprod"
}

variable "namespace" {
  description = "Kubernetes namespace containing the externally managed Secrets."
  type        = string
  default     = "docuelevate-preprod"
}

variable "create_namespace" {
  description = "Create the namespace. Keep false when a platform layer also reconciles Secrets into it."
  type        = bool
  default     = false
}

variable "environment" {
  description = "Environment label applied when this module creates the namespace."
  type        = string
  default     = "preprod"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*$", var.environment))
    error_message = "environment must be a lowercase Kubernetes-safe name such as preprod or canary."
  }
}

variable "chart_path" {
  description = "Path to the checked-out DocuElevate Helm chart."
  type        = string
  default     = "../../../helm/docuelevate"
}

variable "image_repository" {
  description = "DocuElevate container repository."
  type        = string
  default     = "ghcr.io/christianlouis/docuelevate"
}

variable "image_tag" {
  description = "Immutable image tag to deploy. Never use latest."
  type        = string

  validation {
    condition     = trimspace(var.image_tag) != ""
    error_message = "image_tag must not be empty."
  }
}

variable "external_hostname" {
  description = "Public hostname used by DocuElevate and OAuth callbacks."
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$", var.external_hostname))
    error_message = "external_hostname must be a hostname without a URL scheme or path."
  }
}

variable "bootstrap_secret_name" {
  description = "Existing Secret with DATABASE_URL, SESSION_SECRET and other process bootstrap values."
  type        = string
}

variable "setup_secret_name" {
  description = "Existing Secret with the manifest's fromEnv values. Not injected into long-running pods."
  type        = string
  default     = ""
}

variable "agentic_setup_manifest_path" {
  description = "Path to a validated DocuElevateSetup JSON manifest, or null to use the browser wizard."
  type        = string
  default     = null
  nullable    = true
}

variable "ingress_class_name" {
  description = "Ingress controller class."
  type        = string
  default     = "nginx"
}

variable "tls_secret_name" {
  description = "Existing TLS Secret for external_hostname. Empty disables TLS configuration."
  type        = string
  default     = ""
}

variable "additional_helm_values" {
  description = "Additional non-secret Helm YAML documents applied after the safe defaults."
  type        = list(string)
  default     = []
}
