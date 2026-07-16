locals {
  agentic_setup_enabled = var.agentic_setup_manifest_path != null
  agentic_manifest      = local.agentic_setup_enabled ? file(var.agentic_setup_manifest_path) : ""

  docuelevate_values = {
    image = {
      repository = var.image_repository
      tag        = var.image_tag
    }
    env = {
      EXTERNAL_HOSTNAME = var.external_hostname
    }
    secrets = {
      existingSecret = var.bootstrap_secret_name
    }
    agenticSetup = {
      enabled        = local.agentic_setup_enabled
      manifest       = local.agentic_manifest
      existingSecret = var.setup_secret_name
    }
    ingress = {
      enabled   = true
      className = var.ingress_class_name
      hosts = [{
        host = var.external_hostname
        paths = [{
          path     = "/"
          pathType = "Prefix"
        }]
      }]
      tls = var.tls_secret_name == "" ? [] : [{
        secretName = var.tls_secret_name
        hosts      = [var.external_hostname]
      }]
    }
  }
}

resource "kubernetes_namespace_v1" "docuelevate" {
  count = var.create_namespace ? 1 : 0

  metadata {
    name = var.namespace
    labels = {
      "app.kubernetes.io/part-of"     = "docuelevate"
      "app.kubernetes.io/environment" = var.environment
    }
  }
}

resource "helm_release" "docuelevate" {
  name              = var.release_name
  namespace         = var.namespace
  chart             = var.chart_path
  dependency_update = true

  atomic  = true
  wait    = true
  timeout = 900

  values = concat(
    [yamlencode(local.docuelevate_values)],
    var.additional_helm_values,
  )

  depends_on = [kubernetes_namespace_v1.docuelevate]
}
