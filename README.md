# ci-workflows

Reusable GitHub Actions workflows for the G4Med Geant4 validation tests: they build
the test's Apptainer image, run its unit macro, run its validation macros on the
Padova runners and export the plots in the
[Geant Validation Portal](https://geant-val.cern.ch/) JSON format.

New tests start from [G4Med-test/template](https://github.com/G4Med-test/template),
which already contains everything described here.

## Using the pipeline

The test repository's `.github/workflows/ci.yml`:

```yaml
on:
  push:
  pull_request:
  workflow_dispatch:
    inputs:
      geant4_tag:
        description: geant4-alma9 tag to build with (empty = TAG default in Apptainer.def)
        default: ""
        type: string

jobs:
  run-pipeline:
    uses: G4Med-test/ci-workflows/.github/workflows/pipeline.yml@main
    permissions:
      contents: read
      packages: write
    with:
      geant4_tag: ${{ inputs.geant4_tag }}
```

| `pipeline.yml` input | Default | Meaning |
| --- | --- | --- |
| `apptainer_def` | `Apptainer.def` | Definition file of the test image |
| `macro_file` | `macro/unit.mac` | Unit macro, run on GitHub and on Padova |
| `geant4_tag` | empty | `geant4-alma9` tag; empty uses the `TAG` default of `Apptainer.def` |
| `validation_config` | `validation/config.json` | Validation macros; validation is skipped if absent |
| `validation_tools_ref` | `main` | ci-workflows ref of the exporter: keep it equal to the `uses:` ref |

## What runs

```text
build ──┬── unit-test         (GitHub, ubuntu-24.04) ──┬── validation: one job per macro (Padova) ── collect-json ── publish-results
        ├── unit-test-padova  (Padova)               ──┘
        └── prune-images                                                              notify (last, always)
```

- **build** (`apptainer-build-deploy.yml`) builds `Apptainer.def` on top of
  [`ghcr.io/g4med-test/geant4-alma9`](https://github.com/G4Med-test/geant4-alma9),
  whose tags are the Geant4 tags and whose environment the test image inherits, and
  pushes `oras://ghcr.io/<owner>/<repo>:<commit SHA>`, or `<commit SHA>-<geant4_tag>`
  when a Geant4 version is requested. The test jobs use that reference.
- **unit-test** (`run-unit.yml`) runs the unit macro on GitHub, with the Geant4
  datasets downloaded once per Geant4 version and cached.
- **unit-test-padova** (`run-unit-padova.yml`) runs it on Padova, with the datasets
  from CVMFS.
- **validation** (`run-validation-padova.yml`) runs after both unit tests, as
  described below.
- **prune-images** keeps the test's images in GHCR in check (default branch only, see
  [Old images](#old-images)).
- **notify**, last, starts the dashboard update and, for a run started by a Geant4
  validation, `release-queue.yml`. It needs the `G4MED_DISPATCH_TOKEN` secret (passed
  by `secrets: inherit`) and does nothing without it.

Padova jobs use their own temporary directories, so concurrent jobs on the shared
runner do not interfere, and need only Apptainer and CVMFS on the runner.

### Only reviewed code runs on Padova

| Event | build | unit-test (GitHub) | unit-test-padova, validation |
| --- | --- | --- | --- |
| pull request (branch or fork) | yes, nothing pushed: the amd64 SIF is an artifact of the run | yes | skipped |
| push / `workflow_dispatch` on the default branch | yes, pushed to GHCR | yes | yes |
| push / `workflow_dispatch` on another branch | yes, pushed to GHCR | yes | skipped |

A developer opens a pull request; GitHub builds the image and runs the unit macro.
Once someone with write access approves and merges it, the push on the default
branch runs the whole pipeline, Padova included. The check is in
`run-unit-padova.yml` and `run-validation-padova.yml` themselves, so a test's
`ci.yml` cannot skip it by calling them directly.

This relies on the default branch accepting only approved pull requests:
`scripts/protect-repos.sh` sets that ruleset on ci-workflows and on every test in
`tests.json` (or on the repositories given as arguments). Run it again after adding
a test.

## Validation and portal JSON

The test repository provides two files (see the template for a documented example):

- `validation/config.json`: `{"macros": ["a.mac", ...]}`, paths relative to `macro/`.
- `validation/parser.py`, with two functions:
  - `metadata(commands)` receives one macro as `[(command, value), ...]` and returns
    a dict with at least `TEST`; every setting is read from the macro.
  - `parse(job)` yields plots built with `geantval.getJSON`. `job` is the metadata
    plus `path` (the run directory) and `VERSION` (the Geant4 version).

`validation/geantval.py` provides `getJSON`, `one_command`, `single_run` and
`energy_mev`. `getJSON` rejects arguments that do not exist for the plot type.

For each macro, one job:

1. runs it unchanged in an empty directory, bound at `/outputs` and used as working
   directory, with the datasets at `/g4data`. Relative and `/outputs/...` file names
   land there; stdout/stderr are saved as `test_stdout.txt`/`test_stderr.txt`, and
   Geant4 errors in them fail the job. Macros must be self-contained (no
   `/control/execute`, loops or aliases);
2. runs `validation/export.py export` inside the image, which provides Python with
   NumPy and uproot (no ROOT) and `geant4-config` for the version;
3. checks every plot (array lengths, edges, uncertainties, no NaN/Infinity; errors
   name the plot) and uploads `validation-json-<id>` with `results.json`,
   `plots/<md5>.json` and `job.json` (the parser input), plus `validation-raw-<id>`
   with the outputs, logs and macro, also when parsing fails.

`collect-json` runs when all macros succeeded and uploads **`validation-json`**:

- `results.json`: all plots of all macros, as one array;
- `plots/<md5>.json`: one plot per file, named as the original `geant-config-generator`.

Each plot keeps the original format (`article`, `mctool`, `testName`, `metadata`,
`plotType`, `histogram` or `chart`; histogram `nBins` is a one-element array).

`publish-results` (default branch only) opens and merges a pull request in
[validation-results](https://github.com/G4Med-test/validation-results) that writes
`validation-json` both to `<test>/` (the latest results, whatever their Geant4 version)
and to `<test>/versions/<Geant4 version>/` (the latest results of each version).

### Comparing Geant4 versions

`validation/compare.py` compares the plots of a test between two versions. Plots are
matched by everything but the Geant4 version (test, type, model, metadata, title,
axes) and each pair is:

| Status | Meaning |
| --- | --- |
| same | identical values |
| compatible | chi2 of the differences, with the uncertainties of both versions (stat ⊕ syst), has p ≥ 0.01; points without uncertainties differ by at most 5% |
| changed | p < 0.01, or a point without uncertainties differs by more than 5% |
| incomparable | bins or x values differ |
| new / removed | the plot exists in one version only |

It is not a pass/fail judgement on the physics: a change between two Geant4 versions
can be intended. It points at the plots to look at, and its thresholds are options:

```bash
python3 ci-workflows/validation/compare.py validation-results/LowEFrag/versions/{11.3.2,11.4.3}
```

The release report and the dashboard use it with the previous version that has
results.

To run all of this locally (build or download the image, datasets, simulation,
`matrix` and `export`), see the template's README.

## Test repositories: `tests.json`

`tests.json` lists the integrated test repositories, each with the ref checked by
the self-test (a branch, or a pinned commit while a test is broken):

```json
{"tests": [{"repo": "G4Med-test/LowEFrag", "ref": "main"}]}
```

To integrate a new test, add it here with a pull request. Two workflows use it:

- **`self-test.yml`**, on every push and pull request of this repository: actionlint;
  for every listed repository, `export.py matrix` (config, macros, `metadata()`) and
  its own `validation/tests`, if any, with the exporter of this commit; the regression
  suite in `validation/tests`; the template's configuration. It needs no secrets.
- **`geant4-release.yml`** validates one Geant4 tag of
  [Geant4/geant4](https://github.com/Geant4/geant4/tags) with the listed tests; see
  [Validating a Geant4 version](#validating-a-geant4-version).

## Validating a Geant4 version

`geant4-alma9` starts `geant4-release.yml` after publishing a new version (not after a
rebuild). Maintainers (write access to this repository) start it for any version from
the [dashboard](https://github.com/G4Med-test/dashboard)'s *Geant4 versions* page, or:

```bash
gh workflow run geant4-release.yml -R G4Med-test/ci-workflows -f geant4_tag=v11.4.3
# only some tests, e.g. those that failed, and at most 2 at a time:
gh workflow run geant4-release.yml -R G4Med-test/ci-workflows -f geant4_tag=v11.4.3 \
  -f tests=LowEFrag,CCCStest -f max_parallel=2
```

Each validated version is an issue of this repository, **Geant4 &lt;tag&gt; validation**
(label `geant4-release`), kept up to date by `scripts/release.py`: a table with the
state, median and duration of every test, and the state as JSON for the dashboard. Do
not edit it.

1. `geant4-release.yml` checks the tag. If `ghcr.io/g4med-test/geant4-alma9:<tag>` is
   missing, it starts its build and the issue waits for it; `geant4-alma9` starts the
   workflow again once the image is published. If the build disappears (for example
   cancelled by the hourly run of `geant4-alma9`, which shares its concurrency group)
   it is requested again, up to 3 times; then the issue reports the failure and closes.
2. The tests are queued in ascending order of the **median duration** of their last 15
   successful runs on the default branch (fastest first, unknown last), and at most
   `max_parallel` (default 3) run at the same time, so that the Padova runner is not
   flooded by 20 pipelines at once.
3. `release-queue.yml` starts the next test when one finishes: the last job of each
   pipeline starts it, and it also runs every 15 minutes in case a start is lost.
4. When every test has finished it comments with the **report** (result, duration and
   the comparison of each test with its previous Geant4 version), mentioning whoever
   asked for the validation, and closes the issue. Watching this repository, or the
   issue, gives the notification too.

A new request for a version being validated leaves it alone, unless it names tests:
those that have finished run again (that is the dashboard's *Rerun failed*). A request
for a finished version starts it again.

`GITHUB_TOKEN` cannot start workflows in other repositories: both `geant4-alma9` and
this repository need a secret **`G4MED_DISPATCH_TOKEN`**, best an organization
secret, holding a fine-grained token (resource owner `G4Med-test`) or a GitHub App
token with **Actions: read and write** on `ci-workflows`, `geant4-alma9` and the test
repositories, plus `dashboard` for the pipeline's `notify` job. The secret must be
available to the test repositories too (organization secret, visibility "all" or
the selected tests). Without it, `geant4-alma9` only prints a warning,
`geant4-release.yml` fails with an explicit error and `notify` does nothing (the
dashboard and the queue then update on their schedule).

## Old images

Every pipeline run on the default branch pushes three versions (two architectures and
the index) to `ghcr.io/g4med-test/<test>`. `prune-images` (`scripts/prune_images.py`)
keeps the 10 newest builds, those younger than 14 days and those of the results
published in validation-results (`provenance.json` of `<test>/` and of every
`versions/<version>/`), and deletes the rest and old untagged versions.

It **deletes only when the organization variable `G4MED_PRUNE_IMAGES` is `true`**;
until then each run lists what it would delete. Each test repository needs the Admin
role on its own package (*package settings → Manage Actions access*), which the
repository that first pushed it normally has; otherwise the job only warns.

## Development

| Path | Content |
| --- | --- |
| `.github/workflows/` | `pipeline.yml` and the workflows it calls; `self-test.yml`, `geant4-release.yml`, `release-queue.yml` |
| `validation/export.py` | CLI: `matrix`, `export`, `collect` (`--help` for each) |
| `validation/compare.py` | Comparison of the plots of two versions (standard library only) |
| `scripts/release.py` | Queue and report of Geant4 validations |
| `scripts/prune_images.py` | Pruning of old test images |
| `scripts/seed_versions.py` | One-off: fills `versions/` of validation-results from its history |
| `scripts/sync-ci-paths-ignore.py` | One-off: pull requests adding the template's `paths-ignore` to every test's `ci.yml` |
| `scripts/protect-repos.sh` | Ruleset of the default branches (see above) |
| `tests/` | Tests of `scripts/`, run by `self-test.yml` |
| `validation/geantval.py` | Portal format (`getJSON`) and macro helpers |
| `validation/tests_list.py` | Reads and checks `tests.json` |
| `validation/tests/` | Regression suite |

Run the suite with the test repositories checked out next to ci-workflows (or set
`G4MED_WORKSPACE`), after `pip install -r ci-workflows/validation/requirements.txt`
(the same pins as the base image):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ci-workflows/validation/tests -v
```

If `geant-config-generator` is also checked out, the suite compares the CCCStest and
Attenuation plots with its original parsers, and LowEFrag too when PyROOT is
installed. The data are synthetic: the suite does not replace a Geant4 run.

To try a branch of ci-workflows, point both the test's `uses: ...pipeline.yml@<ref>`
and `validation_tools_ref: <ref>` to it: a reusable workflow cannot know the ref it
was called with. For reproducible runs, pin both to a commit.

The exporter and `getJSON` come from `geant-config-generator` (commit
`0bf42953c9c98ac6ecccf077e7c7fe2c4ceb7307`); each test's `validation/README.md`
records where its parser comes from and which original conventions it keeps.
