#!/usr/bin/env bash
# Runs one validation macro as run-validation-padova.yml does, on a runner, a farm node
# or a workstation: unchanged, in the empty directory <work>/outputs, bound at /outputs
# and used as working directory, with the datasets at /g4data and the macro copied to
# <work>/macros, bound at /macro. stdout and stderr are saved as test_stdout.txt and
# test_stderr.txt in <work>/outputs; Geant4 errors in them fail the run, so that no
# results are exported from it.
#
# Plain bash (3.2 or later) and Apptainer only.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run-macro.sh --sif FILE --macro FILE --work DIR [--g4data DIR]

  --sif     image of the test
  --macro   validation macro (a file of the test's macro/ directory)
  --work    working directory: <work>/outputs must be empty or missing
  --g4data  Geant4 datasets (default: $G4DATA, else /cvmfs/geant4.cern.ch/share/data)
EOF
}

die() {
  if [[ "${GITHUB_ACTIONS:-}" == true ]]; then echo "::error::$*" >&2; else echo "run-macro.sh: $*" >&2; fi
  exit 1
}

# Geant4 messages that mean the macro did not run as written.
G4_ERRORS='COMMAND NOT FOUND|Batch is interrupted|Fatal Exception|Fatal Error In Argument'

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

mkdir -p "$work/outputs" "$work/macros"
work=$(cd "$work" && pwd)
if [[ -n "$(ls -A "$work/outputs")" ]]; then
  die "$work/outputs is not empty: the macro must run in an empty directory"
fi
cp "$macro" "$work/macros/"
name=$(basename "$macro")

echo "Running $name in $work/outputs" >&2
apptainer run --unsquash \
  -B "$g4data:/g4data:ro" \
  -B "$work/macros:/macro:ro" \
  -B "$work/outputs:/outputs" \
  --pwd /outputs "$sif" "/macro/$name" \
  > "$work/outputs/test_stdout.txt" \
  2> "$work/outputs/test_stderr.txt"

if grep -E "$G4_ERRORS" "$work/outputs/test_stdout.txt" "$work/outputs/test_stderr.txt"; then
  die "Geant4 reported an error; refusing to export results."
fi
