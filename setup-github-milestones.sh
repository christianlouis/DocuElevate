#!/usr/bin/env bash
#
# DocuElevate — GitHub Milestone & Issue Setup Script
#
# Prerequisites:
#   1. Install gh CLI: https://cli.github.com/
#   2. Authenticate: gh auth login
#   3. Run: chmod +x setup-github-milestones.sh && ./setup-github-milestones.sh
#
# This script is idempotent for milestones/labels (skips duplicates).
# Issues are always created new, so only run the issue section once.
#

set -euo pipefail

REPO="christianlouis/DocuElevate"
DRY_RUN="${DRY_RUN:-false}"  # Set DRY_RUN=true to preview without creating

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!!]${NC} $1"; }
info() { echo -e "${BLUE}[--]${NC} $1"; }
err()  { echo -e "${RED}[XX]${NC} $1"; }

echo ""
echo "============================================="
echo "  DocuElevate GitHub Project Setup"
echo "============================================="
echo ""

# ── Preflight ──
command -v gh &>/dev/null || { err "gh CLI not found. Install: https://cli.github.com/"; exit 1; }
gh auth status &>/dev/null || { err "Not authenticated. Run: gh auth login"; exit 1; }
gh api "repos/$REPO" --jq '.full_name' &>/dev/null || { err "Cannot access $REPO"; exit 1; }
log "Authenticated. Repo: $REPO"
echo ""

# ══════════════════════════════════════════════
# PHASE 1: LABELS
# ══════════════════════════════════════════════
echo "--- Phase 1: Labels ---"
echo ""

create_label() {
    local name="$1" color="$2" desc="$3"
    if [ "$DRY_RUN" = "true" ]; then info "[DRY] label: $name"; return; fi
    local resp
    resp=$(gh api "repos/$REPO/labels" -f name="$name" -f color="$color" -f description="$desc" 2>&1) && \
        log "Label: $name" || {
        if echo "$resp" | grep -q "already_exists"; then
            info "Label exists: $name"
        else
            warn "Label failed: $name"
        fi
    }
}

create_label "security"             "e11d48" "Security hardening and vulnerability fixes"
create_label "testing"              "0e8a16" "Test coverage and quality improvements"
create_label "refactor"             "d4c5f9" "Code refactoring and cleanup"
create_label "ci/cd"                "fbca04" "CI/CD pipeline improvements"
create_label "ui/ux"                "7057ff" "UI/UX improvements and frontend work"
create_label "performance"          "f9d0c4" "Performance optimization"
create_label "area: api"            "c2e0c6" "REST API related"
create_label "area: frontend"       "bfdadc" "Frontend and UI related"
create_label "area: backend"        "d4e5f7" "Backend and core logic"
create_label "area: ai"             "ff6f61" "AI/ML and document intelligence"
create_label "area: infrastructure" "fef2c0" "Infrastructure, Docker, deployment"
create_label "priority: critical"   "b60205" "Must fix immediately"
create_label "priority: high"       "d93f0b" "Important for next release"
create_label "priority: medium"     "fbca04" "Should be addressed soon"
create_label "priority: low"        "0e8a16" "Nice to have, backlog"
create_label "agentic-ready"        "1d76db" "Well-defined for autonomous agent work"
create_label "breaking-change"      "e11d48" "Introduces breaking API or behavior changes"
create_label "needs-design"         "d876e3" "Requires design decisions before implementation"
echo ""

# ══════════════════════════════════════════════
# PHASE 2: MILESTONES
# ══════════════════════════════════════════════
echo "--- Phase 2: Milestones ---"
echo ""

# Returns milestone number on stdout. All logging goes to stderr.
get_or_create_milestone() {
    local title="$1" due="$2" desc="$3"

    # Check if it already exists
    local existing
    existing=$(gh api "repos/$REPO/milestones?state=all&per_page=100" --jq ".[] | select(.title==\"$title\") | .number" 2>/dev/null || echo "")
    if [ -n "$existing" ]; then
        echo -e "${BLUE}[--]${NC} Milestone exists: $title (#$existing)" >&2
        echo "$existing"
        return
    fi

    if [ "$DRY_RUN" = "true" ]; then
        echo -e "${BLUE}[--]${NC} [DRY] milestone: $title" >&2
        echo "0"
        return
    fi

    local num
    num=$(gh api "repos/$REPO/milestones" \
        -f title="$title" \
        -f state="open" \
        -f due_on="$due" \
        -f description="$desc" \
        --jq '.number' 2>/dev/null || echo "")

    if [ -n "$num" ] && [ "$num" != "0" ]; then
        echo -e "${GREEN}[OK]${NC} Milestone: $title (#$num)" >&2
        echo "$num"
    else
        echo -e "${RED}[XX]${NC} Failed to create milestone: $title" >&2
        echo "0"
    fi
}

MS_05x=$(get_or_create_milestone "v0.5.x - Quality & Stability" "2026-03-31T23:59:59Z" \
"Theme: Security hardening, test coverage, code quality, bug fixes.
Goals: 60%+ code coverage, security hardening, strict linting, fix bugs, improve docs.
Release: Patch releases via semantic-release. Agent: Use conventional commits.")

MS_06=$(get_or_create_milestone "v0.6.0 - Enhanced Search & UI" "2026-04-30T23:59:59Z" \
"Theme: Full-text search, filtering, mobile responsive, dark mode, document preview.
Breaking: API response format changes for search endpoints.
Release: Minor release via feat: commits.")

MS_07=$(get_or_create_milestone "v0.7.0 - Workflow Automation" "2026-06-30T23:59:59Z" \
"Theme: Custom pipelines, conditional routing, webhooks, scheduling.
Release: Minor release. Pipeline engine is foundational dependency.")

MS_08=$(get_or_create_milestone "v0.8.0 - Advanced AI & Multi-language" "2026-08-31T23:59:59Z" \
"Theme: Pluggable AI providers, multi-language OCR, similarity, i18n.
Release: Minor release. AI abstraction layer is foundational.")

MS_10=$(get_or_create_milestone "v1.0.0 - Enterprise Edition" "2026-11-30T23:59:59Z" \
"Theme: Multi-tenancy, RBAC, scaling, integrations, collaboration, analytics.
BREAKING: DB schema + API auth changes. Multi-tenancy first.")

MS_20=$(get_or_create_milestone "v2.0.0 - Platform Expansion" "2027-09-30T23:59:59Z" \
"Theme: Self-hosted AI, desktop/mobile apps, compliance, plugin ecosystem.
Long-term strategic vision.")

echo ""
info "Milestone IDs: v0.5.x=$MS_05x v0.6.0=$MS_06 v0.7.0=$MS_07 v0.8.0=$MS_08 v1.0.0=$MS_10 v2.0.0=$MS_20"
echo ""

# Validate milestone IDs
for ms_var in MS_05x MS_06 MS_07 MS_08 MS_10 MS_20; do
    val="${!ms_var}"
    if [ -z "$val" ] || [ "$val" = "0" ]; then
        err "Milestone $ms_var has invalid ID ($val). Cannot continue."
        exit 1
    fi
done

# ══════════════════════════════════════════════
# PHASE 3: ASSIGN EXISTING ISSUES
# ══════════════════════════════════════════════
echo "--- Phase 3: Assign Existing Issues to v0.5.x ---"
echo ""

for issue in 92 94 95 96 161 164 165 168 169 170 171 172 173 174 175 176; do
    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY] assign #$issue -> milestone $MS_05x"
    else
        gh api "repos/$REPO/issues/$issue" -X PATCH -F milestone="$MS_05x" --silent 2>/dev/null && \
            log "Assigned #$issue to v0.5.x" || warn "Failed to assign #$issue"
    fi
done
echo ""

# ══════════════════════════════════════════════
# PHASE 4: CREATE NEW ISSUES
# ══════════════════════════════════════════════
echo "--- Phase 4: Create Issues ---"
echo ""

# Create issue via gh api (reliable, full control)
# Usage: create_issue <milestone_number> <title> <body> <label1> <label2> ...
ISSUE_COUNT=0
ISSUE_FAIL=0

create_issue() {
    local ms_num="$1"
    local title="$2"
    local body="$3"
    shift 3
    local labels=("$@")

    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY] issue: $title"
        return
    fi

    # Build JSON payload
    local labels_json="["
    local first=true
    for lbl in "${labels[@]}"; do
        if [ "$first" = true ]; then first=false; else labels_json+=","; fi
        labels_json+="\"$lbl\""
    done
    labels_json+="]"

    local payload
    payload=$(jq -n \
        --arg title "$title" \
        --arg body "$body" \
        --argjson milestone "$ms_num" \
        --argjson labels "$labels_json" \
        '{title: $title, body: $body, milestone: $milestone, labels: $labels}')

    local result
    result=$(echo "$payload" | gh api "repos/$REPO/issues" --input - --jq '.number' 2>&1)

    if [[ "$result" =~ ^[0-9]+$ ]]; then
        log "#$result: $title"
        ISSUE_COUNT=$((ISSUE_COUNT + 1))
    else
        err "FAILED: $title"
        err "  Response: $result"
        ISSUE_FAIL=$((ISSUE_FAIL + 1))
    fi

    # Rate-limit courtesy
    sleep 0.3
}

# ────────────────────────────────────────
# v0.5.x — Quality & Stability
# ────────────────────────────────────────
echo ""
echo "  >>> v0.5.x — Quality & Stability <<<"
echo ""

create_issue "$MS_05x" \
  "test: achieve 60% code coverage across the project" \
  "## Summary
Current test coverage is ~48%. We need to reach 60% as a first quality gate.

## Context
- Current: 48.17% (see \`TODO_TESTS.md\`)
- Target: 60% (Phase 1), then 70%, then 80%
- Key uncovered areas: API routes, task modules, view routes

## Acceptance Criteria
- [ ] Overall code coverage >= 60% via pytest-cov
- [ ] All new tests pass in CI
- [ ] No reduction in existing module coverage
- [ ] Coverage report uploaded to Codecov

## Implementation Notes
- Focus on modules in \`TODO_TESTS.md\` Phase 1 and 2
- Priority: \`app/api/\` routes, \`app/tasks/convert_to_pdf.py\`, \`app/tasks/embed_metadata_into_pdf.py\`
- Use mocks for external services (Azure, OpenAI, cloud providers)

## Files
- \`TODO_TESTS.md\` — module coverage breakdown
- \`tests/conftest.py\` — existing fixtures

## Agent Notes
Run \`pytest --cov=app --cov-report=term-missing\`. Commit: \`test: increase code coverage to 60%\`" \
  "testing" "priority: high" "agentic-ready" "area: backend"

create_issue "$MS_05x" \
  "fix: resolve session timeout issues with Authentik OAuth" \
  "## Summary
Users experience unexpected session timeouts when authenticated via Authentik OAuth.

## Acceptance Criteria
- [ ] Sessions persist for configured duration without unexpected drops
- [ ] Token refresh works correctly before expiry
- [ ] Graceful redirect to login on true expiry
- [ ] No security regressions

## Implementation Notes
- Check token refresh logic in \`app/auth.py\`
- Verify session middleware config in \`app/main.py\`
- May need proper OAuth token refresh flow

## Files
- \`app/auth.py\`, \`app/main.py\`, \`app/utils/oauth_helper.py\`" \
  "bug" "priority: high" "agentic-ready" "area: backend"

create_issue "$MS_05x" \
  "fix: improve Redis connection pool handling and failure recovery" \
  "## Summary
Redis connection failures cause cascading issues. Need proper connection pooling and graceful degradation.

## Acceptance Criteria
- [ ] Redis connections use configured pool (\`max_connections\` limit)
- [ ] Failures retried with exponential backoff
- [ ] App degrades gracefully when Redis is temporarily down
- [ ] Health check at \`/status\` reports Redis connectivity
- [ ] Pool metrics available for monitoring

## Files
- \`app/celery_worker.py\`, \`app/config.py\`" \
  "bug" "priority: high" "agentic-ready" "area: infrastructure"

create_issue "$MS_05x" \
  "fix: handle large file uploads (>100MB) reliably" \
  "## Summary
Uploads >100MB fail or timeout. Must support the advertised 500MB limit.

## Acceptance Criteria
- [ ] Files up to 500MB upload successfully via UI and API
- [ ] Upload progress accurately reported
- [ ] Worker timeouts configured for large files
- [ ] Memory bounded (streaming, not buffering)
- [ ] Temp files cleaned up in all code paths

## Files
- \`app/api/upload.py\`, \`app/tasks/\`, \`frontend/js/upload.js\`" \
  "bug" "priority: high" "agentic-ready" "area: api"

create_issue "$MS_05x" \
  "fix: correct timezone handling inconsistencies" \
  "## Summary
Timestamps mix UTC and local time across the app.

## Acceptance Criteria
- [ ] All DB timestamps stored as UTC
- [ ] API responses use ISO 8601 with timezone info
- [ ] Frontend displays in user's local timezone
- [ ] Processing logs use consistent UTC

## Implementation Notes
- Replace \`datetime.now()\` with \`datetime.now(timezone.utc)\`
- SQLAlchemy: \`DateTime(timezone=True)\`
- Jinja2: timezone-aware formatting

## Files
- \`app/models.py\`, \`app/views/\`" \
  "bug" "priority: medium" "agentic-ready" "area: backend"

create_issue "$MS_05x" \
  "refactor: enforce strict linting (Black, isort, Flake8)" \
  "## Summary
Code style is inconsistently enforced. Make linting a blocking CI check.

## Acceptance Criteria
- [ ] All Python files pass Black
- [ ] All imports sorted by isort
- [ ] Zero Flake8 violations (or documented exclusions)
- [ ] CI fails on any lint violation
- [ ] Pre-commit hooks enforce formatting

## Files
- \`pyproject.toml\`, \`.github/workflows/\`, \`.pre-commit-config.yaml\`

## Agent Notes
Commit: \`style: enforce strict linting across codebase\`" \
  "refactor" "ci/cd" "priority: high" "agentic-ready"

create_issue "$MS_05x" \
  "refactor: add comprehensive type hints to core modules" \
  "## Summary
Core modules lack type hints, hindering IDE support and type checking.

## Acceptance Criteria
- [ ] Type hints on all public functions in: \`config.py\`, \`models.py\`, \`database.py\`, \`auth.py\`, \`main.py\`
- [ ] Type hints on all API routes in \`app/api/\`
- [ ] Type hints on all tasks in \`app/tasks/\`
- [ ] Type hints on all utils in \`app/utils/\`
- [ ] mypy passes with no errors

## Agent Notes
Commit: \`refactor: add type hints to core modules\`" \
  "refactor" "priority: medium" "agentic-ready" "area: backend"

create_issue "$MS_05x" \
  "refactor: break up large functions in main modules" \
  "## Summary
Several modules contain oversized functions (50+ lines). Extract into focused helpers.

## Acceptance Criteria
- [ ] No function exceeds 50 lines of logic
- [ ] Extracted functions have clear single responsibility
- [ ] All existing tests still pass
- [ ] New unit tests cover extracted functions

## Files
- \`app/tasks/\`, \`app/views/\`, \`app/config.py\`

## Agent Notes
Commit: \`refactor: extract helper functions from large modules\`" \
  "refactor" "priority: medium" "agentic-ready" "area: backend"

create_issue "$MS_05x" \
  "docs: add architecture diagram to documentation" \
  "## Summary
Add a visual architecture diagram showing component interactions.

## Acceptance Criteria
- [ ] Diagram (Mermaid or SVG) showing: Web UI -> FastAPI -> Celery -> Redis -> Workers -> External Services
- [ ] Storage providers, AI services, auth flow shown
- [ ] Added to README.md or \`docs/architecture.md\`

## Components
FastAPI, Celery, Redis, PostgreSQL/SQLite, Dropbox, Google Drive, OneDrive, Nextcloud, S3, Paperless NGX, Azure Doc Intelligence, OpenAI, Gotenberg, Authentik

## Agent Notes
Commit: \`docs: add architecture diagram\`" \
  "documentation" "priority: medium" "agentic-ready"

create_issue "$MS_05x" \
  "docs: document all environment variables with descriptions and defaults" \
  "## Summary
No single reference for all environment variables. Create one.

## Acceptance Criteria
- [ ] Complete list with: name, description, default, required/optional, example
- [ ] Organized by category (DB, Redis, OAuth, AI, storage, etc.)
- [ ] Cross-referenced with \`app/config.py\`

## Files
- \`app/config.py\`, \`docker-compose.yml\`

## Agent Notes
Commit: \`docs: document all environment variables\`" \
  "documentation" "priority: medium" "agentic-ready"

create_issue "$MS_05x" \
  "docs: add troubleshooting guide for common issues" \
  "## Summary
Troubleshooting guide covering common deployment and operational issues.

## Acceptance Criteria
- [ ] Coverage: Docker startup, Redis failures, OAuth config, OCR failures, storage auth, Celery workers, large uploads, DB migrations
- [ ] Each issue: symptom, likely cause, solution steps
- [ ] Added to README or \`docs/troubleshooting.md\`

## Agent Notes
Commit: \`docs: add troubleshooting guide\`" \
  "documentation" "priority: low" "agentic-ready"

# ────────────────────────────────────────
# v0.6.0 — Enhanced Search & UI
# ────────────────────────────────────────
echo ""
echo "  >>> v0.6.0 — Enhanced Search & UI <<<"
echo ""

create_issue "$MS_06" \
  "feat: implement full-text search across documents and metadata" \
  "## Summary
Add full-text search so users can find documents by content, metadata, filename, and OCR text.

## Acceptance Criteria
- [ ] Search bar on /files page with instant results
- [ ] Search across: filename, OCR text, AI metadata, tags
- [ ] Results ranked by relevance with term highlighting
- [ ] API: \`GET /api/search?q=...\`
- [ ] Paginated results
- [ ] Performance: <500ms for 10,000 documents

## Implementation Notes
- Start with PostgreSQL full-text search (pg_trgm + tsvector)
- Design abstraction for future Elasticsearch/Meilisearch
- Add DB migration for search indexes

## API
\`\`\`
GET /api/search?q=invoice&type=pdf&date_from=2026-01-01&page=1&per_page=20
\`\`\`

## Agent Notes
Foundational v0.6.0 feature. Commit: \`feat: add full-text search for documents\`" \
  "enhancement" "priority: high" "agentic-ready" "area: api" "area: backend" "breaking-change"

create_issue "$MS_06" \
  "feat: add advanced filtering and saved searches" \
  "## Summary
Filter documents by multiple criteria; save frequently used filters.

## Acceptance Criteria
- [ ] Filter by: date range, file type, status, storage provider, tags
- [ ] Multiple filters combinable (AND logic)
- [ ] Sort by: date, name, size, status
- [ ] Save filter combos as saved searches per user
- [ ] Filter state in URL (shareable)
- [ ] API supports all filter params

## Depends On
- Full-text search implementation

## Agent Notes
Commit: \`feat: add advanced filtering and saved searches\`" \
  "enhancement" "priority: high" "agentic-ready" "area: api" "area: frontend"

create_issue "$MS_06" \
  "feat: implement responsive mobile interface" \
  "## Summary
Make the UI fully responsive for phones and tablets.

## Acceptance Criteria
- [ ] All pages correct on 320px to 1920px+ viewports
- [ ] Nav collapses to hamburger on small screens
- [ ] File list changes to card view on mobile
- [ ] Upload works on mobile (incl. camera)
- [ ] Touch-friendly targets (min 44px)
- [ ] No horizontal scrolling
- [ ] Tested: iOS Safari, Android Chrome, tablet

## Implementation Notes
- Tailwind responsive utilities (sm:, md:, lg:, xl:)
- File table to card at md (768px)

## Agent Notes
Commit: \`feat: add responsive mobile interface\`" \
  "enhancement" "ui/ux" "priority: high" "agentic-ready" "area: frontend"

create_issue "$MS_06" \
  "feat: add dark mode support" \
  "## Summary
Dark/light mode toggle with system preference detection.

## Acceptance Criteria
- [ ] Toggle in navbar
- [ ] System preference detection (prefers-color-scheme)
- [ ] Preference persisted (localStorage + DB setting)
- [ ] All pages styled in both modes
- [ ] WCAG AA contrast compliance
- [ ] Smooth transition animation

## Implementation Notes
- Tailwind darkMode: class strategy
- dark: variants on all color utilities

## Agent Notes
Commit: \`feat: add dark mode support\`" \
  "enhancement" "ui/ux" "priority: medium" "agentic-ready" "area: frontend"

create_issue "$MS_06" \
  "feat: add in-browser document preview" \
  "## Summary
Preview PDFs, images, and text files without downloading.

## Acceptance Criteria
- [ ] PDF preview (pdf.js or native)
- [ ] Image preview (JPEG, PNG, TIFF, WebP) with zoom
- [ ] Text preview with syntax highlighting
- [ ] Preview in modal from file list
- [ ] Works for original and processed docs
- [ ] Fallback for unsupported types
- [ ] Streaming for large files

## API
\`GET /api/files/{id}/preview\`

## Agent Notes
Commit: \`feat: add in-browser document preview\`" \
  "enhancement" "ui/ux" "priority: high" "agentic-ready" "area: frontend" "area: api"

create_issue "$MS_06" \
  "feat: add bulk operations (select, delete, reprocess, download)" \
  "## Summary
Select multiple files and perform bulk actions.

## Acceptance Criteria
- [ ] Checkbox selection (individual, all, page)
- [ ] Bulk delete with confirmation
- [ ] Bulk reprocess
- [ ] Bulk download as ZIP
- [ ] Bulk toolbar on selection
- [ ] Async via Celery for large batches

## API
\`\`\`
POST /api/files/bulk { action: \"delete\", file_ids: [...] }
POST /api/files/bulk/download { file_ids: [...] }
\`\`\`

## Agent Notes
Commit: \`feat: add bulk file operations\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: api" "area: frontend"

create_issue "$MS_06" \
  "feat: implement proper pagination for file list API" \
  "## Summary
Server-side pagination with consistent API format.

## Acceptance Criteria
- [ ] Server-side pagination (default 25 per page)
- [ ] Response: page, per_page, total, pages, next, previous
- [ ] UI pagination controls
- [ ] URL reflects page state
- [ ] Consistent format across all list endpoints

## Breaking Changes
Wraps /api/files in pagination envelope.

## Agent Notes
Commit: \`feat: add paginated file list API\`" \
  "enhancement" "priority: high" "agentic-ready" "area: api" "breaking-change"

create_issue "$MS_06" \
  "feat: add file download endpoint" \
  "## Summary
Direct download for original and processed files.

## Acceptance Criteria
- [ ] \`GET /api/files/{id}/download\` — processed file
- [ ] \`GET /api/files/{id}/download?version=original\` — original
- [ ] Content-Disposition with original filename
- [ ] Streaming for large files
- [ ] Auth required
- [ ] Download button in UI

## Agent Notes
Commit: \`feat: add file download endpoint\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: api"

create_issue "$MS_06" \
  "perf: optimize database queries and add caching layer" \
  "## Summary
Fix slow queries and add Redis caching.

## Acceptance Criteria
- [ ] Fix N+1 queries in file list/detail views
- [ ] Add indexes for common query columns
- [ ] Redis caching for settings, sessions, frequent responses
- [ ] Cache invalidation on changes
- [ ] /files with 1000+ docs in <1 second

## Implementation Notes
- SQLAlchemy selectinload/joinedload
- Composite indexes for filter/sort
- Redis for app-level cache

## Agent Notes
Commit: \`perf: optimize database queries and add caching\`" \
  "performance" "priority: medium" "agentic-ready" "area: backend"

# ────────────────────────────────────────
# v0.7.0 — Workflow Automation
# ────────────────────────────────────────
echo ""
echo "  >>> v0.7.0 — Workflow Automation <<<"
echo ""

create_issue "$MS_07" \
  "feat: build custom processing pipeline engine" \
  "## Summary
Pipeline engine for custom document processing workflows as ordered steps.

## Context
Currently all documents follow one fixed path. Different types need different workflows.

## Acceptance Criteria
- [ ] Pipeline model: ordered steps with per-step config
- [ ] Built-in steps: OCR, metadata extraction, PDF conversion, cloud upload, classification
- [ ] Pipeline CRUD API and management UI
- [ ] Documents assignable to specific pipelines
- [ ] Default pipeline for unassigned docs
- [ ] Per-document step-level status tracking
- [ ] Failed steps retryable individually

## Data Model
\`\`\`
Pipeline: id, name, description, steps (JSON), is_default, created_at
PipelineStep: order, type, config (JSON), on_failure (skip|stop|retry)
PipelineExecution: document_id, pipeline_id, status, current_step, timestamps
\`\`\`

## Implementation Notes
- FOUNDATIONAL for v0.7.0 — build first
- Use Celery chains/chords for step execution
- Pluggable steps via registry pattern
- Execution idempotent and resumable

## Agent Notes
Commit: \`feat: add custom processing pipeline engine\`. BUILD THIS FIRST." \
  "enhancement" "priority: critical" "agentic-ready" "area: backend" "needs-design"

create_issue "$MS_07" \
  "feat: add conditional routing based on document type and metadata" \
  "## Summary
Pipelines branch based on document properties.

## Acceptance Criteria
- [ ] Rules based on: file type, category, metadata, size, source
- [ ] Conditions: equals, contains, regex, greater/less than
- [ ] Multiple rules with AND/OR logic
- [ ] Default route for unmatched
- [ ] Routing logged for audit
- [ ] UI for creating/testing rules

## Depends On
- Pipeline engine

## Agent Notes
Commit: \`feat: add conditional document routing\`" \
  "enhancement" "priority: high" "agentic-ready" "area: backend" "needs-design"

create_issue "$MS_07" \
  "feat: implement webhook support for external integrations" \
  "## Summary
Notify external systems of document events via webhooks.

## Acceptance Criteria
- [ ] Config: URL, events, secret for HMAC signature
- [ ] CRUD API and management UI
- [ ] Events: document.uploaded, document.processed, document.failed, pipeline.completed
- [ ] HMAC-SHA256 signature (X-DocuElevate-Signature header)
- [ ] Retry with backoff (3 attempts)
- [ ] Delivery log with status/response

## API
\`\`\`
POST /api/webhooks { url, events, secret }
GET  /api/webhooks
GET  /api/webhooks/{id}/deliveries
\`\`\`

## Agent Notes
Commit: \`feat: add webhook support for document events\`" \
  "enhancement" "priority: high" "agentic-ready" "area: api"

create_issue "$MS_07" \
  "feat: add rule-based document classification" \
  "## Summary
Auto-classify documents (invoice, contract, receipt, etc.) using rules + AI.

## Acceptance Criteria
- [ ] Rules: filename patterns, keywords, metadata, AI inference
- [ ] Pre-built + custom categories
- [ ] Runs as pipeline step
- [ ] Results stored as metadata with confidence score
- [ ] Manual override
- [ ] Accuracy dashboard

## Depends On
- Pipeline engine

## Agent Notes
Commit: \`feat: add rule-based document classification\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: backend" "area: ai"

create_issue "$MS_07" \
  "feat: implement scheduled batch processing" \
  "## Summary
Schedule processing jobs at specific times or intervals.

## Acceptance Criteria
- [ ] Cron or interval scheduling
- [ ] Jobs: process new docs, reprocess failed, cleanup temps
- [ ] Schedule management UI
- [ ] Execution history
- [ ] Manual trigger for any job
- [ ] Timezone-aware

## Implementation Notes
- Celery Beat with database scheduler

## Agent Notes
Commit: \`feat: add scheduled batch processing\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: backend"

create_issue "$MS_07" \
  "feat: add retry logic with exponential backoff for failed tasks" \
  "## Summary
Failed tasks auto-retry with backoff instead of permanently failing.

## Acceptance Criteria
- [ ] Configurable retry policy per task type
- [ ] Exponential backoff with jitter
- [ ] Retryable vs permanent failure distinction
- [ ] Retry count in document detail view
- [ ] Manual retry for permanent failures
- [ ] Default: 3 retries at 60s, 300s, 900s

## Implementation Notes
- Celery autoretry_for, retry_backoff, retry_jitter
- Permanent: invalid format, auth errors
- Retryable: network timeout, rate limit

## Files
- \`app/tasks/\`, \`app/celery_worker.py\`

## Agent Notes
Commit: \`feat: add task retry with exponential backoff\`" \
  "enhancement" "priority: high" "agentic-ready" "area: backend"

create_issue "$MS_07" \
  "feat: build notification system (email, webhook, in-app)" \
  "## Summary
Notify users via email, webhook, or in-app (bell icon).

## Acceptance Criteria
- [ ] Channels: email (SMTP), webhook, in-app
- [ ] Events: processing complete/failed, batch complete, system alerts
- [ ] Per-user preferences
- [ ] In-app center with read/unread
- [ ] WebSocket for real-time
- [ ] Preference management UI

## Implementation Notes
- Celery for async delivery
- Model: NotificationPreference(user_id, event, channel, enabled)

## Agent Notes
Commit: \`feat: add notification system\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: backend" "area: frontend" "needs-design"

# ────────────────────────────────────────
# v0.8.0 — Advanced AI & Multi-language
# ────────────────────────────────────────
echo ""
echo "  >>> v0.8.0 — Advanced AI & Multi-language <<<"
echo ""

create_issue "$MS_08" \
  "feat: build pluggable AI model provider abstraction layer" \
  "## Summary
Abstract AI services so the platform isn't locked to OpenAI.

## Acceptance Criteria
- [ ] Abstract AIProvider base class
- [ ] Implementations: OpenAI, Azure OpenAI, Anthropic Claude
- [ ] Provider selection via config
- [ ] Consistent response format
- [ ] Health check and fallback
- [ ] Configurable per pipeline step
- [ ] Settings UI for provider config

## Interface
\`\`\`python
class AIProvider(ABC):
    async def extract_metadata(self, text, schema) -> dict
    async def classify_document(self, text, categories) -> Classification
    async def summarize(self, text, max_length) -> str
    async def health_check(self) -> bool
\`\`\`

## Implementation Notes
- Follow storage provider pattern
- Factory pattern for instantiation
- Graceful fallback on failure

## Agent Notes
FOUNDATIONAL for v0.8.0. Commit: \`feat: add pluggable AI model provider layer\`" \
  "enhancement" "priority: critical" "agentic-ready" "area: ai" "area: backend" "needs-design"

create_issue "$MS_08" \
  "feat: add multi-language OCR support" \
  "## Summary
OCR in 20+ languages with auto language detection.

## Acceptance Criteria
- [ ] 20+ languages (EN, DE, FR, ES, IT, PT, NL, PL, RU, ZH, JA, KO, AR...)
- [ ] Auto language detection
- [ ] Manual override per document/pipeline
- [ ] Language config in settings
- [ ] Multi-language document support

## Implementation Notes
- Azure Doc Intelligence supports multi-language
- Add detection step (langdetect or lingua)
- Store detected language as metadata

## Depends On
- AI provider abstraction

## Agent Notes
Commit: \`feat: add multi-language OCR support\`" \
  "enhancement" "priority: high" "agentic-ready" "area: ai"

create_issue "$MS_08" \
  "feat: implement document similarity detection" \
  "## Summary
Detect similar documents using embeddings and cosine similarity.

## Acceptance Criteria
- [ ] Similarity scoring (0-1)
- [ ] Similar documents section on detail page
- [ ] Based on: text, metadata, structure
- [ ] Configurable threshold
- [ ] Batch analysis for corpus
- [ ] API: \`GET /api/files/{id}/similar\`

## Implementation Notes
- Text embeddings (OpenAI or sentence-transformers)
- Store in pgvector or vector store
- LSH for large-scale
- Background indexing after processing

## Agent Notes
Commit: \`feat: add document similarity detection\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: ai" "area: backend"

create_issue "$MS_08" \
  "feat: add duplicate document detection and management" \
  "## Summary
Detect and flag exact + near-duplicate documents.

## Acceptance Criteria
- [ ] Exact duplicates via SHA-256 hash
- [ ] Near-duplicates via content similarity
- [ ] Warning on upload
- [ ] Management UI (view groups, merge, delete)
- [ ] API: \`POST /api/files/check-duplicate\`
- [ ] Configurable: warn, block, auto-merge

## Depends On
- Document similarity detection

## Agent Notes
Commit: \`feat: add duplicate document detection\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: backend" "area: ai"

create_issue "$MS_08" \
  "feat: implement UI internationalization (i18n) for 10+ languages" \
  "## Summary
Translate the web UI into multiple languages.

## Acceptance Criteria
- [ ] i18n framework in templates
- [ ] Language selector in nav/settings
- [ ] All UI text in translation files
- [ ] Languages: EN, DE, FR, ES, IT, PT, NL, PL, RU, ZH
- [ ] Per-user pref + browser auto-detect
- [ ] Date/number locale formatting

## Implementation Notes
- Backend: Babel
- Frontend: Jinja2 gettext or JS i18n
- .po/.mo or JSON translation files

## Agent Notes
Commit: \`feat: add UI internationalization\`" \
  "enhancement" "ui/ux" "priority: medium" "agentic-ready" "area: frontend" "needs-design"

create_issue "$MS_08" \
  "feat: add API response localization" \
  "## Summary
API errors/status localized via Accept-Language header.

## Acceptance Criteria
- [ ] Respects Accept-Language
- [ ] Error messages localized
- [ ] Fallback to English
- [ ] OpenAPI docs updated

## Depends On
- UI i18n

## Agent Notes
Commit: \`feat: add API response localization\`" \
  "enhancement" "priority: low" "agentic-ready" "area: api"

# ────────────────────────────────────────
# v1.0.0 — Enterprise Edition
# ────────────────────────────────────────
echo ""
echo "  >>> v1.0.0 — Enterprise Edition <<<"
echo ""

create_issue "$MS_10" \
  "feat!: implement multi-tenancy with organization and team management" \
  "## Summary
Multi-tenancy so multiple orgs share one instance with full data isolation.

## Acceptance Criteria
- [ ] Organization model (CRUD)
- [ ] Team management within orgs
- [ ] User in one or more orgs
- [ ] Complete data isolation (docs, settings, pipelines)
- [ ] Tenant-scoped DB queries (no leakage)
- [ ] Per-tenant quotas and config
- [ ] Org admin panel
- [ ] Tenant context in all API requests
- [ ] Migration path from single-tenant

## Breaking Changes
- DB schema: tenant_id FK on all tables
- API: tenant context required

## Implementation Notes
- Shared DB with tenant_id approach
- Middleware for tenant context
- SQLAlchemy filters for isolation
- Superadmin for cross-tenant

## Agent Notes
BUILD FIRST for v1.0.0. Commit: \`feat!: add multi-tenancy\`. BREAKING CHANGE." \
  "enhancement" "priority: critical" "breaking-change" "needs-design" "area: backend"

create_issue "$MS_10" \
  "feat!: implement role-based access control (RBAC)" \
  "## Summary
Granular RBAC with configurable permissions per role.

## Acceptance Criteria
- [ ] Default roles: Admin, Manager, User, Viewer
- [ ] Custom roles with granular permissions
- [ ] Permissions: docs CRUD, pipelines CRUD, settings R/W, users manage, reports view
- [ ] Role per user per org
- [ ] Permission checks on all endpoints
- [ ] Permission-aware UI
- [ ] Audit log for changes

## Depends On
- Multi-tenancy

## Agent Notes
Commit: \`feat!: add RBAC\`. BREAKING CHANGE." \
  "enhancement" "priority: critical" "breaking-change" "needs-design" "area: backend" "area: api"

create_issue "$MS_10" \
  "feat: add horizontal scaling support" \
  "## Summary
Stateless app servers + distributed workers behind load balancer.

## Acceptance Criteria
- [ ] Fully stateless app
- [ ] Sessions in Redis
- [ ] Uploads to shared storage
- [ ] Independent worker scaling
- [ ] DB connection pooling
- [ ] /health endpoint
- [ ] Multi-replica Docker Compose
- [ ] Kubernetes manifest

## Agent Notes
Commit: \`feat: add horizontal scaling support\`" \
  "enhancement" "priority: high" "area: infrastructure" "needs-design"

create_issue "$MS_10" \
  "feat: add comprehensive audit logging with tamper detection" \
  "## Summary
Log all significant actions for compliance.

## Acceptance Criteria
- [ ] Events: login/logout, doc CRUD, settings, permissions, API keys
- [ ] Fields: timestamp, user, action, resource, details, IP, tenant
- [ ] Append-only storage
- [ ] Viewer UI with filter and export
- [ ] API for queries
- [ ] Configurable retention
- [ ] Optional hash chain

## Agent Notes
Commit: \`feat: add audit logging\`" \
  "enhancement" "security" "priority: high" "area: backend"

create_issue "$MS_10" \
  "feat: add SharePoint integration for document storage" \
  "## Summary
SharePoint as storage provider.

## Acceptance Criteria
- [ ] SharePoint Online auth via Graph API
- [ ] Upload to configurable library
- [ ] Download from SharePoint
- [ ] Folder mapping
- [ ] Metadata sync
- [ ] Settings UI

## Implementation Notes
- Microsoft Graph API, MSAL for auth
- Follow existing provider pattern

## Agent Notes
Commit: \`feat: add SharePoint integration\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: backend"

create_issue "$MS_10" \
  "feat: add Slack and Microsoft Teams bot integration" \
  "## Summary
Chat bots for upload, status, notifications.

## Acceptance Criteria
- [ ] Slack bot: upload via DM, status, notifications
- [ ] Teams bot: same
- [ ] Commands: upload, status, search, help
- [ ] File upload through chat
- [ ] Channel notifications
- [ ] Bot config in settings

## Agent Notes
Commit: \`feat: add Slack and Teams bots\`" \
  "enhancement" "priority: medium" "needs-design" "area: backend"

create_issue "$MS_10" \
  "feat: add Zapier and Make.com integration" \
  "## Summary
Trigger Zapier/Make.com workflows and accept incoming triggers.

## Acceptance Criteria
- [ ] Outgoing triggers via webhooks
- [ ] Incoming actions
- [ ] Zapier-compatible format
- [ ] Auth for incoming
- [ ] Setup docs

## Depends On
- Webhooks (v0.7.0)

## Agent Notes
Commit: \`feat: add Zapier/Make.com integration\`" \
  "enhancement" "priority: low" "area: api"

create_issue "$MS_10" \
  "feat: add GraphQL API alongside REST" \
  "## Summary
GraphQL for flexible data querying.

## Acceptance Criteria
- [ ] /graphql endpoint
- [ ] Schema: docs, pipelines, settings, users, audit
- [ ] Queries, mutations, subscriptions
- [ ] Auth integrated
- [ ] GraphiQL in dev mode
- [ ] Rate limit by complexity

## Implementation Notes
- Strawberry or Ariadne
- Share logic with REST
- Dataloader for N+1

## Agent Notes
Commit: \`feat: add GraphQL API\`" \
  "enhancement" "priority: medium" "needs-design" "area: api"

create_issue "$MS_10" \
  "feat: add document sharing with expiring links" \
  "## Summary
Share documents via time/view-limited links.

## Acceptance Criteria
- [ ] Generate shareable link
- [ ] Expiration: time (1h-30d) or view-count
- [ ] Optional password
- [ ] Management UI (view, revoke)
- [ ] API: POST /api/files/{id}/share, GET /api/shared/{token}
- [ ] Clean read-only viewer
- [ ] Audit log per access

## Agent Notes
Commit: \`feat: add document sharing\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: api" "area: frontend"

create_issue "$MS_10" \
  "feat: add document comments and annotations" \
  "## Summary
Threaded comments and PDF annotations.

## Acceptance Criteria
- [ ] Threaded comments on docs
- [ ] Text annotations on PDF pages
- [ ] @mention with notifications
- [ ] Resolution workflow
- [ ] History/edit tracking
- [ ] CRUD API
- [ ] Real-time via WebSocket

## Depends On
- Multi-tenancy + RBAC

## Agent Notes
Commit: \`feat: add comments and annotations\`" \
  "enhancement" "priority: low" "needs-design" "area: frontend" "area: api"

create_issue "$MS_10" \
  "feat: add document version history with diff" \
  "## Summary
Track versions, compare, restore.

## Acceptance Criteria
- [ ] Version on: re-upload, reprocess, metadata edit
- [ ] Version list on detail page
- [ ] Download any version
- [ ] Side-by-side text diff
- [ ] Metadata change history
- [ ] Restore previous version

## Agent Notes
Commit: \`feat: add version history\`" \
  "enhancement" "priority: low" "needs-design" "area: backend" "area: frontend"

create_issue "$MS_10" \
  "feat: build reporting and analytics dashboard" \
  "## Summary
Analytics on processing, storage, AI costs, health.

## Acceptance Criteria
- [ ] Dashboard: docs processed, storage used, AI costs
- [ ] Stats: success rate, avg time, failures
- [ ] Storage per-provider, trends
- [ ] AI confidence distribution
- [ ] Export CSV/PDF
- [ ] Filter by date, type, pipeline

## Implementation Notes
- Celery periodic task for aggregation
- Chart.js frontend

## Agent Notes
Commit: \`feat: add analytics dashboard\`" \
  "enhancement" "priority: medium" "needs-design" "area: frontend" "area: backend"

create_issue "$MS_10" \
  "feat: add SLA monitoring and alerting" \
  "## Summary
Monitor SLAs and alert on breaches.

## Acceptance Criteria
- [ ] Thresholds: max processing time, max queue, min success rate
- [ ] Alerts: email, webhook, in-app
- [ ] SLA dashboard
- [ ] Historical reporting
- [ ] Escalation (warn -> critical)

## Depends On
- Notifications (v0.7.0), Analytics

## Agent Notes
Commit: \`feat: add SLA monitoring\`" \
  "enhancement" "priority: low" "area: backend" "area: infrastructure"

# ────────────────────────────────────────
# v2.0.0 — Platform Expansion
# ────────────────────────────────────────
echo ""
echo "  >>> v2.0.0 — Platform Expansion <<<"
echo ""

create_issue "$MS_20" \
  "feat: add self-hosted OCR engine support (Tesseract, EasyOCR)" \
  "## Summary
Self-hosted OCR as alternative to Azure.

## Acceptance Criteria
- [ ] Tesseract OCR integration
- [ ] EasyOCR integration
- [ ] Provider selection via config
- [ ] Comparable output format to Azure
- [ ] Performance benchmarks
- [ ] Docker image with engines
- [ ] GPU acceleration (EasyOCR)

## Agent Notes
Commit: \`feat: add self-hosted OCR support\`" \
  "enhancement" "priority: high" "area: ai" "area: infrastructure"

create_issue "$MS_20" \
  "feat: add local LLM support (Ollama, LLaMA)" \
  "## Summary
Local LLMs as alternative to OpenAI.

## Acceptance Criteria
- [ ] Ollama integration
- [ ] LLaMA, Mistral support
- [ ] Provider selection via config
- [ ] Prompt templates for local models
- [ ] Quality comparison vs OpenAI
- [ ] GPU acceleration
- [ ] Model management UI

## Implementation Notes
- Ollama API is OpenAI-compatible

## Agent Notes
Commit: \`feat: add local LLM support\`" \
  "enhancement" "priority: high" "area: ai"

create_issue "$MS_20" \
  "feat: build desktop application (Electron)" \
  "## Summary
Desktop app for Windows, macOS, Linux.

## Acceptance Criteria
- [ ] Electron app connecting to server
- [ ] Native file drag-and-drop
- [ ] System tray with notifications
- [ ] Watch folder (auto-upload)
- [ ] Offline viewing
- [ ] Auto-update
- [ ] Windows, macOS, Linux builds

## Agent Notes
Commit: \`feat: add desktop application\`" \
  "enhancement" "priority: medium" "needs-design" "area: frontend"

create_issue "$MS_20" \
  "feat: build mobile apps (iOS and Android)" \
  "## Summary
Native mobile apps.

## Acceptance Criteria
- [ ] iOS and Android (React Native or Flutter)
- [ ] Camera capture to upload
- [ ] Document viewing and search
- [ ] Push notifications
- [ ] Offline cache
- [ ] Biometric auth

## Agent Notes
Commit: \`feat: add mobile apps\`" \
  "enhancement" "priority: medium" "needs-design" "area: frontend"

create_issue "$MS_20" \
  "feat: build CLI tool for power users" \
  "## Summary
Command-line tool for scripting.

## Acceptance Criteria
- [ ] Commands: upload, download, search, list, status, config
- [ ] Batch operations via globs
- [ ] Pipe-friendly output (JSON, CSV, plain)
- [ ] Auth via API key or OAuth device flow
- [ ] Tab completion (bash, zsh, fish)
- [ ] Published to PyPI

## Agent Notes
Commit: \`feat: add CLI tool\`" \
  "enhancement" "priority: medium" "agentic-ready" "area: api"

create_issue "$MS_20" \
  "feat: add browser extension for web clipping" \
  "## Summary
Clip web pages and send to DocuElevate.

## Acceptance Criteria
- [ ] Chrome and Firefox
- [ ] Clip full page, selection, or screenshot
- [ ] Convert to PDF
- [ ] Quick metadata tagging
- [ ] Auth with DocuElevate instance

## Agent Notes
Commit: \`feat: add browser extension\`" \
  "enhancement" "priority: low" "needs-design" "area: frontend"

create_issue "$MS_20" \
  "feat: implement document lifecycle management and retention policies" \
  "## Summary
Manage lifecycle: active, archived, deleted.

## Acceptance Criteria
- [ ] Stages: active, archived, pending-deletion, deleted
- [ ] Retention policies per type/category
- [ ] Auto-archive after period
- [ ] Auto-delete after retention
- [ ] Legal hold
- [ ] Policy management UI
- [ ] Compliance reporting

## Agent Notes
Commit: \`feat: add lifecycle management\`" \
  "enhancement" "priority: medium" "needs-design" "area: backend"

create_issue "$MS_20" \
  "feat: add compliance templates (GDPR, HIPAA, SOC2)" \
  "## Summary
Pre-built compliance configurations.

## Acceptance Criteria
- [ ] GDPR: retention, right to deletion, export, audit
- [ ] HIPAA: access controls, encryption, audit trail
- [ ] SOC2: monitoring, incident response, access
- [ ] One-click template apply
- [ ] Compliance dashboard
- [ ] Gap analysis report

## Depends On
- Multi-tenancy, RBAC, audit logging, lifecycle management

## Agent Notes
Commit: \`feat: add compliance templates\`" \
  "enhancement" "priority: medium" "needs-design" "area: backend"

create_issue "$MS_20" \
  "feat: build plugin system and marketplace" \
  "## Summary
Extensible plugin architecture.

## Acceptance Criteria
- [ ] Plugin API with hooks and extension points
- [ ] Types: storage, AI, pipeline steps, UI widgets
- [ ] Packaging and installation format
- [ ] Sandboxing (resources, permissions)
- [ ] Marketplace UI (browse, install, configure)
- [ ] Developer docs and SDK

## Agent Notes
Commit: \`feat: add plugin system\`" \
  "enhancement" "priority: low" "needs-design" "area: backend" "area: api"

# ══════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════
echo ""
echo "============================================="
echo "  Setup Complete!"
echo "============================================="
echo ""
echo "Created: $ISSUE_COUNT issues, Failed: $ISSUE_FAIL"
echo ""
echo "Milestone status:"
gh api "repos/$REPO/milestones" --jq '.[] | "  \(.title): \(.open_issues) open issues"' 2>/dev/null
echo ""
echo "  https://github.com/$REPO/milestones"
echo "  https://github.com/$REPO/issues"
echo ""
