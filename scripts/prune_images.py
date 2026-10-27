#!/usr/bin/env python3
"""Prune old images of one test from GHCR (ghcr.io/<owner>/<test, lowercase>).

Every build pushes <tag>-amd64, <tag>-arm64 and the index <tag>, where <tag> is the
commit SHA, plus -<geant4 tag> for other Geant4 versions. A build is kept when:

- it is one of the --keep newest builds;
- it is younger than --days days;
- published results point to it (provenance.json of the test in validation-results,
  its latest results and every versions/<version>/): they must stay reproducible.

Untagged versions (left behind when a tag is pushed again) are deleted once older
than --days. Without --delete nothing is deleted: the plan is only printed.

Environment: GITHUB_TOKEN (packages write on the test's package), GITHUB_REPOSITORY
(the test repository), RESULTS_DIR (checkout of validation-results).
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ARCH = re.compile(r"-(amd64|arm64)\Z")


def base_tag(tag):
    return ARCH.sub("", tag)


def referenced_tags(results_dir, test, package):
    """Tags of this package named by the provenance.json files of the published results."""
    root = Path(results_dir) / test
    if not Path(results_dir).is_dir():
        raise SystemExit(f"{results_dir} not found: cannot tell which images are published")
    prefix = re.compile(r"^(?:oras://)?ghcr\.io/[^/]+/" + re.escape(package) + r":(.+)$")
    tags = set()
    for prov in [root / "provenance.json", *root.glob("versions/*/provenance.json")]:
        if prov.exists():
            m = prefix.match(json.loads(prov.read_text()).get("image") or "")
            if m:
                tags.add(base_tag(m.group(1)))
    return tags


def plan(versions, keep, days, referenced, now):
    """(kept, deleted) package versions; each version is the API object."""
    newest = {}
    for v in versions:
        for tag in v["metadata"]["container"]["tags"]:
            b = base_tag(tag)
            created = v["created_at"]
            newest[b] = max(newest.get(b, created), created)
    recent = sorted(newest, key=newest.get, reverse=True)[:keep]
    limit = (now - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    keep_bases = set(recent) | {b for b, t in newest.items() if t >= limit} | (referenced & set(newest))
    kept, deleted = [], []
    for v in versions:
        tags = v["metadata"]["container"]["tags"]
        old = v["created_at"] < limit
        if (tags and not any(base_tag(t) in keep_bases for t in tags)) or (not tags and old):
            deleted.append(v)
        else:
            kept.append(v)
    return kept, deleted


def api(method, url, token):
    req = urllib.request.Request(url, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def main():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--keep", type=int, default=10, help="newest builds always kept (default: %(default)s)")
    cli.add_argument("--days", type=int, default=14, help="builds younger than this are kept (default: %(default)s)")
    cli.add_argument("--delete", action="store_true", help="delete; without it only print the plan")
    args = cli.parse_args()
    owner, test = os.environ["GITHUB_REPOSITORY"].split("/")
    package, token = test.lower(), os.environ["GITHUB_TOKEN"]
    base = f"https://api.github.com/orgs/{owner}/packages/container/{package}/versions"
    versions, page = [], 1
    try:
        while True:
            chunk = api("GET", f"{base}?per_page=100&page={page}", token)
            versions += chunk
            if len(chunk) < 100:
                break
            page += 1
    except urllib.error.HTTPError as err:
        # The repository needs the Admin role on its package (package settings,
        # "Manage Actions access") to list and delete versions with GITHUB_TOKEN.
        print(f"::warning::Cannot list the versions of {package} (HTTP {err.code}): nothing pruned")
        return
    referenced = referenced_tags(os.environ.get("RESULTS_DIR", "validation-results"), test, package)
    kept, deleted = plan(versions, args.keep, args.days, referenced, datetime.now(timezone.utc))
    print(f"{package}: {len(versions)} versions, keeping {len(kept)} "
          f"({len(referenced)} build(s) of published results), {'deleting' if args.delete else 'would delete'} {len(deleted)}")
    for v in deleted:
        tags = ", ".join(v["metadata"]["container"]["tags"]) or "untagged " + v["name"][:19]
        print(f"  {'delete' if args.delete else 'would delete'} {tags} ({v['created_at'][:10]})")
        if args.delete:
            try:
                api("DELETE", f"{base}/{v['id']}", token)
            except urllib.error.HTTPError as err:
                print(f"::warning::Cannot delete {tags} (HTTP {err.code})")
                sys.exit(0)


if __name__ == "__main__":
    main()
