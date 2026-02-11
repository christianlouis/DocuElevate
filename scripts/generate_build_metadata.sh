#!/bin/bash
#
# Generate build metadata files for DocuElevate
#
# This script generates metadata files that are read by the application
# at runtime to display version, build date, and Git commit information
# in the /status endpoint.
#
# Files generated:
# - BUILD_DATE: UTC timestamp of when the build was created
# - GIT_SHA: Short Git commit SHA (7 characters)
# - RUNTIME_INFO: Combined build information
#
# Usage:
#   ./scripts/generate_build_metadata.sh
#
# The script should be run during Docker build or CI/CD pipeline.

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Navigate to project root
cd "${PROJECT_ROOT}"

echo "Generating build metadata..."

# Generate BUILD_DATE in ISO 8601 format with time (UTC)
BUILD_DATE=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
echo "${BUILD_DATE}" > BUILD_DATE
echo "✓ BUILD_DATE: ${BUILD_DATE}"

# Generate GIT_SHA (short commit hash)
if git rev-parse --git-dir > /dev/null 2>&1; then
    GIT_SHA=$(git rev-parse --short=7 HEAD)
    echo "${GIT_SHA}" > GIT_SHA
    echo "✓ GIT_SHA: ${GIT_SHA}"
    
    # Get full commit SHA for reference
    GIT_FULL_SHA=$(git rev-parse HEAD)
    
    # Get commit date
    GIT_COMMIT_DATE=$(git log -1 --format=%cd --date=iso-strict)
    
    # Get branch name (if available)
    GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
else
    echo "⚠ Warning: Not a git repository, using 'unknown' for Git metadata"
    echo "unknown" > GIT_SHA
    GIT_SHA="unknown"
    GIT_FULL_SHA="unknown"
    GIT_COMMIT_DATE="unknown"
    GIT_BRANCH="unknown"
fi

# Read VERSION file
if [ -f "VERSION" ]; then
    VERSION=$(cat VERSION | tr -d '\n')
    echo "✓ VERSION (from file): ${VERSION}"
else
    echo "⚠ Warning: VERSION file not found"
    VERSION="unknown"
fi

# Try to derive version from the latest git tag (semantic-release creates vX.Y.Z tags)
if git rev-parse --git-dir > /dev/null 2>&1; then
    LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    if [ -n "${LATEST_TAG}" ]; then
        # Strip the 'v' prefix from the tag (e.g., v0.9.1 -> 0.9.1)
        TAG_VERSION="${LATEST_TAG#v}"
        if [ "${TAG_VERSION}" != "${VERSION}" ]; then
            echo "⚠ VERSION file (${VERSION}) is out of sync with latest tag (${TAG_VERSION})"
            echo "  Updating VERSION file to ${TAG_VERSION}"
            echo "${TAG_VERSION}" > VERSION
            VERSION="${TAG_VERSION}"
            echo "✓ VERSION (updated from tag): ${VERSION}"
        fi
    fi
fi

# Generate RUNTIME_INFO with combined metadata
cat > RUNTIME_INFO << EOF
DocuElevate Build Information
==============================
Version: ${VERSION}
Build Date: ${BUILD_DATE}
Git Commit: ${GIT_FULL_SHA}
Git Short SHA: ${GIT_SHA}
Git Branch: ${GIT_BRANCH}
Commit Date: ${GIT_COMMIT_DATE}
Build Timestamp: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
==============================
EOF

echo "✓ RUNTIME_INFO generated"
echo ""
echo "Build metadata generation complete!"
echo ""
echo "Files created/updated:"
echo "  - BUILD_DATE"
echo "  - GIT_SHA"
echo "  - RUNTIME_INFO"
echo ""
