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

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }

# ──────────────────────────────────────────────
# Verify prerequisites
# ──────────────────────────────────────────────
echo ""
echo "============================================="
echo "  DocuElevate GitHub Project Setup"
echo "============================================="
echo ""

if ! command -v gh &> /dev/null; then
    err "gh CLI not found. Install from https://cli.github.com/"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    err "Not authenticated. Run: gh auth login"
    exit 1
fi

# Verify repo access
if ! gh api "repos/$REPO" --jq '.full_name' &> /dev/null; then
    err "Cannot access $REPO. Check your permissions."
    exit 1
fi

log "Authenticated and repo accessible: $REPO"
echo ""

# Helper: create label (skip if exists)
create_label() {
    local name="$1" color="$2" desc="$3"
    if gh api "repos/$REPO/labels/$( echo "$name" | sed 's/ /%20/g' )" &> /dev/null; then
        info "Label '$name' already exists, skipping"
    else
        if [ "$DRY_RUN" = "true" ]; then
            info "[DRY RUN] Would create label: $name"
        else
            gh api "repos/$REPO/labels" -f name="$name" -f color="$color" -f description="$desc" --silent 2>/dev/null && \
                log "Created label: $name" || warn "Failed to create label: $name"
        fi
    fi
}

# Helper: create milestone (skip if exists, return milestone number)
create_milestone() {
    local title="$1" due="$2" desc="$3"
    local existing
    existing=$(gh api "repos/$REPO/milestones?state=all&per_page=100" --jq ".[] | select(.title==\"$title\") | .number" 2>/dev/null)
    if [ -n "$existing" ]; then
        info "Milestone '$title' already exists (#$existing), skipping"
        echo "$existing"
    else
        if [ "$DRY_RUN" = "true" ]; then
            info "[DRY RUN] Would create milestone: $title"
            echo "0"
        else
            gh api "repos/$REPO/milestones" \
                -f title="$title" \
                -f state="open" \
                -f due_on="$due" \
                -f description="$desc" \
                --jq '.number' 2>/dev/null && log "Created milestone: $title" || { warn "Failed to create milestone: $title"; echo "0"; }
        fi
    fi
}

# Helper: create issue with labels and milestone
create_issue() {
    local title="$1" body="$2" milestone="$3"
    shift 3
    local labels=("$@")

    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY RUN] Would create issue: $title (milestone=$milestone, labels=${labels[*]})"
        return
    fi

    local label_args=""
    for label in "${labels[@]}"; do
        label_args="$label_args -f labels[]=$label"
    done

    local num
    num=$(gh issue create --repo "$REPO" \
        --title "$title" \
        --body "$body" \
        --milestone "$milestone" \
        $label_args \
        2>&1 | grep -oP '/issues/\K[0-9]+' || echo "")

    if [ -n "$num" ]; then
        log "Created issue #$num: $title"
    else
        warn "Issue may have been created (check repo): $title"
    fi

    # Small delay to avoid rate limiting
    sleep 0.5
}

# ══════════════════════════════════════════════
# PHASE 1: LABELS
# ══════════════════════════════════════════════
echo "─────────────────────────────────────────────"
echo "  Phase 1: Creating Labels"
echo "─────────────────────────────────────────────"
echo ""

create_label "security"           "e11d48" "Security hardening and vulnerability fixes"
create_label "testing"            "0e8a16" "Test coverage and quality improvements"
create_label "refactor"           "d4c5f9" "Code refactoring and cleanup"
create_label "ci/cd"              "fbca04" "CI/CD pipeline improvements"
create_label "ui/ux"              "7057ff" "UI/UX improvements and frontend work"
create_label "performance"        "f9d0c4" "Performance optimization"
create_label "area: api"          "c2e0c6" "REST API related"
create_label "area: frontend"     "bfdadc" "Frontend and UI related"
create_label "area: backend"      "d4e5f7" "Backend and core logic"
create_label "area: ai"           "ff6f61" "AI/ML and document intelligence"
create_label "area: infrastructure" "fef2c0" "Infrastructure, Docker, deployment"
create_label "priority: critical" "b60205" "Must fix immediately"
create_label "priority: high"     "d93f0b" "Important for next release"
create_label "priority: medium"   "fbca04" "Should be addressed soon"
create_label "priority: low"      "0e8a16" "Nice to have, backlog"
create_label "agentic-ready"      "1d76db" "Well-defined for autonomous agent work"
create_label "breaking-change"    "e11d48" "Introduces breaking API or behavior changes"
create_label "needs-design"       "d876e3" "Requires design decisions before implementation"

echo ""

# ══════════════════════════════════════════════
# PHASE 2: MILESTONES
# ══════════════════════════════════════════════
echo "─────────────────────────────────────────────"
echo "  Phase 2: Creating Milestones"
echo "─────────────────────────────────────────────"
echo ""

MS_05x=$(create_milestone "v0.5.x - Quality & Stability" "2026-03-31T23:59:59Z" \
"Theme: Security hardening, test coverage, code quality, and bug fixes.

Goals:
- Achieve 60%+ code coverage (currently ~48%)
- Complete security hardening (rate limiting, CSRF, audit logging, input validation)
- Enforce strict linting and type checking
- Fix known high-priority bugs
- Improve documentation

Release Strategy: Multiple patch releases (v0.5.1, v0.5.2, etc.) via semantic-release.
Agent Instructions: Issues are well-scoped for autonomous work. Use conventional commits (fix:, test:, refactor:, docs:).")

MS_06=$(create_milestone "v0.6.0 - Enhanced Search & UI" "2026-04-30T23:59:59Z" \
"Theme: Full-text search, advanced filtering, mobile responsiveness, dark mode, document preview.

Goals:
- Implement full-text search across documents and metadata
- Add advanced filtering, sorting, and saved searches
- Make UI fully responsive for mobile
- Add dark mode and in-browser document preview

Breaking Changes: API response format changes for search endpoints.
Release Strategy: Minor release triggered by feat: commits.")

MS_07=$(create_milestone "v0.7.0 - Workflow Automation" "2026-06-30T23:59:59Z" \
"Theme: Custom processing pipelines, conditional routing, webhooks, scheduled processing.

Goals:
- Build pipeline engine for custom document workflows
- Conditional routing based on document type/metadata
- Webhook support for external integrations
- Scheduled batch processing and retry logic

Release Strategy: Minor release. Pipeline engine is the foundational dependency.")

MS_08=$(create_milestone "v0.8.0 - Advanced AI & Multi-language" "2026-08-31T23:59:59Z" \
"Theme: Pluggable AI models, multi-language OCR, document intelligence, i18n.

Goals:
- Pluggable AI provider abstraction (not locked to OpenAI)
- Multi-language OCR support
- Document similarity and duplicate detection
- UI internationalization (10+ languages)

Release Strategy: Minor release. AI abstraction layer is the foundational dependency.")

MS_10=$(create_milestone "v1.0.0 - Enterprise Edition" "2026-11-30T23:59:59Z" \
"Theme: Multi-tenancy, RBAC, horizontal scaling, enterprise integrations.

Goals:
- Multi-tenancy with organization management
- Role-based access control (RBAC)
- Horizontal scaling support
- Enterprise integrations (SharePoint, Slack/Teams, Zapier)
- GraphQL API, collaboration features, analytics

BREAKING CHANGES: Database schema changes, API auth changes.
Release Strategy: Major release. Multi-tenancy must be implemented first.")

MS_20=$(create_milestone "v2.0.0 - Platform Expansion" "2027-09-30T23:59:59Z" \
"Theme: Self-hosted AI, desktop/mobile apps, compliance, plugin ecosystem.

Goals:
- Self-hosted OCR and local LLM support
- Desktop (Electron) and mobile apps
- CLI tool and browser extension
- Compliance templates (GDPR, HIPAA, SOC2)
- Plugin system and marketplace

Release Strategy: Major release. Long-term strategic vision.")

echo ""
info "Milestone numbers: v0.5.x=$MS_05x, v0.6.0=$MS_06, v0.7.0=$MS_07, v0.8.0=$MS_08, v1.0.0=$MS_10, v2.0.0=$MS_20"
echo ""

# ══════════════════════════════════════════════
# PHASE 3: ASSIGN EXISTING ISSUES TO MILESTONES
# ══════════════════════════════════════════════
echo "─────────────────────────────────────────────"
echo "  Phase 3: Assigning Existing Open Issues"
echo "─────────────────────────────────────────────"
echo ""

assign_to_milestone() {
    local issue="$1" milestone="$2"
    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY RUN] Would assign #$issue to milestone $milestone"
    else
        gh api "repos/$REPO/issues/$issue" -X PATCH --field milestone="$milestone" --silent 2>/dev/null && \
            log "Assigned #$issue to milestone $milestone" || warn "Failed to assign #$issue"
    fi
}

# These existing open issues belong to v0.5.x (Quality & Stability)
for issue in 92 94 95 96 161 164 165 168 169 170 171 172 173 174 175 176; do
    assign_to_milestone "$issue" "$MS_05x"
done

# Add labels to existing issues
add_labels() {
    local issue="$1"
    shift
    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY RUN] Would add labels to #$issue: $*"
    else
        local json_labels
        json_labels=$(printf '"%s",' "$@" | sed 's/,$//')
        gh api "repos/$REPO/issues/$issue/labels" -X POST --input - <<< "{\"labels\":[$json_labels]}" --silent 2>/dev/null && \
            log "Labeled #$issue" || warn "Failed to label #$issue"
    fi
}

add_labels 92  "security" "priority: high" "agentic-ready" "area: api"
add_labels 94  "security" "priority: critical" "agentic-ready" "area: backend"
add_labels 95  "security" "priority: high" "agentic-ready" "area: api"
add_labels 96  "testing" "priority: high" "agentic-ready" "area: api"
add_labels 161 "testing" "priority: high" "agentic-ready"
add_labels 164 "refactor" "priority: medium" "agentic-ready" "area: backend"
add_labels 165 "ci/cd" "priority: medium" "agentic-ready"
add_labels 168 "security" "priority: high" "agentic-ready" "area: api"
add_labels 169 "security" "priority: medium" "agentic-ready" "area: api"
add_labels 170 "security" "priority: high" "agentic-ready" "area: backend"
add_labels 171 "security" "ci/cd" "priority: high" "agentic-ready"
add_labels 172 "security" "priority: high" "agentic-ready" "area: api"
add_labels 173 "security" "priority: medium" "agentic-ready" "area: api"
add_labels 174 "security" "priority: high" "agentic-ready" "area: api"
add_labels 175 "security" "priority: medium" "agentic-ready" "area: api"
add_labels 176 "testing" "priority: high" "agentic-ready"

echo ""

# ══════════════════════════════════════════════
# PHASE 4: CREATE NEW ISSUES
# ══════════════════════════════════════════════
echo "─────────────────────────────────────────────"
echo "  Phase 4: Creating New Issues"
echo "─────────────────────────────────────────────"
echo ""

# ────────────────────────────────────────
# v0.5.x — Quality & Stability
# ────────────────────────────────────────
echo ""
echo "  >>> v0.5.x — Quality & Stability <<<"
echo ""

MS="$MS_05x"

create_issue "test: achieve 60% code coverage across the project" \
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
"$MS" "testing" "priority: high" "agentic-ready" "area: backend"

create_issue "fix: resolve session timeout issues with Authentik OAuth" \
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
"$MS" "bug" "priority: high" "agentic-ready" "area: backend"

create_issue "fix: improve Redis connection pool handling and failure recovery" \
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
"$MS" "bug" "priority: high" "agentic-ready" "area: infrastructure"

create_issue "fix: handle large file uploads (>100MB) reliably" \
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
"$MS" "bug" "priority: high" "agentic-ready" "area: api"

create_issue "fix: correct timezone handling inconsistencies" \
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
"$MS" "bug" "priority: medium" "agentic-ready" "area: backend"

create_issue "refactor: enforce strict linting (Black, isort, Flake8)" \
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
"$MS" "refactor" "ci/cd" "priority: high" "agentic-ready"

create_issue "refactor: add comprehensive type hints to core modules" \
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
"$MS" "refactor" "priority: medium" "agentic-ready" "area: backend"

create_issue "refactor: break up large functions in main modules" \
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
Commit: \`refactor: extract helper functions from large modules\`. Run tests after every change." \
"$MS" "refactor" "priority: medium" "agentic-ready" "area: backend"

create_issue "docs: add architecture diagram to documentation" \
"## Summary
Add a visual architecture diagram showing component interactions.

## Acceptance Criteria
- [ ] Diagram (Mermaid or SVG) showing: Web UI → FastAPI → Celery → Redis → Workers → External Services
- [ ] Storage providers, AI services, auth flow all shown
- [ ] Added to README.md or \`docs/architecture.md\`

## Components to Include
FastAPI, Celery, Redis, PostgreSQL/SQLite, Dropbox, Google Drive, OneDrive, Nextcloud, S3, Paperless NGX, Azure Doc Intelligence, OpenAI, Gotenberg, Authentik

## Agent Notes
Commit: \`docs: add architecture diagram\`" \
"$MS" "documentation" "priority: medium" "agentic-ready"

create_issue "docs: document all environment variables with descriptions and defaults" \
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
"$MS" "documentation" "priority: medium" "agentic-ready"

create_issue "docs: add troubleshooting guide for common issues" \
"## Summary
Troubleshooting guide covering common deployment and operational issues.

## Acceptance Criteria
- [ ] Coverage: Docker startup, Redis failures, OAuth config, OCR failures, storage auth, Celery workers, large uploads, DB migrations
- [ ] Each issue has: symptom, likely cause, solution steps
- [ ] Added to README or \`docs/troubleshooting.md\`

## Agent Notes
Commit: \`docs: add troubleshooting guide\`" \
"$MS" "documentation" "priority: low" "agentic-ready"

# ────────────────────────────────────────
# v0.6.0 — Enhanced Search & UI
# ────────────────────────────────────────
echo ""
echo "  >>> v0.6.0 — Enhanced Search & UI <<<"
echo ""

MS="$MS_06"

create_issue "feat: implement full-text search across documents and metadata" \
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
- Design abstraction layer for future Elasticsearch/Meilisearch
- Add DB migration for search indexes

## API Design
\`\`\`
GET /api/search?q=invoice&type=pdf&date_from=2026-01-01&page=1&per_page=20
Response: { results: [...], total: 42, page: 1, pages: 3 }
\`\`\`

## Agent Notes
Foundational v0.6.0 feature. Commit: \`feat: add full-text search for documents\`" \
"$MS" "enhancement" "priority: high" "agentic-ready" "area: api" "area: backend" "breaking-change"

create_issue "feat: add advanced filtering and saved searches" \
"## Summary
Filter documents by multiple criteria; save frequently used filters.

## Acceptance Criteria
- [ ] Filter by: date range, file type, status, storage provider, tags
- [ ] Multiple filters combinable (AND logic)
- [ ] Sort by: date, name, size, status
- [ ] Save filter combos as 'saved searches' per user
- [ ] Filter state in URL (shareable links)
- [ ] API supports all filter params

## Depends On
- Full-text search implementation

## Agent Notes
Commit: \`feat: add advanced filtering and saved searches\`" \
"$MS" "enhancement" "priority: high" "agentic-ready" "area: api" "area: frontend"

create_issue "feat: implement responsive mobile interface" \
"## Summary
Make the UI fully responsive for phones and tablets.

## Acceptance Criteria
- [ ] All pages correct on 320px–1920px+ viewports
- [ ] Nav collapses to hamburger on small screens
- [ ] File list → card view on mobile
- [ ] Upload works on mobile (incl. camera capture)
- [ ] Touch-friendly targets (min 44px)
- [ ] No horizontal scrolling
- [ ] Tested: iOS Safari, Android Chrome, tablet

## Implementation Notes
- Tailwind responsive utilities (sm:, md:, lg:, xl:)
- Mobile-first approach for new components
- File table → card layout at \`md\` (768px)

## Agent Notes
Commit: \`feat: add responsive mobile interface\`" \
"$MS" "enhancement" "ui/ux" "priority: high" "agentic-ready" "area: frontend"

create_issue "feat: add dark mode support" \
"## Summary
Dark/light mode toggle with system preference detection.

## Acceptance Criteria
- [ ] Toggle in navbar
- [ ] System preference detection (\`prefers-color-scheme\`)
- [ ] Preference persisted (localStorage + DB setting)
- [ ] All pages styled in both modes
- [ ] WCAG AA contrast compliance
- [ ] Smooth transition animation

## Implementation Notes
- Tailwind \`darkMode: 'class'\` strategy
- \`dark:\` variants on all color utilities
- JS: detect system pref → check localStorage → apply class

## Agent Notes
Commit: \`feat: add dark mode support\`" \
"$MS" "enhancement" "ui/ux" "priority: medium" "agentic-ready" "area: frontend"

create_issue "feat: add in-browser document preview" \
"## Summary
Preview PDFs, images, and text files in-browser without downloading.

## Acceptance Criteria
- [ ] PDF preview (pdf.js or native)
- [ ] Image preview (JPEG, PNG, TIFF, WebP) with zoom/pan
- [ ] Text file preview with syntax highlighting
- [ ] Preview in modal/side panel from file list
- [ ] Works for original and processed documents
- [ ] Fallback for unsupported types (download link)
- [ ] Streaming for large files

## API
\`GET /api/files/{id}/preview\`

## Agent Notes
Commit: \`feat: add in-browser document preview\`" \
"$MS" "enhancement" "ui/ux" "priority: high" "agentic-ready" "area: frontend" "area: api"

create_issue "feat: add bulk operations (select, delete, reprocess, download)" \
"## Summary
Select multiple files and perform bulk actions.

## Acceptance Criteria
- [ ] Checkbox selection (individual, all, page)
- [ ] Bulk delete with confirmation
- [ ] Bulk reprocess (re-run OCR/metadata)
- [ ] Bulk download as ZIP
- [ ] Bulk toolbar appears on selection
- [ ] Async via Celery for large batches

## API
\`\`\`
POST /api/files/bulk { action: \"delete\", file_ids: [...] }
POST /api/files/bulk { action: \"reprocess\", file_ids: [...] }
POST /api/files/bulk/download { file_ids: [...] } → ZIP stream
\`\`\`

## Agent Notes
Commit: \`feat: add bulk file operations\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: api" "area: frontend"

create_issue "feat: implement proper pagination for file list API" \
"## Summary
Server-side pagination with consistent API format.

## Acceptance Criteria
- [ ] Server-side pagination (default 25 per page)
- [ ] Response: \`page\`, \`per_page\`, \`total\`, \`pages\`, \`next\`, \`previous\`
- [ ] UI pagination controls
- [ ] URL reflects page state
- [ ] Consistent format across all list endpoints

## Breaking Changes
Wraps /api/files response in pagination envelope.

## Agent Notes
Commit: \`feat: add paginated file list API\`. Document breaking change." \
"$MS" "enhancement" "priority: high" "agentic-ready" "area: api" "breaking-change"

create_issue "feat: add file download endpoint" \
"## Summary
Direct download endpoint for original and processed files.

## Acceptance Criteria
- [ ] \`GET /api/files/{id}/download\` — processed file
- [ ] \`GET /api/files/{id}/download?version=original\` — original upload
- [ ] Proper Content-Disposition with original filename
- [ ] Streaming for large files
- [ ] Auth required
- [ ] Download button in UI

## Agent Notes
Commit: \`feat: add file download endpoint\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: api"

create_issue "perf: optimize database queries and add caching layer" \
"## Summary
Fix slow queries and add Redis caching for frequent data.

## Acceptance Criteria
- [ ] Fix N+1 queries in file list/detail views
- [ ] Add indexes for common query columns
- [ ] Redis caching for: settings, sessions, frequent API responses
- [ ] Cache invalidation on data changes
- [ ] /files with 1000+ docs loads in <1 second

## Implementation Notes
- SQLAlchemy \`selectinload\`/\`joinedload\` for eager loading
- Composite indexes for filter/sort combos
- Redis (already available) for app-level cache

## Agent Notes
Commit: \`perf: optimize database queries and add caching\`" \
"$MS" "performance" "priority: medium" "agentic-ready" "area: backend"

# ────────────────────────────────────────
# v0.7.0 — Workflow Automation
# ────────────────────────────────────────
echo ""
echo "  >>> v0.7.0 — Workflow Automation <<<"
echo ""

MS="$MS_07"

create_issue "feat: build custom processing pipeline engine" \
"## Summary
Pipeline engine for custom document processing workflows as ordered steps.

## Context
Currently all documents follow the same fixed path. Different types need different workflows.

## Acceptance Criteria
- [ ] Pipeline model: ordered steps with per-step config
- [ ] Built-in steps: OCR, metadata extraction, PDF conversion, cloud upload, classification
- [ ] Pipeline CRUD API and management UI
- [ ] Documents assignable to specific pipelines
- [ ] Default pipeline for unassigned documents
- [ ] Per-document step-level status tracking
- [ ] Failed steps retryable individually

## Data Model
\`\`\`
Pipeline: id, name, description, steps (JSON), is_default, created_at
PipelineStep: order, type, config (JSON), on_failure (skip|stop|retry)
PipelineExecution: document_id, pipeline_id, status, current_step, timestamps
\`\`\`

## Implementation Notes
- Foundational for v0.7.0 — build FIRST
- Use Celery chains/chords for step execution
- Steps pluggable via registry pattern
- Execution idempotent and resumable

## Agent Notes
Commit: \`feat: add custom processing pipeline engine\`. Build this FIRST." \
"$MS" "enhancement" "priority: critical" "agentic-ready" "area: backend" "needs-design"

create_issue "feat: add conditional routing based on document type and metadata" \
"## Summary
Pipelines branch based on document properties — invoices to one workflow, contracts to another.

## Acceptance Criteria
- [ ] Rules based on: file type, category, metadata fields, size, source
- [ ] Conditions: equals, contains, regex, greater/less than
- [ ] Multiple rules with AND/OR logic
- [ ] Default route for unmatched documents
- [ ] Routing decisions logged
- [ ] UI for creating/testing rules

## Depends On
- Pipeline engine

## Agent Notes
Commit: \`feat: add conditional document routing\`" \
"$MS" "enhancement" "priority: high" "agentic-ready" "area: backend" "needs-design"

create_issue "feat: implement webhook support for external integrations" \
"## Summary
Notify external systems of document events via configurable webhooks.

## Acceptance Criteria
- [ ] Webhook config: URL, events, secret for HMAC signature
- [ ] CRUD API and management UI
- [ ] Events: \`document.uploaded\`, \`document.processed\`, \`document.failed\`, \`pipeline.completed\`
- [ ] HMAC-SHA256 signature (\`X-DocuElevate-Signature\` header)
- [ ] Retry with backoff on failure (3 attempts)
- [ ] Delivery log with status/response codes

## API
\`\`\`
POST /api/webhooks { url, events: [...], secret }
GET /api/webhooks
GET /api/webhooks/{id}/deliveries
\`\`\`

## Agent Notes
Commit: \`feat: add webhook support for document events\`" \
"$MS" "enhancement" "priority: high" "agentic-ready" "area: api"

create_issue "feat: add rule-based document classification" \
"## Summary
Auto-classify documents (invoice, contract, receipt, etc.) using rules + AI.

## Acceptance Criteria
- [ ] Rules: filename patterns, content keywords, metadata, AI inference
- [ ] Pre-built categories + custom ones
- [ ] Runs as pipeline step
- [ ] Results stored as metadata
- [ ] Confidence score for AI classification
- [ ] Manual override
- [ ] Accuracy dashboard

## Implementation Notes
- Rule-based (fast, deterministic) + AI-based (flexible, probabilistic)
- Use existing OpenAI integration for AI classification

## Depends On
- Pipeline engine

## Agent Notes
Commit: \`feat: add rule-based document classification\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: backend" "area: ai"

create_issue "feat: implement scheduled batch processing" \
"## Summary
Schedule document processing jobs at specific times or intervals.

## Acceptance Criteria
- [ ] Cron or interval scheduling (hourly, daily, weekly)
- [ ] Jobs: process new docs, reprocess failed, cleanup temp files
- [ ] Schedule management UI
- [ ] Execution history with status
- [ ] Manual trigger for any job
- [ ] Timezone-aware scheduling

## Implementation Notes
- Celery Beat with database scheduler
- Monitor for missed/overdue tasks

## Agent Notes
Commit: \`feat: add scheduled batch processing\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: backend"

create_issue "feat: add retry logic with exponential backoff for failed tasks" \
"## Summary
Failed tasks auto-retry with configurable backoff instead of permanently failing.

## Acceptance Criteria
- [ ] Configurable retry policy per task type
- [ ] Exponential backoff with jitter
- [ ] Distinguish retryable vs permanent failures
- [ ] Retry count/history in document detail view
- [ ] Manual retry button for permanent failures
- [ ] Default: 3 retries at 60s, 300s, 900s

## Implementation Notes
- Celery \`autoretry_for\`, \`retry_backoff\`, \`retry_jitter\`
- Permanent: invalid format, auth errors
- Retryable: network timeout, rate limit, transient API errors

## Files
- \`app/tasks/\`, \`app/celery_worker.py\`

## Agent Notes
Commit: \`feat: add task retry with exponential backoff\`" \
"$MS" "enhancement" "priority: high" "agentic-ready" "area: backend"

create_issue "feat: build notification system (email, webhook, in-app)" \
"## Summary
Notify users of document events via email, webhook, or in-app notifications.

## Acceptance Criteria
- [ ] Channels: email (SMTP), webhook, in-app (bell icon)
- [ ] Events: processing complete/failed, batch complete, system alerts
- [ ] Per-user preferences (which channels for which events)
- [ ] In-app notification center with read/unread
- [ ] Email via configurable SMTP
- [ ] WebSocket for real-time in-app updates
- [ ] Preference management UI

## Implementation Notes
- WebSocket from frontend, notifications in DB
- Celery tasks for async delivery
- Preference model: \`NotificationPreference(user_id, event, channel, enabled)\`

## Agent Notes
Commit: \`feat: add notification system\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: backend" "area: frontend" "needs-design"

# ────────────────────────────────────────
# v0.8.0 — Advanced AI & Multi-language
# ────────────────────────────────────────
echo ""
echo "  >>> v0.8.0 — Advanced AI & Multi-language <<<"
echo ""

MS="$MS_08"

create_issue "feat: build pluggable AI model provider abstraction layer" \
"## Summary
Abstract AI services so the platform isn't locked to OpenAI. Support pluggable providers.

## Acceptance Criteria
- [ ] Abstract \`AIProvider\` base class
- [ ] Implementations: OpenAI (existing), Azure OpenAI, Anthropic Claude
- [ ] Provider selection via configuration
- [ ] Consistent response format regardless of provider
- [ ] Health check and fallback support
- [ ] Model configurable per pipeline step
- [ ] Settings UI for provider config

## Interface
\`\`\`python
class AIProvider(ABC):
    async def extract_metadata(self, text: str, schema: dict) -> dict
    async def classify_document(self, text: str, categories: list) -> Classification
    async def summarize(self, text: str, max_length: int) -> str
    async def health_check(self) -> bool
\`\`\`

## Implementation Notes
- Follow existing storage provider pattern
- Factory pattern for instantiation
- Graceful fallback on provider failure

## Agent Notes
Foundational for v0.8.0. Commit: \`feat: add pluggable AI model provider layer\`" \
"$MS" "enhancement" "priority: critical" "agentic-ready" "area: ai" "area: backend" "needs-design"

create_issue "feat: add multi-language OCR support" \
"## Summary
OCR in 20+ languages with automatic language detection.

## Acceptance Criteria
- [ ] 20+ languages (EN, DE, FR, ES, IT, PT, NL, PL, RU, ZH, JA, KO, AR, ...)
- [ ] Auto language detection
- [ ] Manual language override per document/pipeline
- [ ] Language config in settings
- [ ] OCR quality metrics per language
- [ ] Multi-language document support

## Implementation Notes
- Azure Doc Intelligence already supports multi-language — configure param
- Add detection step (\`langdetect\` or \`lingua\`)
- Store detected language as metadata

## Depends On
- AI provider abstraction

## Agent Notes
Commit: \`feat: add multi-language OCR support\`" \
"$MS" "enhancement" "priority: high" "agentic-ready" "area: ai"

create_issue "feat: implement document similarity detection" \
"## Summary
Detect similar documents using text embeddings and cosine similarity.

## Acceptance Criteria
- [ ] Similarity scoring (0–1 scale)
- [ ] 'Similar documents' section on detail page
- [ ] Based on: text content, metadata, structure
- [ ] Configurable threshold
- [ ] Batch analysis for entire corpus
- [ ] API: \`GET /api/files/{id}/similar\`

## Implementation Notes
- Text embeddings (OpenAI or sentence-transformers)
- Store embeddings (pgvector or vector store)
- Cosine similarity; LSH for large-scale
- Background indexing after processing

## Agent Notes
Commit: \`feat: add document similarity detection\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: ai" "area: backend"

create_issue "feat: add duplicate document detection and management" \
"## Summary
Detect and flag exact + near-duplicate documents.

## Acceptance Criteria
- [ ] Exact duplicates via SHA-256 hash
- [ ] Near-duplicates via content similarity
- [ ] Warning on upload (before processing)
- [ ] Duplicate management UI (view groups, merge, delete)
- [ ] API: \`POST /api/files/check-duplicate\`
- [ ] Configurable action: warn, block, auto-merge

## Implementation Notes
- Phase 1: hash comparison (fast)
- Phase 2: content similarity (uses similarity feature)

## Depends On
- Document similarity detection

## Agent Notes
Commit: \`feat: add duplicate document detection\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: backend" "area: ai"

create_issue "feat: implement UI internationalization (i18n) for 10+ languages" \
"## Summary
Translate the web UI into multiple languages.

## Acceptance Criteria
- [ ] i18n framework in templates
- [ ] Language selector in nav/settings
- [ ] All UI text in translation files
- [ ] Languages: EN, DE, FR, ES, IT, PT, NL, PL, RU, ZH (Simplified)
- [ ] Per-user preference + browser auto-detect
- [ ] Date/number/currency locale formatting

## Implementation Notes
- Backend: Babel for Python i18n
- Frontend: Jinja2 gettext or JS i18n library
- Extract all hardcoded strings
- \`.po\`/\`.mo\` or JSON translation files

## Agent Notes
Commit: \`feat: add UI internationalization (i18n)\`" \
"$MS" "enhancement" "ui/ux" "priority: medium" "agentic-ready" "area: frontend" "needs-design"

create_issue "feat: add API response localization" \
"## Summary
API errors and status messages localized via Accept-Language header.

## Acceptance Criteria
- [ ] API respects \`Accept-Language\` header
- [ ] Error messages in requested language
- [ ] Status descriptions localized
- [ ] Fallback to English
- [ ] OpenAPI docs updated

## Depends On
- UI i18n (shared translation infra)

## Agent Notes
Commit: \`feat: add API response localization\`" \
"$MS" "enhancement" "priority: low" "agentic-ready" "area: api"

# ────────────────────────────────────────
# v1.0.0 — Enterprise Edition
# ────────────────────────────────────────
echo ""
echo "  >>> v1.0.0 — Enterprise Edition <<<"
echo ""

MS="$MS_10"

create_issue "feat!: implement multi-tenancy with organization and team management" \
"## Summary
Multi-tenancy so multiple organizations share one DocuElevate instance with full data isolation.

## Acceptance Criteria
- [ ] Organization model (CRUD)
- [ ] Team management within orgs
- [ ] User belongs to one or more orgs
- [ ] Complete data isolation (documents, settings, pipelines)
- [ ] Tenant-scoped DB queries (no leakage)
- [ ] Per-tenant quotas and config
- [ ] Org admin panel
- [ ] Tenant context in all API requests
- [ ] Migration path for single-tenant → multi-tenant

## Breaking Changes
- DB schema: tenant_id FK on all tables
- API auth: tenant context required
- Data migration needed

## Implementation Notes
- Shared DB with tenant_id column approach
- Middleware for tenant context
- SQLAlchemy filters for isolation
- Superadmin for cross-tenant management

## Agent Notes
BUILD THIS FIRST for v1.0.0. Commit: \`feat!: add multi-tenancy support\`. BREAKING CHANGE." \
"$MS" "enhancement" "priority: critical" "breaking-change" "needs-design" "area: backend"

create_issue "feat!: implement role-based access control (RBAC)" \
"## Summary
Granular RBAC with configurable permissions per role.

## Acceptance Criteria
- [ ] Default roles: Admin, Manager, User, Viewer
- [ ] Custom role creation with granular permissions
- [ ] Permissions: documents CRUD, pipelines CRUD, settings R/W, users manage, reports view
- [ ] Role assignment per user per org
- [ ] Permission checks on all endpoints
- [ ] Permission-aware UI
- [ ] Audit log for permission changes

## Implementation Notes
- \`Role → Permission\` many-to-many
- Decorator/middleware for checks
- Integrate with Authentik OAuth groups
- Cache permissions in session

## Depends On
- Multi-tenancy

## Agent Notes
Commit: \`feat!: add role-based access control\`. BREAKING CHANGE." \
"$MS" "enhancement" "priority: critical" "breaking-change" "needs-design" "area: backend" "area: api"

create_issue "feat: add horizontal scaling support" \
"## Summary
Scale horizontally with stateless app servers and distributed workers.

## Acceptance Criteria
- [ ] Fully stateless app (no local FS for state)
- [ ] Session storage in Redis
- [ ] Uploads to shared storage (S3/NFS)
- [ ] Independent Celery worker scaling
- [ ] DB connection pooling configured
- [ ] Health check for load balancer (\`/health\`)
- [ ] Multi-replica Docker Compose config
- [ ] Kubernetes manifest (Helm or kustomize)

## Agent Notes
Commit: \`feat: add horizontal scaling support\`" \
"$MS" "enhancement" "priority: high" "area: infrastructure" "needs-design"

create_issue "feat: add comprehensive audit logging with tamper detection" \
"## Summary
Log all significant actions for compliance auditing.

## Acceptance Criteria
- [ ] Events: login/logout, document CRUD, settings changes, permission changes, API key usage
- [ ] Fields: timestamp, user, action, resource, details, IP, tenant
- [ ] Append-only storage
- [ ] Viewer UI with filtering and export
- [ ] API for queries
- [ ] Configurable retention policy
- [ ] Optional hash chain for tamper detection

## Agent Notes
Commit: \`feat: add comprehensive audit logging\`" \
"$MS" "enhancement" "security" "priority: high" "area: backend"

create_issue "feat: add SharePoint integration for document storage" \
"## Summary
Microsoft SharePoint as storage provider.

## Acceptance Criteria
- [ ] SharePoint Online auth via Microsoft Graph API
- [ ] Upload to configurable SharePoint library
- [ ] Download from SharePoint
- [ ] Folder mapping (categories → SharePoint folders)
- [ ] Metadata sync
- [ ] Settings UI config

## Implementation Notes
- Microsoft Graph API (not legacy REST)
- Follow existing provider pattern
- MSAL for auth

## Agent Notes
Commit: \`feat: add SharePoint storage integration\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: backend"

create_issue "feat: add Slack and Microsoft Teams bot integration" \
"## Summary
Chat bots for uploading docs, checking status, receiving notifications.

## Acceptance Criteria
- [ ] Slack bot: upload via DM, status queries, notifications
- [ ] Teams bot: same capabilities
- [ ] Commands: upload, status, search, help
- [ ] File upload through chat
- [ ] Notification delivery to configured channel
- [ ] Bot config in settings UI

## Implementation Notes
- Slack Bolt framework + Bot Framework SDK
- Shared command handler with platform adapters

## Agent Notes
Commit: \`feat: add Slack and Teams bot integration\`" \
"$MS" "enhancement" "priority: medium" "needs-design" "area: backend"

create_issue "feat: add Zapier and Make.com integration" \
"## Summary
Trigger Zapier/Make.com workflows from DocuElevate events and accept incoming triggers.

## Acceptance Criteria
- [ ] Outgoing triggers via webhooks
- [ ] Incoming actions (documents and commands)
- [ ] Zapier-compatible webhook format
- [ ] Auth for incoming (API key or OAuth)
- [ ] Setup documentation

## Depends On
- Webhook support (v0.7.0)

## Agent Notes
Commit: \`feat: add Zapier and Make.com integration\`" \
"$MS" "enhancement" "priority: low" "area: api"

create_issue "feat: add GraphQL API alongside REST" \
"## Summary
GraphQL endpoint for flexible data querying.

## Acceptance Criteria
- [ ] Endpoint at \`/graphql\`
- [ ] Schema: documents, pipelines, settings, users, audit logs
- [ ] Queries, mutations, subscriptions
- [ ] Auth/authz integrated
- [ ] GraphiQL playground (dev mode)
- [ ] Rate limiting by query complexity

## Implementation Notes
- Strawberry or Ariadne for Python
- Share business logic with REST (don't duplicate)
- Dataloader pattern for N+1

## Agent Notes
Commit: \`feat: add GraphQL API\`" \
"$MS" "enhancement" "priority: medium" "needs-design" "area: api"

create_issue "feat: add document sharing with expiring links" \
"## Summary
Share documents via time-limited or view-limited links.

## Acceptance Criteria
- [ ] Generate shareable link for any document
- [ ] Expiration: time-based (1h–30d) or view-count
- [ ] Optional password protection
- [ ] Management UI (view active, revoke)
- [ ] API: \`POST /api/files/{id}/share\`, \`GET /api/shared/{token}\`
- [ ] Clean read-only viewer for shared links
- [ ] Audit log entry per access

## Agent Notes
Commit: \`feat: add document sharing with expiring links\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: api" "area: frontend"

create_issue "feat: add document comments and annotations" \
"## Summary
Threaded comments and PDF annotations for collaboration.

## Acceptance Criteria
- [ ] Comments on documents (threaded)
- [ ] Text annotations on PDF pages/sections
- [ ] @mention users (with notifications)
- [ ] Comment resolution
- [ ] History and edit tracking
- [ ] CRUD API
- [ ] Real-time via WebSocket

## Depends On
- Multi-tenancy + RBAC

## Agent Notes
Commit: \`feat: add document comments and annotations\`" \
"$MS" "enhancement" "priority: low" "needs-design" "area: frontend" "area: api"

create_issue "feat: add document version history with diff" \
"## Summary
Track document versions and allow comparison.

## Acceptance Criteria
- [ ] Version on: re-upload, reprocess, metadata edit
- [ ] Version list on detail page
- [ ] Download any previous version
- [ ] Side-by-side text diff
- [ ] Metadata change history
- [ ] Restore previous version
- [ ] Storage-efficient (delta or reference counting)

## Agent Notes
Commit: \`feat: add document version history\`" \
"$MS" "enhancement" "priority: low" "needs-design" "area: backend" "area: frontend"

create_issue "feat: build reporting and analytics dashboard" \
"## Summary
Analytics on processing activity, storage, AI costs, system health.

## Acceptance Criteria
- [ ] Dashboard: docs processed (daily/weekly/monthly), storage used, AI costs
- [ ] Stats: success rate, avg processing time, failure reasons
- [ ] Storage: per-provider usage, growth trends
- [ ] AI: confidence scores, distribution
- [ ] Export as CSV/PDF
- [ ] Filterable by date, type, pipeline

## Implementation Notes
- Aggregate via Celery periodic task
- Dedicated analytics table
- Chart.js for frontend

## Agent Notes
Commit: \`feat: add reporting and analytics dashboard\`" \
"$MS" "enhancement" "priority: medium" "needs-design" "area: frontend" "area: backend"

create_issue "feat: add SLA monitoring and alerting" \
"## Summary
Monitor processing SLAs and alert on threshold breaches.

## Acceptance Criteria
- [ ] Configurable thresholds: max processing time, max queue depth, min success rate
- [ ] Alert channels: email, webhook, in-app
- [ ] SLA compliance dashboard
- [ ] Historical reporting
- [ ] Escalation (warn → critical)
- [ ] Health endpoint with SLA status

## Depends On
- Notification system (v0.7.0), Reporting dashboard

## Agent Notes
Commit: \`feat: add SLA monitoring and alerting\`" \
"$MS" "enhancement" "priority: low" "area: backend" "area: infrastructure"

# ────────────────────────────────────────
# v2.0.0 — Platform Expansion
# ────────────────────────────────────────
echo ""
echo "  >>> v2.0.0 — Platform Expansion <<<"
echo ""

MS="$MS_20"

create_issue "feat: add self-hosted OCR engine support (Tesseract, EasyOCR)" \
"## Summary
Support self-hosted OCR as alternative to Azure Document Intelligence.

## Acceptance Criteria
- [ ] Tesseract OCR integration
- [ ] EasyOCR integration
- [ ] Provider selection via config (Azure, Tesseract, EasyOCR)
- [ ] Comparable output format to Azure
- [ ] Performance benchmarks vs Azure
- [ ] Docker image with OCR engines included
- [ ] GPU acceleration support (EasyOCR)

## Implementation Notes
- Use AI provider abstraction from v0.8.0
- OCR provider as pipeline step
- Quality comparison metrics

## Agent Notes
Commit: \`feat: add self-hosted OCR support\`" \
"$MS" "enhancement" "priority: high" "area: ai" "area: infrastructure"

create_issue "feat: add local LLM support (Ollama, LLaMA)" \
"## Summary
Support local/self-hosted LLMs as alternative to OpenAI for metadata extraction.

## Acceptance Criteria
- [ ] Ollama integration for local model inference
- [ ] Support for LLaMA, Mistral, and other popular models
- [ ] Provider selection via config
- [ ] Prompt templates optimized for local models
- [ ] Performance and quality comparison vs OpenAI
- [ ] GPU acceleration support
- [ ] Model download and management UI

## Implementation Notes
- Use AI provider abstraction from v0.8.0
- Ollama API is OpenAI-compatible (simplifies integration)
- May need prompt engineering for smaller models

## Agent Notes
Commit: \`feat: add local LLM support via Ollama\`" \
"$MS" "enhancement" "priority: high" "area: ai"

create_issue "feat: build desktop application (Electron)" \
"## Summary
Desktop app for Windows, macOS, and Linux with native OS integration.

## Acceptance Criteria
- [ ] Electron-based app connecting to DocuElevate server
- [ ] Native file drag-and-drop from OS
- [ ] System tray icon with notifications
- [ ] Watch folder support (auto-upload new files)
- [ ] Offline document viewing
- [ ] Auto-update mechanism
- [ ] Windows, macOS, Linux builds

## Agent Notes
Commit: \`feat: add desktop application\`" \
"$MS" "enhancement" "priority: medium" "needs-design" "area: frontend"

create_issue "feat: build mobile apps (iOS and Android)" \
"## Summary
Native mobile apps for document upload, viewing, and management.

## Acceptance Criteria
- [ ] iOS and Android apps (React Native or Flutter)
- [ ] Camera capture → direct upload
- [ ] Document viewing and search
- [ ] Push notifications for processing events
- [ ] Offline document cache
- [ ] Biometric authentication

## Agent Notes
Commit: \`feat: add mobile apps\`" \
"$MS" "enhancement" "priority: medium" "needs-design" "area: frontend"

create_issue "feat: build CLI tool for power users" \
"## Summary
Command-line tool for scripting and automation.

## Acceptance Criteria
- [ ] Commands: upload, download, search, list, status, config
- [ ] Batch operations via glob patterns
- [ ] Pipe-friendly output (JSON, CSV, plain)
- [ ] Authentication via API key or OAuth device flow
- [ ] Tab completion (bash, zsh, fish)
- [ ] Published to PyPI (\`pip install docuelevate-cli\`)

## Agent Notes
Commit: \`feat: add CLI tool\`" \
"$MS" "enhancement" "priority: medium" "agentic-ready" "area: api"

create_issue "feat: add browser extension for web clipping" \
"## Summary
Browser extension to clip web pages and send to DocuElevate as documents.

## Acceptance Criteria
- [ ] Chrome and Firefox extensions
- [ ] Clip full page, selection, or screenshot
- [ ] Convert to PDF before upload
- [ ] Quick metadata tagging on clip
- [ ] Authentication with DocuElevate instance

## Agent Notes
Commit: \`feat: add browser extension\`" \
"$MS" "enhancement" "priority: low" "needs-design" "area: frontend"

create_issue "feat: implement document lifecycle management and retention policies" \
"## Summary
Manage document lifecycle from ingestion through archival and deletion.

## Acceptance Criteria
- [ ] Lifecycle stages: active, archived, pending-deletion, deleted
- [ ] Retention policies per document type or category
- [ ] Auto-archive after configurable period
- [ ] Auto-delete after retention period expires
- [ ] Legal hold (prevent deletion regardless of policy)
- [ ] Retention policy management UI
- [ ] Compliance reporting

## Agent Notes
Commit: \`feat: add document lifecycle management\`" \
"$MS" "enhancement" "priority: medium" "area: backend" "needs-design"

create_issue "feat: add compliance templates (GDPR, HIPAA, SOC2)" \
"## Summary
Pre-built compliance configurations for common regulatory frameworks.

## Acceptance Criteria
- [ ] GDPR template: data retention, right to deletion, export, audit logging
- [ ] HIPAA template: access controls, encryption, audit trail
- [ ] SOC2 template: monitoring, incident response, access management
- [ ] One-click apply template to tenant configuration
- [ ] Compliance status dashboard
- [ ] Gap analysis report

## Depends On
- Multi-tenancy, RBAC, audit logging, lifecycle management

## Agent Notes
Commit: \`feat: add compliance templates\`" \
"$MS" "enhancement" "priority: medium" "needs-design" "area: backend"

create_issue "feat: build plugin system and marketplace" \
"## Summary
Extensible plugin architecture allowing third-party integrations.

## Acceptance Criteria
- [ ] Plugin API with defined hooks and extension points
- [ ] Plugin types: storage providers, AI providers, pipeline steps, UI widgets
- [ ] Plugin packaging and installation format
- [ ] Plugin sandboxing (resource limits, permission scoping)
- [ ] Plugin marketplace UI (browse, install, configure)
- [ ] Plugin developer documentation and SDK

## Agent Notes
Commit: \`feat: add plugin system and marketplace\`" \
"$MS" "enhancement" "priority: low" "needs-design" "area: backend" "area: api"

# ══════════════════════════════════════════════
# DONE
# ══════════════════════════════════════════════
echo ""
echo "============================================="
echo "  Setup Complete!"
echo "============================================="
echo ""
echo "Summary:"
gh api "repos/$REPO/milestones" --jq '.[] | "  \(.title): \(.open_issues) open issues"' 2>/dev/null
echo ""
echo "Total open issues:"
gh api "repos/$REPO" --jq '"  \(.open_issues_count) open issues"' 2>/dev/null
echo ""
echo "View your milestones at:"
echo "  https://github.com/$REPO/milestones"
echo ""
echo "View your issues at:"
echo "  https://github.com/$REPO/issues"
echo ""
