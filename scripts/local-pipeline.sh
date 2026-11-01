#!/usr/bin/env bash
# Runs the validation pipeline of one, several or all tests outside GitHub Actions, on
# a workstation or a batch farm, with the steps of the CI: the image the CI built for
# the commit, each macro run by run-macro.sh and exported by export-macro.sh, the
# results merged by `export.py collect`. The results have the layout of the CI
# artifact validation-json (results.json, plots/, provenance.json).
#
# Plain bash (3.2 or later), git and Apptainer; Python runs inside the test images.
# On a farm, the run directory must be on a filesystem shared with the nodes.

set -euo pipefail

SELF=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
TOOLS=$(cd "$(dirname "$0")/.." && pwd)
SCRIPTS="$TOOLS/scripts"
GIT_URL="${G4MED_GIT_URL:-https://github.com/G4Med-test}"
REGISTRY="${G4MED_REGISTRY:-oras://ghcr.io/g4med-test}"
CVMFS_DATA="${G4MED_CVMFS_DATA:-/cvmfs/geant4.cern.ch/share/data}"
DIR="${G4MED_RUN_DIR:-$PWD/g4med-run}"
TAB=$(printf '\t')

usage() {
  cat <<'EOF'
Usage: local-pipeline.sh COMMAND [--dir DIR] [options] [arguments]

Runs the validation pipeline of the G4Med tests as the CI does, locally or on a
batch farm. Every command takes --dir DIR, the run directory (default: $G4MED_RUN_DIR,
else ./g4med-run), which must be on a shared filesystem to submit to a farm.

Commands:
  prepare [--ref REF] [--geant4 TAG] [--build] [--g4data DIR] TEST... | all
      Check out each test (default branch, or REF), get its image and the Geant4
      datasets, and list its validation macros in DIR/jobs.txt.
        image     by default the one the CI built for the commit:
                  oras://ghcr.io/g4med-test/<test>:<commit>[-<TAG>]; with --build,
                  built from the checkout (APPTAINER_BUILD_FLAGS, e.g. --fakeroot)
        --geant4  geant4-alma9 tag (e.g. v11.4.3) instead of the TAG of Apptainer.def
        datasets  --g4data DIR, else $G4DATA, else CVMFS, else downloaded once per
                  Geant4 version into DIR/g4data/<version>
  unit [--macro FILE] TEST...
      Run the unit macro (default macro/unit.mac) as the Padova unit test does.
  run [--force] TASK | TEST MACRO
      Run one validation macro and export its JSON: line TASK (from 1) of
      DIR/jobs.txt, or MACRO (name or id) of TEST. Macros already done are skipped
      unless --force. This is the payload of a batch job.
  submit [-j N] local|slurm|condor [-- SCHEDULER OPTIONS]
      Run every macro of DIR/jobs.txt that is not done yet:
        local   here, N at a time (default 1), then collect
        slurm   one array job, then a collect job (sbatch options after --)
        condor  one cluster, one job per macro (condor_submit options after --,
                e.g. -a 'request_memory = 4 GB'); run collect when it finishes
  collect [TEST...]
      Merge the JSON of every macro of each test (default: all prepared tests) into
      DIR/<test>/validation-json, as the collect-json job does.
  status
      Macros done, failed, started and pending of each prepared test.

Run directory:
  DIR/jobs.txt                 one "<test> TAB <id> TAB <macro>" line per macro
  DIR/logs/                    batch job logs
  DIR/g4data/<version>/        downloaded datasets
  DIR/<test>/repo/             checkout of the test
  DIR/<test>/simulation.sif    image of the test
  DIR/<test>/pipeline.env      commit, image and datasets used by the other commands
  DIR/<test>/runs/<id>/        outputs/, macros/, json/ and status of one macro
  DIR/<test>/validation-json/  results of the test

Environment: G4MED_GIT_URL (default https://github.com/G4Med-test), G4MED_REGISTRY
(default oras://ghcr.io/g4med-test), G4DATA, APPTAINER_BUILD_FLAGS, APPTAINER_TMPDIR
(default: a new directory in $TMPDIR, removed at the end; images are unpacked there).
If the images are private, run `apptainer registry login oras://ghcr.io` once.
EOF
}

die() { echo "local-pipeline.sh: $*" >&2; exit 1; }
log() { echo "==> $*" >&2; }
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

check_test_name() {
  [[ "$1" =~ ^[A-Za-z0-9._-]+$ && "$1" != . && "$1" != .. ]] || die "invalid test name: $1"
}

# The run directory, absolute: batch jobs do not start where the submission did.
resolve_dir() {
  if [[ "${1:-}" == create ]]; then mkdir -p "$DIR"; fi
  [[ -d "$DIR" ]] || die "run directory not found: $DIR (run prepare first)"
  DIR=$(cd "$DIR" && pwd)
}

# Apptainer unpacks the image (--unsquash, as on Padova) in APPTAINER_TMPDIR: by default
# a directory of this process in $TMPDIR, node-local on most farms, removed at exit.
use_tmp() {
  [[ -z "${TMP_WORK:-}" ]] || return 0
  TMP_WORK=$(mktemp -d "${TMPDIR:-/tmp}/g4med.XXXXXXXX")
  trap 'rm -rf "$TMP_WORK"' EXIT
  export APPTAINER_TMPDIR="${APPTAINER_TMPDIR:-$TMP_WORK/tmp}"
  export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-$TMP_WORK/cache}"
  mkdir -p "$APPTAINER_TMPDIR" "$APPTAINER_CACHEDIR"
}

load_env() {
  [[ -f "$DIR/$1/pipeline.env" ]] || die "$1 is not prepared in $DIR"
  # shellcheck source=/dev/null
  . "$DIR/$1/pipeline.env"
}

prepared_tests() {
  local env
  for env in "$DIR"/*/pipeline.env; do
    [[ -f "$env" ]] && basename "$(dirname "$env")"
  done
}

status_of() { cat "$DIR/$1/runs/$2/status" 2>/dev/null || echo pending; }

# ---------------------------------------------------------------------------- prepare

cmd_prepare() {
  local ref="" tag="" build=false g4data="" tests=() failed=() t
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) DIR="${2:-}"; shift 2 ;;
      --ref) ref="${2:-}"; shift 2 ;;
      --geant4) tag="${2:-}"; shift 2 ;;
      --build) build=true; shift ;;
      --g4data) g4data="${2:-}"; shift 2 ;;
      -*) die "unknown option: $1" ;;
      all) while read -r t; do tests+=("$t"); done < <(sed -n 's/.*"repo": *"[^"/]*\/\([^"]*\)".*/\1/p' "$TOOLS/tests.json"); shift ;;
      *) tests+=("$1"); shift ;;
    esac
  done
  [[ ${#tests[@]} -gt 0 ]] || die "prepare: name the tests, or all"
  if [[ -n "$tag" ]]; then
    [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$ ]] || die "invalid Geant4 tag: $tag"
  fi
  if [[ -n "$g4data" ]]; then g4data=$(cd "$g4data" && pwd) || die "datasets not found: $g4data"; fi
  for t in "${tests[@]}"; do check_test_name "$t"; done
  resolve_dir create

  # A process per test: a failure leaves the other tests to prepare.
  for t in "${tests[@]}"; do
    bash "$SELF" _prepare "$DIR" "$t" "$ref" "$tag" "$build" "$g4data" || failed+=("$t")
  done
  write_jobs
  log "$(grep -c . "$DIR/jobs.txt" || true) macros in $DIR/jobs.txt"
  [[ ${#failed[@]} -eq 0 ]] || die "not prepared: ${failed[*]}"
}

prepare_test() {
  DIR=$1
  local test=$2 ref=$3 tag=$4 build=$5 g4data=$6
  local tdir="$DIR/$test" repo="$DIR/$test/repo" sif="$DIR/$test/simulation.sif"
  local target="origin/HEAD" sha image="" source previous="" version id macro

  log "$test: checking out ${ref:-the default branch}"
  mkdir -p "$tdir"
  if [[ -d "$repo/.git" ]]; then
    git -C "$repo" fetch --quiet --tags origin
  else
    git clone --quiet "$GIT_URL/$test.git" "$repo"
  fi
  if [[ -n "$ref" ]]; then
    if git -C "$repo" rev-parse --quiet --verify "origin/$ref^{commit}" >/dev/null; then
      target="origin/$ref"
    else
      target="$ref"
    fi
  fi
  git -C "$repo" checkout --quiet --detach "$target"
  sha=$(git -C "$repo" rev-parse HEAD)

  if [[ "$build" == true ]]; then
    source="build:$sha:${tag:-default}"
  else
    # The reference pushed by apptainer-build-deploy.yml.
    image="$REGISTRY/$(lower "$test"):$sha${tag:+-$tag}"
    source="$image"
  fi
  if [[ -f "$tdir/pipeline.env" ]]; then
    # shellcheck source=/dev/null
    previous=$(IMAGE_SOURCE=""; . "$tdir/pipeline.env"; printf '%s' "$IMAGE_SOURCE")
  fi
  if [[ "$previous" != "$source" ]]; then
    # Results of another commit or image are not results of this one.
    rm -rf "$tdir/runs" "$tdir/validation-json" "$tdir/unit" "$tdir/jobs.txt" "$tdir/pipeline.env"
  fi

  use_tmp
  if [[ -f "$sif" && "$previous" == "$source" ]]; then
    log "$test: image already there"
  elif [[ "$build" == true ]]; then
    local flags=() args=()
    read -r -a flags <<< "${APPTAINER_BUILD_FLAGS:-}"
    if [[ -n "$tag" ]]; then args=(--build-arg "TAG=$tag"); fi
    log "$test: building the image of $sha"
    # Apptainer.def copies "." : the build runs in the checkout, as in the CI.
    (cd "$repo" && apptainer build --force ${flags[@]+"${flags[@]}"} ${args[@]+"${args[@]}"} \
      --build-arg "PROJECT_NAME=$test" "$sif.part" Apptainer.def)
    mv "$sif.part" "$sif"
  else
    log "$test: pulling $image"
    apptainer pull --force "$sif.part" "$image" \
      || die "$test: cannot pull $image: the CI did not push an image for this commit (or Geant4 tag), or the package is private (apptainer registry login oras://ghcr.io); --build builds it here"
    mv "$sif.part" "$sif"
  fi
  version=$(apptainer exec --unsquash "$sif" geant4-config --version)
  [[ -n "$version" ]] || die "$test: no Geant4 version in the image"

  if [[ -z "$g4data" && -n "${G4DATA:-}" ]]; then g4data="$G4DATA"; fi
  if [[ -z "$g4data" && -d "$CVMFS_DATA" ]]; then g4data="$CVMFS_DATA"; fi
  if [[ -z "$g4data" ]]; then
    g4data="$DIR/g4data/$version"
    if [[ ! -f "$g4data/.complete" ]]; then
      log "$test: downloading the datasets of Geant4 $version into $g4data"
      mkdir -p "$g4data"
      apptainer exec --unsquash -B "$g4data:/g4data" "$sif" geant4-config --install-datasets
      touch "$g4data/.complete"
    fi
  fi

  : > "$tdir/jobs.txt"
  if [[ -f "$repo/validation/config.json" ]]; then
    apptainer exec --unsquash -B "$repo:/validation:ro" -B "$TOOLS:/ci-tools:ro" --pwd /validation "$sif" \
      /opt/venv/bin/python3 /ci-tools/validation/export.py matrix --lines > "$tdir/matrix.txt"
    while IFS="$TAB" read -r id macro; do
      printf '%s\t%s\t%s\n' "$test" "$id" "$macro" >> "$tdir/jobs.txt"
    done < "$tdir/matrix.txt"
    rm -f "$tdir/matrix.txt"
  else
    log "$test: no validation/config.json, validation skipped"
  fi

  {
    printf 'TEST=%q\n' "$test"
    printf 'REPOSITORY=%q\n' "${GIT_URL##*[/:]}/$test"
    printf 'SHA=%q\n' "$sha"
    printf 'IMAGE=%q\n' "$image"
    printf 'IMAGE_SOURCE=%q\n' "$source"
    printf 'GEANT4_VERSION=%q\n' "$version"
    printf 'G4DATA=%q\n' "$g4data"
  } > "$tdir/pipeline.env"
  log "$test: Geant4 $version, $(grep -c . "$tdir/jobs.txt" || true) validation macros"
}

write_jobs() {
  local t
  : > "$DIR/jobs.txt"
  for t in $(prepared_tests); do cat "$DIR/$t/jobs.txt" >> "$DIR/jobs.txt"; done
}

# ------------------------------------------------------------------------- unit, run

cmd_unit() {
  local macro="macro/unit.mac" tests=() t
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) DIR="${2:-}"; shift 2 ;;
      --macro) macro="${2:-}"; shift 2 ;;
      -*) die "unknown option: $1" ;;
      *) check_test_name "$1"; tests+=("$1"); shift ;;
    esac
  done
  [[ ${#tests[@]} -gt 0 ]] || die "unit: name the tests"
  resolve_dir
  use_tmp
  for t in "${tests[@]}"; do
    load_env "$t"
    rm -rf "$DIR/$t/unit"
    log "$t: unit macro $macro"
    "$SCRIPTS/run-unit.sh" --sif "$DIR/$t/simulation.sif" --macro "$DIR/$t/repo/$macro" \
      --work "$DIR/$t/unit" --g4data "$G4DATA"
  done
}

cmd_run() {
  local force=false args=() line test="" id="" macro="" i m
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) DIR="${2:-}"; shift 2 ;;
      --force) force=true; shift ;;
      -*) die "unknown option: $1" ;;
      *) args+=("$1"); shift ;;
    esac
  done
  resolve_dir
  if [[ ${#args[@]} -eq 1 && "${args[0]}" =~ ^[1-9][0-9]*$ ]]; then
    line=$(sed -n "${args[0]}p" "$DIR/jobs.txt")
    [[ -n "$line" ]] || die "no task ${args[0]} in $DIR/jobs.txt"
    IFS="$TAB" read -r test id macro <<< "$line"
  elif [[ ${#args[@]} -eq 2 ]]; then
    check_test_name "${args[0]}"
    [[ -f "$DIR/${args[0]}/jobs.txt" ]] || die "${args[0]} is not prepared in $DIR"
    while IFS="$TAB" read -r _ i m; do
      if [[ "$i" == "${args[1]}" || "$m" == "${args[1]}" ]]; then test=${args[0]} id=$i macro=$m; fi
    done < "$DIR/${args[0]}/jobs.txt"
    [[ -n "$test" ]] || die "${args[1]} is not a validation macro of ${args[0]}"
  else
    die "run: give a task number or a test and a macro"
  fi
  run_job "$test" "$id" "$macro" "$force"
}

run_job() {
  local test=$1 id=$2 macro=$3 force=$4
  local tdir="$DIR/$1" work="$DIR/$1/runs/$2"
  load_env "$test"
  if [[ "$force" != true && "$(status_of "$test" "$id")" == "done" ]]; then
    log "$test: $macro already done"
    return 0
  fi
  [[ "$(git -C "$tdir/repo" rev-parse HEAD)" == "$SHA" ]] \
    || die "$test: the checkout is no longer at $SHA: run prepare again"

  rm -rf "$work"
  mkdir -p "$work"
  echo started > "$work/status"
  STATUS_FILE="$work/status"
  trap 'echo failed > "$STATUS_FILE"; exit 143' TERM INT
  use_tmp

  # Read by export.py for provenance.json, as in the CI. A modified checkout is not
  # the commit, and an image built here has no reference: those fields stay null.
  export IMAGE GITHUB_REPOSITORY="$REPOSITORY" GITHUB_SHA="$SHA"
  if [[ -z "$IMAGE" ]]; then unset IMAGE; fi
  if [[ -n "$(git -C "$tdir/repo" status --porcelain)" ]]; then
    log "$test: the checkout has local changes: provenance.json will not name a commit"
    unset GITHUB_REPOSITORY GITHUB_SHA
  fi

  log "$test: running $macro"
  if "$SCRIPTS/run-macro.sh" --sif "$tdir/simulation.sif" --macro "$tdir/repo/macro/$macro" \
       --work "$work" --g4data "$G4DATA" \
     && "$SCRIPTS/export-macro.sh" --sif "$tdir/simulation.sif" --repo "$tdir/repo" \
       --macro "$macro" --work "$work"; then
    echo "done" > "$work/status"
  else
    echo failed > "$work/status"
    die "$test: $macro failed (outputs and logs in $work/outputs)"
  fi
}

# ---------------------------------------------------------------------------- submit

cmd_submit() {
  local scheduler="" jobs=1 extra=() n
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) DIR="${2:-}"; shift 2 ;;
      -j|--jobs) jobs="${2:-}"; shift 2 ;;
      --) shift; extra=("$@"); break ;;
      local|slurm|condor) scheduler=$1; shift ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  [[ -n "$scheduler" ]] || die "submit: choose local, slurm or condor"
  [[ "$jobs" =~ ^[1-9][0-9]*$ ]] || die "invalid number of parallel jobs: $jobs"
  resolve_dir
  [[ -f "$DIR/jobs.txt" ]] || die "no $DIR/jobs.txt: run prepare first"
  n=$(grep -c . "$DIR/jobs.txt" || true)
  [[ "$n" -gt 0 ]] || die "no validation macros in $DIR/jobs.txt"
  if [[ "$scheduler" != local && "$DIR$SELF" =~ [[:space:]] ]]; then
    die "the run directory and ci-workflows must not contain spaces for batch jobs"
  fi
  mkdir -p "$DIR/logs"
  "submit_$scheduler" "$n" "$jobs" ${extra[@]+"${extra[@]}"}
}

submit_local() {
  local n=$1 jobs=$2
  if seq 1 "$n" | xargs -n 1 -P "$jobs" bash "$SELF" run --dir "$DIR"; then
    cmd_collect --dir "$DIR"
  else
    cmd_status --dir "$DIR"
    die "some macros failed; submit again to run only those not done"
  fi
}

submit_slurm() {
  local n=$1 run collect id cid
  shift 2
  run="$DIR/slurm-run.sh" collect="$DIR/slurm-collect.sh"
  # shellcheck disable=SC2016 # $SLURM_ARRAY_TASK_ID expands in the job
  printf '#!/bin/bash\n#SBATCH --job-name=g4med-run\n#SBATCH --output=%s/logs/run-%%A_%%a.log\nexec bash %s run --dir %s "$SLURM_ARRAY_TASK_ID"\n' \
    "$DIR" "$SELF" "$DIR" > "$run"
  printf '#!/bin/bash\n#SBATCH --job-name=g4med-collect\n#SBATCH --output=%s/logs/collect-%%j.log\nexec bash %s collect --dir %s\n' \
    "$DIR" "$SELF" "$DIR" > "$collect"
  id=$(sbatch --parsable --array="1-$n" "$@" "$run")
  id=${id%%;*}
  # afterany: collect runs also if some macros failed, and reports which.
  cid=$(sbatch --parsable --dependency="afterany:$id" "$@" "$collect")
  log "Slurm: array job $id ($n macros), collect job ${cid%%;*}; logs in $DIR/logs"
}

submit_condor() {
  local sub="$DIR/condor-run.sub"
  shift 2
  cat > "$sub" <<EOF
# One job per line of jobs.txt; the run directory is on a shared filesystem.
universe = vanilla
executable = /bin/bash
arguments = "$SELF run --dir $DIR \$(test) \$(id)"
transfer_executable = false
should_transfer_files = NO
output = $DIR/logs/\$(test)-\$(id).out
error = $DIR/logs/\$(test)-\$(id).err
log = $DIR/logs/condor.log
queue test,id,macro from $DIR/jobs.txt
EOF
  condor_submit "$@" "$sub"
  log "HTCondor: when the jobs finish, run: $SELF collect --dir $DIR"
}

# --------------------------------------------------------------------- collect, status

cmd_collect() {
  local tests=() failed=() t
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) DIR="${2:-}"; shift 2 ;;
      -*) die "unknown option: $1" ;;
      *) check_test_name "$1"; tests+=("$1"); shift ;;
    esac
  done
  resolve_dir
  if [[ ${#tests[@]} -eq 0 ]]; then
    for t in $(prepared_tests); do tests+=("$t"); done
  fi
  [[ ${#tests[@]} -gt 0 ]] || die "no prepared tests in $DIR"
  for t in "${tests[@]}"; do
    bash "$SELF" _collect "$DIR" "$t" || failed+=("$t")
  done
  [[ ${#failed[@]} -eq 0 ]] || die "not collected: ${failed[*]}"
}

collect_test() {
  DIR=$1
  local test=$2 tdir="$1/$2" missing=() id macro
  load_env "$test"
  if [[ ! -s "$tdir/jobs.txt" ]]; then
    log "$test: no validation macros"
    return 0
  fi
  while IFS="$TAB" read -r _ id macro; do
    [[ "$(status_of "$test" "$id")" == "done" ]] || missing+=("$macro ($(status_of "$test" "$id"))")
  done < "$tdir/jobs.txt"
  [[ ${#missing[@]} -eq 0 ]] || die "$test: not every macro succeeded: ${missing[*]}"

  rm -rf "$tdir/collect-input" "$tdir/validation-json"
  mkdir "$tdir/collect-input"
  while IFS="$TAB" read -r _ id _; do
    cp -R "$tdir/runs/$id/json" "$tdir/collect-input/$id"
  done < "$tdir/jobs.txt"
  use_tmp
  apptainer exec --unsquash -B "$TOOLS:/ci-tools:ro" -B "$tdir:/test" "$tdir/simulation.sif" \
    /opt/venv/bin/python3 /ci-tools/validation/export.py collect \
    --input /test/collect-input --output /test/validation-json
  rm -rf "$tdir/collect-input"
  log "$test: $(find "$tdir/validation-json/plots" -name '*.json' | wc -l | tr -d ' ') plots in $tdir/validation-json"
}

cmd_status() {
  local t id s total ok failed started pending results
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir) DIR="${2:-}"; shift 2 ;;
      *) die "unknown argument: $1" ;;
    esac
  done
  resolve_dir
  printf '%-24s %7s %5s %7s %8s %8s  %s\n' TEST MACROS DONE FAILED STARTED PENDING RESULTS
  for t in $(prepared_tests); do
    total=0 ok=0 failed=0 started=0 pending=0
    while IFS="$TAB" read -r _ id _; do
      total=$((total + 1))
      s=$(status_of "$t" "$id")
      case "$s" in
        done) ok=$((ok + 1)) ;;
        failed) failed=$((failed + 1)) ;;
        started) started=$((started + 1)) ;;
        *) pending=$((pending + 1)) ;;
      esac
    done < "$DIR/$t/jobs.txt"
    results=-
    if [[ -f "$DIR/$t/validation-json/results.json" ]]; then results=collected; fi
    printf '%-24s %7d %5d %7d %8d %8d  %s\n' "$t" "$total" "$ok" "$failed" "$started" "$pending" "$results"
  done
}

# ------------------------------------------------------------------------------ main

[[ $# -gt 0 ]] || { usage >&2; exit 1; }
command=$1
shift
case "$command" in
  prepare) cmd_prepare "$@" ;;
  unit) cmd_unit "$@" ;;
  run) cmd_run "$@" ;;
  submit) cmd_submit "$@" ;;
  collect) cmd_collect "$@" ;;
  status) cmd_status "$@" ;;
  _prepare) prepare_test "$@" ;;
  _collect) collect_test "$@" ;;
  -h|--help|help) usage ;;
  *) usage >&2; die "unknown command: $command" ;;
esac
