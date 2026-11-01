#!/usr/bin/env bash
# Exports the portal JSON of one macro run by run-macro.sh, as run-validation-padova.yml
# does: validation/export.py runs inside the test image (Python with NumPy and uproot,
# geant4-config for the version), with the test repository bound read-only at
# /validation, this ci-workflows checkout at /ci-tools and the working directory at
# /work. It reads <work>/outputs and writes <work>/json: results.json, plots/<md5>.json,
# job.json and provenance.json.
#
# provenance.json is filled from the environment, which Apptainer passes to the image:
# GITHUB_REPOSITORY and GITHUB_SHA (the test repository and commit) and IMAGE (the
# oras:// reference of the image). Fields left unset are null.
#
# Plain bash (3.2 or later) and Apptainer only.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: export-macro.sh --sif FILE --repo DIR --macro NAME --work DIR [--config FILE] [--tools DIR]

  --sif     image of the test
  --repo    checkout of the test repository
  --macro   macro name relative to the repository's macro/, as in config.json
  --work    working directory of run-macro.sh: <work>/json must not exist
  --config  validation config, relative to --repo (default: validation/config.json)
  --tools   ci-workflows checkout (default: the one containing this script)
EOF
}

die() {
  if [[ "${GITHUB_ACTIONS:-}" == true ]]; then echo "::error::$*" >&2; else echo "export-macro.sh: $*" >&2; fi
  exit 1
}

sif="" repo="" macro="" work="" config="validation/config.json"
tools=$(cd "$(dirname "$0")/.." && pwd)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sif) sif="${2:-}"; shift 2 ;;
    --repo) repo="${2:-}"; shift 2 ;;
    --macro) macro="${2:-}"; shift 2 ;;
    --work) work="${2:-}"; shift 2 ;;
    --config) config="${2:-}"; shift 2 ;;
    --tools) tools="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
done
[[ -n "$sif" && -n "$repo" && -n "$macro" && -n "$work" ]] \
  || { usage >&2; die "--sif, --repo, --macro and --work are required"; }
[[ -f "$sif" ]] || die "image not found: $sif"
[[ -f "$repo/$config" ]] || die "validation config not found: $repo/$config"
[[ -f "$tools/validation/export.py" ]] || die "not a ci-workflows checkout: $tools"
[[ -d "$work/outputs" ]] || die "no outputs to export: $work/outputs"
[[ ! -e "$work/json" ]] || die "$work/json already exists"
repo=$(cd "$repo" && pwd)
work=$(cd "$work" && pwd)
tools=$(cd "$tools" && pwd)

apptainer exec --unsquash \
  -B "$repo:/validation:ro" \
  -B "$tools:/ci-tools:ro" \
  -B "$work:/work" \
  --pwd /validation "$sif" \
  /opt/venv/bin/python3 /ci-tools/validation/export.py export \
  --repo /validation --config "$config" --macro "$macro" \
  --input /work/outputs --output /work/json
