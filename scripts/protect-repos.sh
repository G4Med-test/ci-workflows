#!/usr/bin/env bash
# Applies the "reviewed-code-only" protection to every test in tests.json and to the
# repositories the pipeline trusts (ci-workflows, template, geant4-alma9,
# apptainer-gha-runner), or to the repositories given as arguments.
# validation-results is left out: the pipeline merges its pull requests itself.
#
# - ruleset "reviewed-default-branch" on the default branch: no deletion or force
#   push, changes only through pull requests approved by someone with write access,
#   approvals dismissed by new commits, the last push approved by someone else, and
#   the GitHub-hosted build and unit test passing (tests and ci-workflows only);
#   Organization owners can merge their own pull requests without approval, but
#   still cannot push directly (bypass only through pull requests);
# - pull request workflows from outside collaborators need an approval to run.
#
# Re-running it updates the existing ruleset. Needs `gh` logged in as an admin.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
if (($#)); then
  repos=("$@")
else
  repos=(G4Med-test/ci-workflows G4Med-test/template G4Med-test/geant4-alma9 G4Med-test/apptainer-gha-runner)
  while read -r repo; do repos+=("$repo"); done < <(python3 "$here/validation/tests_list.py" matrix \
    | python3 -c 'import json,sys; print("\n".join(t["repo"] for t in json.load(sys.stdin)["include"]))')
fi

ruleset() {
  # $1: required status checks, as a JSON array of check names
  cat <<JSON
{
  "name": "reviewed-default-branch",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "bypass_actors": [{"actor_type": "OrganizationAdmin", "actor_id": 1, "bypass_mode": "pull_request"}],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request", "parameters": {
      "required_approving_review_count": 1,
      "dismiss_stale_reviews_on_push": true,
      "require_last_push_approval": true,
      "require_code_owner_review": false,
      "required_review_thread_resolution": false
    }}$(python3 -c '
import json, sys
checks = json.loads(sys.argv[1])
print("," + json.dumps({"type": "required_status_checks", "parameters": {
    "strict_required_status_checks_policy": False,
    "required_status_checks": [{"context": c} for c in checks]}}) if checks else "")' "$1")
  ]
}
JSON
}

for repo in "${repos[@]}"; do
  case "$repo" in
    */ci-workflows)
      # Required only once self-test.yml, which runs actionlint, is on the default branch.
      if gh api "repos/$repo/contents/.github/workflows/self-test.yml" >/dev/null 2>&1; then
        checks='["actionlint"]'
      else
        checks='[]'
      fi ;;
    # The template skips its own pipeline; geant4-alma9 and apptainer-gha-runner have
    # no pull request check common to every change.
    */template | */geant4-alma9 | */apptainer-gha-runner) checks='[]' ;;
    *) checks='["run-pipeline / build / build (amd64)", "run-pipeline / unit-test / test-container"]' ;;
  esac
  id=$(gh api "repos/$repo/rulesets" --jq '.[] | select(.name == "reviewed-default-branch") | .id')
  if [[ -n "$id" ]]; then
    ruleset "$checks" | gh api -X PUT "repos/$repo/rulesets/$id" --input - >/dev/null
    echo "$repo: ruleset $id updated"
  else
    ruleset "$checks" | gh api -X POST "repos/$repo/rulesets" --input - >/dev/null
    echo "$repo: ruleset created"
  fi
  gh api -X PUT "repos/$repo/actions/permissions/fork-pr-contributor-approval" \
    -f approval_policy=all_external_contributors >/dev/null
done
