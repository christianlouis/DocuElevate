#!/usr/bin/env bash
# Resolve the release version created for one exact merge commit.

set -euo pipefail

head_sha="${1:-$(git rev-parse HEAD)}"

# Semantic Release creates an annotated tag on a release commit whose direct
# parent is the merge commit that triggered the release workflow. Matching the
# parent prevents a concurrent newer release from being assigned to this build.
while IFS= read -r tag; do
  tag_commit="$(git rev-parse "${tag}^{commit}")"
  read -r -a commit_line <<<"$(git rev-list --parents -n 1 "${tag_commit}")"
  for parent_sha in "${commit_line[@]:1}"; do
    if [[ "${parent_sha}" == "${head_sha}" ]]; then
      printf '%s\n' "${tag#v}"
      exit 0
    fi
  done
done < <(git tag --list 'v[0-9]*' --sort=-version:refname)

# No tag means the commit did not create a release (for example, a docs-only
# change). The caller deliberately falls back to the checked-in VERSION file.
exit 0
