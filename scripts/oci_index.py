#!/usr/bin/env python3
"""Combine per-architecture SIF manifests into one multi-arch OCI index.

oras manifest index create cannot tag each entry with its platform: an
Apptainer-pushed SIF manifest has no OCI image config for it to read the
architecture from, so the resulting index has no way to pick the right
manifest for the pulling host. This builds the index by hand instead, the
same way geant4-alma9 does for the base image.
"""
import argparse
import hashlib
import json
from pathlib import Path

INDEX = "application/vnd.oci.image.index.v1+json"
MANIFEST = "application/vnd.oci.image.manifest.v1+json"


def descriptor(arch, manifest):
    return {
        "mediaType": MANIFEST,
        "digest": "sha256:" + hashlib.sha256(manifest).hexdigest(),
        "size": len(manifest),
        "platform": {"architecture": arch, "os": "linux"},
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--entry", nargs=2, action="append", required=True, metavar=("ARCH", "MANIFEST"))
    cli.add_argument("--output", required=True)
    args = cli.parse_args()
    manifests = [descriptor(arch, Path(manifest).read_bytes()) for arch, manifest in sorted(args.entry)]
    index = {"schemaVersion": 2, "mediaType": INDEX, "manifests": manifests}
    Path(args.output).write_text(json.dumps(index, indent=2) + "\n")


if __name__ == "__main__":
    main()
