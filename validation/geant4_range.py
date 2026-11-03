#!/usr/bin/env python3
"""Geant4 versions a test supports: the optional "geant4" field of validation/config.json.

    {"macros": ["main.mac"],
     "geant4": {"min": "11.4", "max": "11.4", "reason": "opengate 10.1.1 targets Geant4 11.4"}}

"min" and "max" are inclusive and optional (at least one): "11.4" is the whole 11.4
series (11.4.0.beta to 11.4.x), "11.4.2" one version and its pre-releases. "reason"
is required: it is shown wherever the test is left out. A Geant4 validation
(scripts/release.py) does not start a test outside its range, a build with such a
Geant4 tag stops at once, and local-pipeline.sh skips the test (it has a bash copy of
allows(), kept equal by tests/test_local_pipeline.py).

    geant4_range.py check [--config C] [--tag vX.Y.Z | --apptainer-def D]

exits with 1, and says why, if the test does not support that Geant4 tag (or the TAG
default of the Apptainer definition). Standard library only.
"""
import argparse
import json
from pathlib import Path
import re
import sys

BOUND = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?\Z")
VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
TAG_DEFAULT = re.compile(r"^\s*TAG=(\S+)\s*$", re.M)


def parse(field):
    """The checked "geant4" field of a configuration (None if absent)."""
    if field is None:
        return None
    if not isinstance(field, dict) or not set(field) <= {"min", "max", "reason"}:
        raise ValueError('config "geant4" must be {"min": ..., "max": ..., "reason": ...}')
    if "min" not in field and "max" not in field:
        raise ValueError('config "geant4" needs "min", "max" or both')
    if not isinstance(field.get("reason"), str) or not field["reason"].strip():
        raise ValueError('config "geant4" needs a "reason"')
    for key in ("min", "max"):
        if key in field and not (isinstance(field[key], str) and BOUND.match(field[key])):
            raise ValueError('config "geant4" %s must be a Geant4 version such as "11.4" or "11.4.2", not %r'
                             % (key, field[key]))
    if "min" in field and "max" in field:
        low, high = bound(field["min"]), bound(field["max"])
        n = min(len(low), len(high))
        if low[:n] > high[:n]:
            raise ValueError('config "geant4": min %s is above max %s' % (field["min"], field["max"]))
    return field


def bound(text):
    return tuple(int(n) for n in BOUND.match(text).groups() if n is not None)


def allows(field, tag):
    """True if the Geant4 tag (v11.4.3, 11.5.0.beta) is in the range of the field."""
    if field is None:
        return True
    m = VERSION.match(tag)
    if not m:
        raise ValueError("Not a Geant4 version: %r" % tag)
    version = tuple(int(n) for n in m.groups())
    if "min" in field:
        low = bound(field["min"])
        if version[:len(low)] < low:
            return False
    if "max" in field:
        high = bound(field["max"])
        if version[:len(high)] > high:
            return False
    return True


def describe(field):
    if field.get("min") == field.get("max"):
        return "Geant4 " + field["min"]
    if "max" not in field:
        return "Geant4 >= " + field["min"]
    if "min" not in field:
        return "Geant4 <= " + field["max"]
    return "Geant4 %s to %s" % (field["min"], field["max"])


def excluded(config, tag):
    """Why the configuration (a dict) excludes the Geant4 tag; None if it allows it."""
    field = parse(config.get("geant4"))
    if allows(field, tag):
        return None
    return "requires %s: %s" % (describe(field), field["reason"])


def tag_default(apptainer_def):
    m = TAG_DEFAULT.search(Path(apptainer_def).read_text())
    if not m:
        raise ValueError("No TAG= default in " + str(apptainer_def))
    return m.group(1)


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = cli.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="exit with 1 if the test does not support the Geant4 tag")
    check.add_argument("--config", type=Path, default=Path("validation/config.json"))
    which = check.add_mutually_exclusive_group(required=True)
    which.add_argument("--tag", help="Geant4 tag, e.g. v11.4.3")
    which.add_argument("--apptainer-def", type=Path, help="use the TAG default of this definition")
    args = cli.parse_args(argv)
    config = json.loads(args.config.read_text()) if args.config.exists() else {}
    if config.get("geant4") is None:
        print("%s: no Geant4 range, every version allowed" % args.config)
        return 0
    tag = args.tag or tag_default(args.apptainer_def)
    why = excluded(config, tag)
    if why:
        print("::error::Geant4 %s is not supported by this test: it %s (%s)" % (tag, why, args.config))
        return 1
    print("Geant4 %s is supported by this test" % tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
