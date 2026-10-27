#!/usr/bin/env python3
"""Fill <test>/versions/<geant4 version>/ of a validation-results checkout from its history.

The pipeline writes versions/ since it exists; results published before have only the
latest run of each test. For each test and Geant4 version without a versions/ folder,
this copies the most recent commit's results of that version (from provenance.json).
Run it in a full clone, review, then commit through a pull request:

  python3 ci-workflows/scripts/seed_versions.py validation-results
"""
import json
from pathlib import Path
import re
import subprocess
import sys

VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9._-]*$")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def main():
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else "validation-results")
    if git(repo, "rev-parse", "--is-shallow-repository").strip() == "true":
        raise SystemExit("Shallow clone: run `git fetch --unshallow` first")
    for test in sorted(p for p in repo.iterdir() if p.is_dir() and not p.name.startswith(".")):
        seen = set()
        for commit in git(repo, "log", "--format=%H", "--", f"{test.name}/provenance.json").split():
            try:
                prov = json.loads(git(repo, "show", f"{commit}:{test.name}/provenance.json"))
            except (subprocess.CalledProcessError, ValueError):
                continue
            version = prov.get("geant4_version") or ""
            if not VERSION.match(version) or version in seen:
                continue
            seen.add(version)  # newest commit of this version
            target = test / "versions" / version
            if target.exists():
                continue
            files = git(repo, "ls-tree", "-r", "--name-only", commit, "--", f"{test.name}/").splitlines()
            for name in files:
                rel = Path(name).relative_to(test.name)
                if rel.parts[0] == "versions":
                    continue
                out = target / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{name}"],
                                               check=True, capture_output=True).stdout)
            print(f"{test.name}/versions/{version} <- {commit[:7]}")


if __name__ == "__main__":
    main()
