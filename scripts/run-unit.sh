#!/usr/bin/env bash
# Runs the unit macro as run-unit-padova.yml does: in <work>/outputs, bound at /outputs
# and used as working directory, with the datasets at /g4data. The output goes to the
# console; the job fails only if the simulation exits with an error.
#
# Plain bash (3.2 or later) and Apptainer only.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-unit.sh --sif FILE --macro FILE --work DIR [--g4data DIR]

  --sif     image of the test
  --macro   unit macro (default of the pipeline: macro/unit.mac of the test)
  --work    working directory: the macro runs in <work>/outputs
  --g4data  Geant4 datasets (default: $G4DATA, else /cvmfs/geant4.cern.ch/share/data)
EOF
}

die() {
  if [[ "${GITHUB_ACTIONS:-}" == true ]]; then echo "::error::$*" >&2; else echo "run-unit.sh: $*" >&2; fi
  exit 1
}

sif="" macro="" work="" g4data="${G4DATA:-/cvmfs/geant4.cern.ch/share/data}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sif) sif="${2:-}"; shift 2 ;;
    --macro) macro="${2:-}"; shift 2 ;;
    --work) work="${2:-}"; shift 2 ;;
    --g4data) g4data="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
done
[[ -n "$sif" && -n "$macro" && -n "$work" ]] || { usage >&2; die "--sif, --macro and --work are required"; }
[[ -f "$sif" ]] || die "image not found: $sif"
[[ -f "$macro" ]] || die "macro not found: $macro"
[[ -d "$g4data" ]] || die "Geant4 datasets not found: $g4data (set --g4data or G4DATA)"

sif=$(cd "$(dirname "$sif")" && pwd)/$(basename "$sif")
macro_dir=$(cd "$(dirname "$macro")" && pwd)
mkdir -p "$work/outputs"
cd "$work/outputs"

# The macro keeps its own path: its directory is bound at the same place in the image,
# where it is visible also outside the directories Apptainer binds by default.
echo "Running macro: $macro_dir/$(basename "$macro")" >&2
apptainer run --unsquash \
  -B "$g4data:/g4data:ro" \
  -B "$macro_dir:$macro_dir:ro" \
  -B "$PWD:/outputs" \
  "$sif" "$macro_dir/$(basename "$macro")"
