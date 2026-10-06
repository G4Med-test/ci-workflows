#!/usr/bin/env python3
"""Read tests.json, the test repositories checked by self-test and Geant4 releases."""
import json
from pathlib import Path
import re
import sys

TESTS = Path(__file__).resolve().parents[1] / "tests.json"
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
REF = re.compile(r"[A-Za-z0-9_./-]+\Z")


def load(path=TESTS):
    tests = json.loads(Path(path).read_text())["tests"]
    repos = [test["repo"] for test in tests]
    if not tests or len(set(repos)) != len(repos):
        raise ValueError("tests.json must list each repository once")
    for test in tests:
        if set(test) != {"repo", "ref"} or not REPO.match(test["repo"]) or not REF.match(test["ref"]):
            raise ValueError("Each test needs a valid 'repo' (owner/name) and 'ref': %r" % test)
    return tests


def main():
    if sys.argv[1:] == ["matrix"]:
        print(json.dumps({"include": load()}, separators=(",", ":")))
    elif sys.argv[1:] == ["lines"]:
        for test in load():
            print(test["repo"], test["ref"])
    else:
        sys.exit("usage: tests_list.py matrix|lines")


if __name__ == "__main__":
    main()
