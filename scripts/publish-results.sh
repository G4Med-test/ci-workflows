#!/usr/bin/env bash
# Writes the collected results of a test (results.json, plots/, provenance.json, from
# `export.py collect`) into a checkout of validation-results, with the layout of the
# publish-results job of run-validation-padova.yml:
#
#   <test>/                     the latest results, whatever their Geant4 version
#   <test>/versions/<version>/  the latest results of each Geant4 version
#
# Both are replaced; the other versions are kept. The Geant4 version is read from
# provenance.json and printed on stdout. Nothing is committed or pushed.
#
# Plain bash (3.2 or later) only.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: publish-results.sh --input DIR --results DIR --test NAME

  --input    collected results (output of export.py collect)
  --results  checkout of G4Med-test/validation-results
  --test     test name: the repository name, as in tests.json
EOF
}

die() {
  if [[ "${GITHUB_ACTIONS:-}" == true ]]; then echo "::error::$*" >&2; else echo "publish-results.sh: $*" >&2; fi
  exit 1
}

input="" results="" test=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --input) input="${2:-}"; shift 2 ;;
    --results) results="${2:-}"; shift 2 ;;
    --test) test="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
done
[[ -n "$input" && -n "$results" && -n "$test" ]] || { usage >&2; die "--input, --results and --test are required"; }
[[ "$test" =~ ^[A-Za-z0-9._-]+$ && "$test" != . && "$test" != .. ]] || die "invalid test name: $test"
[[ -f "$input/results.json" ]] || die "no results.json in $input"
[[ -f "$input/provenance.json" ]] || die "no provenance.json in $input"
[[ -d "$results" ]] || die "validation-results checkout not found: $results"

version=$(grep -o '"geant4_version": *"[^"]*"' "$input/provenance.json" | sed 's/.*"\([^"]*\)"$/\1/' || true)
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9._-]*$ ]] || die "Unexpected Geant4 version: $version"

dir="$results/$test"
mkdir -p "$dir"
find "$dir" -mindepth 1 -maxdepth 1 ! -name versions -exec rm -rf {} +
cp -r "$input/." "$dir/"
rm -rf "$dir/versions/$version"
mkdir -p "$dir/versions/$version"
cp -r "$input/." "$dir/versions/$version/"
echo "$version"
