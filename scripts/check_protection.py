#!/usr/bin/env python3
"""Check that the default branch of repositories accepts only reviewed changes.

check_protection.py [--branch B] [owner/repo ...]

A branch passes when the rulesets active on it forbid deletion and force pushes and
require pull requests approved by at least one reviewer: the rules that
protect-repos.sh sets. Without repositories it checks the ones protect-repos.sh
protects by default (--list prints them): every test in tests.json and the
repositories of the organization listed in ORGANIZATION.

The rules of a branch are public (GET repos/<repo>/rules/branches/<branch>), so any
token, or none, can check them; who may bypass them is visible only to admins and is
not checked. Run by the Padova workflows before running anything, and by self-test.

Environment: GITHUB_TOKEN or GH_TOKEN, optional (higher API rate limit).
"""
import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
import tests_list

API = "https://api.github.com"
# Besides the tests: the repositories whose code the pipeline runs, the dashboard
# (it holds a token of the organization) and .github (the organization's profile).
ORGANIZATION = ["G4Med-test/ci-workflows", "G4Med-test/template",
                "G4Med-test/geant4-alma9", "G4Med-test/apptainer-gha-runner",
                "G4Med-test/dashboard", "G4Med-test/.github"]


def default_repositories():
    return ORGANIZATION + [test["repo"] for test in tests_list.load()]


def problems(rules):
    """What the rules of a branch (the API's list) lack; empty if it is protected."""
    types = {rule["type"] for rule in rules}
    missing = []
    if "deletion" not in types:
        missing.append("deletion is allowed")
    if "non_fast_forward" not in types:
        missing.append("force pushes are allowed")
    approvals = max((rule.get("parameters", {}).get("required_approving_review_count", 0)
                     for rule in rules if rule["type"] == "pull_request"), default=None)
    if approvals is None:
        missing.append("direct pushes are allowed (no pull request rule)")
    elif approvals < 1:
        missing.append("pull requests need no approval")
    return missing


def get(path):
    request = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def check(repo, branch=None):
    """(branch, problems) of one repository."""
    if branch is None:
        branch = get("/repos/%s" % repo)["default_branch"]
    rules = get("/repos/%s/rules/branches/%s" % (repo, urllib.parse.quote(branch, safe="")))
    return branch, problems(rules)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("repos", nargs="*", metavar="owner/repo")
    parser.add_argument("--branch", help="branch to check (default: the default branch)")
    parser.add_argument("--list", action="store_true",
                        help="print the repositories checked by default and exit")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(default_repositories()))
        return 0
    failed = False
    for repo in args.repos or default_repositories():
        try:
            branch, missing = check(repo, args.branch)
        except urllib.error.HTTPError as e:
            branch, missing = args.branch or "default branch", ["cannot read it: HTTP %d" % e.code]
        if missing:
            failed = True
            print("::error::%s: %s is not protected: %s. An organization owner protects it "
                  "with ci-workflows/scripts/protect-repos.sh %s"
                  % (repo, branch, "; ".join(missing), repo))
        else:
            print("%s: %s protected" % (repo, branch))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
