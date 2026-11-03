#!/usr/bin/env bash
# Adds a test repository to G4Med-test, protected from the start:
#
#   add-test.sh <name> ["description"]
#
# creates G4Med-test/<name>, public, from G4Med-test/template (unless it exists
# already, e.g. created from the web page of the template), protects its default
# branch with protect-repos.sh and checks the result with check_protection.py.
# From then on its code changes only through approved pull requests, and the Padova
# workflows run it. Add it to tests.json, with a pull request, once its validation
# works. Needs `gh` logged in as an organization owner.
set -euo pipefail

usage() { echo "usage: add-test.sh <name> [\"description\"]" >&2; exit 2; }
(($# == 1 || $# == 2)) || usage
name=$1
[[ $name =~ ^[A-Za-z0-9_.-]+$ ]] || usage
repo=G4Med-test/$name
here="$(cd "$(dirname "$0")" && pwd)"

if gh api "repos/$repo" >/dev/null 2>&1; then
  echo "$repo exists: protecting it"
else
  args=(--public --template G4Med-test/template)
  if (($# == 2)); then args+=(--description "$2"); fi
  gh repo create "$repo" "${args[@]}"
fi

# GitHub copies the template asynchronously: the ruleset needs the default branch.
for attempt in $(seq 1 30); do
  branch=$(gh api "repos/$repo" --jq .default_branch)
  if gh api "repos/$repo/branches/$branch" >/dev/null 2>&1; then break; fi
  if ((attempt == 30)); then echo "$repo: no $branch branch after 60 s" >&2; exit 1; fi
  sleep 2
done

"$here/protect-repos.sh" "$repo"
GH_TOKEN=$(gh auth token) python3 "$here/check_protection.py" "$repo"
cat <<EOF

$repo is ready: https://github.com/$repo
Develop on branches and open pull requests to $branch (see the template README).
When its validation works, add it to ci-workflows/tests.json with a pull request.
EOF
