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
build ──┬── unit-test         (GitHub, ubuntu-24.04) ──┬── validation: one job per macro (Padova) ── collect-json
        └── unit-test-padova  (Padova)               ──┘
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

Padova jobs use their own temporary directories, so concurrent jobs on the shared
runner do not interfere, and need only Apptainer and CVMFS on the runner.

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
`plotType`, `histogram` or `chart`; histogram `nBins` is a one-element array). No
goodness-of-fit test or pass/fail threshold is applied to the physics.

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
- **`geant4-release.yml`**, when a new Geant4 version is published: it checks that
  `ghcr.io/g4med-test/geant4-alma9:<tag>` exists and starts `ci.yml` on the default
  branch of every listed test with that `geant4_tag`. Each full pipeline then appears
  in the test repository's Actions tab. `geant4-alma9` starts it after publishing a
  new version (not after a rebuild); it can also be started by hand:

  ```bash
  gh workflow run geant4-release.yml -R G4Med-test/ci-workflows -f geant4_tag=v11.4.3
  ```

`GITHUB_TOKEN` cannot start workflows in other repositories: both `geant4-alma9` and
this repository need a secret **`G4MED_DISPATCH_TOKEN`**, best an organization
secret, holding a fine-grained token (resource owner `G4Med-test`) or a GitHub App
token with **Actions: read and write** on `ci-workflows` and the test repositories.
Without it, `geant4-alma9` only prints a warning and `geant4-release.yml` fails with
an explicit error.

## Development

| Path | Content |
| --- | --- |
| `.github/workflows/` | `pipeline.yml` and the workflows it calls; `self-test.yml`, `geant4-release.yml` |
| `validation/export.py` | CLI: `matrix`, `export`, `collect` (`--help` for each) |
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
