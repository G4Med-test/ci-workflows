#!/usr/bin/env python3
"""Open a pull request in every test of tests.json adding the template's `paths-ignore`
to the push trigger of .github/workflows/ci.yml: pushes changing only documentation
then run no pipeline (template README, "Small changes without running the validation").

Without --apply it only prints, for each repository, what it would do. Needs `gh`
logged in with write access to the test repositories. Repositories whose ci.yml already
has paths-ignore, or whose push trigger is not the template's, are left alone.
"""
import argparse
import base64
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
import tests_list  # noqa: E402

BRANCH = "ci/skip-docs-only-pushes"
PUSH = re.compile(r'^(  push:\n    branches: \[[^\]\n]*\]\n)', re.M)
BLOCK = """    # A push changing only these files does not run the pipeline, so neither the
    # validation on Padova nor the publication of results (README, "Small changes").
    # Pull requests always run: their checks are required to merge.
    paths-ignore:
      - "**.md"
      - "docs/**"
      - "LICENSE*"
      - ".gitignore"
"""
BODY = """Pushes that change only documentation (`*.md`, `docs/`, `LICENSE`, `.gitignore`) no
longer run the pipeline after the merge: no validation on Padova, no new results. Pull
requests still run their required checks. Same as G4Med-test/template; see its README,
"Small changes without running the validation"."""


def gh(*args, input=None):
    return subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True, input=input).stdout


def updated(text):
    if "paths-ignore" in text:
        return None, "already has paths-ignore"
    if not PUSH.search(text):
        return None, "push trigger differs from the template: edit by hand"
    return PUSH.sub(lambda m: m.group(1) + BLOCK, text, count=1), None


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--apply", action="store_true", help="create the branches and pull requests")
    cli.add_argument("repos", nargs="*", help="owner/name (default: every test in tests.json)")
    args = cli.parse_args()
    for repo in args.repos or [t["repo"] for t in tests_list.load()]:
        info = json.loads(gh(f"repos/{repo}"))
        base = info["default_branch"]
        f = json.loads(gh(f"repos/{repo}/contents/.github/workflows/ci.yml?ref={base}"))
        text, why = updated(base64.b64decode(f["content"]).decode())
        if text is None:
            print(f"{repo}: skipped, {why}")
            continue
        if not args.apply:
            print(f"{repo}: would open a pull request on {base}")
            continue
        head = json.loads(gh(f"repos/{repo}/git/ref/heads/{base}"))["object"]["sha"]
        gh(f"repos/{repo}/git/refs", "-X", "POST", "-f", f"ref=refs/heads/{BRANCH}", "-f", f"sha={head}")
        gh(f"repos/{repo}/contents/.github/workflows/ci.yml", "-X", "PUT", "--input", "-", input=json.dumps({
            "message": "ci: do not run the pipeline for documentation-only pushes", "branch": BRANCH,
            "sha": f["sha"], "content": base64.b64encode(text.encode()).decode()}))
        pr = json.loads(gh(f"repos/{repo}/pulls", "-X", "POST", "--input", "-", input=json.dumps({
            "title": "ci: do not run the pipeline for documentation-only pushes", "head": BRANCH, "base": base, "body": BODY})))
        print(f"{repo}: {pr['html_url']}")


if __name__ == "__main__":
    main()
