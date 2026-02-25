{{/*
Expand the name of the chart.
*/}}
{{- define "docuelevate.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this.
If release name contains chart name it will be used as a full name.
*/}}
{{- define "docuelevate.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label value: "chart-name-version"
*/}}
{{- define "docuelevate.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "docuelevate.labels" -}}
helm.sh/chart: {{ include "docuelevate.chart" . }}
{{ include "docuelevate.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "docuelevate.selectorLabels" -}}
app.kubernetes.io/name: {{ include "docuelevate.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "docuelevate.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "docuelevate.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image reference, using appVersion as default tag.
*/}}
{{- define "docuelevate.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion }}
{{- printf "%s:%s" .Values.image.repository $tag }}
{{- end }}

{{/*
Resolve REDIS_URL: prefer externalRedis.url, then secrets.REDIS_URL,
then fall back to the bundled Redis service URL.
*/}}
{{- define "docuelevate.redisUrl" -}}
{{- if .Values.externalRedis.url }}
{{- .Values.externalRedis.url }}
{{- else if .Values.secrets.REDIS_URL }}
{{- .Values.secrets.REDIS_URL }}
{{- else if .Values.redis.enabled }}
{{- printf "redis://%s-redis-master:6379/0" .Release.Name }}
{{- else }}
{{- "" }}
{{- end }}
{{- end }}

{{/*
Resolve GOTENBERG_URL — use env override if set, otherwise build from service name.
*/}}
{{- define "docuelevate.gotenbergUrl" -}}
{{- if .Values.env.GOTENBERG_URL }}
{{- tpl .Values.env.GOTENBERG_URL . }}
{{- else }}
{{- printf "http://%s-gotenberg:3000" (include "docuelevate.fullname" .) }}
{{- end }}
{{- end }}

{{/*
Resolve MEILISEARCH_URL — use env override if set, otherwise build from service name.
*/}}
{{- define "docuelevate.meilisearchUrl" -}}
{{- if .Values.env.MEILISEARCH_URL }}
{{- tpl .Values.env.MEILISEARCH_URL . }}
{{- else }}
{{- printf "http://%s-meilisearch:7700" (include "docuelevate.fullname" .) }}
{{- end }}
{{- end }}
