#!/usr/bin/env python3
"""Run repository-owned parsers and serialize the legacy portal JSON format."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from geantval import read_macro


def load_parser(repo):
    path = repo / "validation/parser.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("validation_parser", path)
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    return parser


def geant4_version():
    """Version of the Geant4 in this environment: run the export inside the test image."""
    try:
        return subprocess.run(["geant4-config", "--version"], check=True,
                              capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        raise SystemExit("geant4-config not found: run inside the test container or pass --version")


def validate_record(record):
    """Check one portal record; errors name the plot (title and secondary particle)."""
    data = record.get("histogram", record.get("chart", {}))
    where = "plot %r (%s)" % (data.get("title"), record.get("metadata", {}).get("secondaryParticle"))

    def fail(message):
        raise ValueError(where + ": " + message)

    if set(record) != {"article", "mctool", "testName", "metadata", "plotType",
                       "histogram" if record["plotType"] == "TH1" else "chart"}:
        fail("unexpected top-level keys %s" % sorted(record))
    if record["plotType"] == "TH1":
        n, = data["nBins"]
        fields = ("binEdgeLow", "binEdgeHigh", "binContent")
        if any(lo >= hi for lo, hi in zip(data["binEdgeLow"], data["binEdgeHigh"])):
            fail("binEdgeLow must be below binEdgeHigh in every bin")
    elif record["plotType"] == "SCATTER2D":
        n = data["nPoints"]
        fields = ("xValues", "yValues")
    else:
        fail("unsupported plotType %r" % record["plotType"])
    if n <= 0:
        fail("no points or bins")
    for key in fields:
        if len(data[key]) != n:
            fail("%s has %d values, expected %d" % (key, len(data[key]), n))
    for key, values in data.items():
        if "Errors" in key:
            if len(values) not in (0, n):
                fail("%s has %d values, expected 0 or %d" % (key, len(values), n))
            if any(v < 0 for v in values):
                fail(key + " has negative values")
    if data.get("binLabel") and len(data["binLabel"]) != n:
        fail("binLabel has %d labels, expected %d" % (len(data["binLabel"]), n))
    # Strict JSON rejects NaN/Infinity from failed/undersampled simulations.
    try:
        json.dumps(record, allow_nan=False)
    except ValueError:
        fail("contains NaN or Infinity")


def write_results(records, output):
    if not records:
        raise ValueError("Parser returned no records")
    for record in records:
        validate_record(record)
    output.mkdir(parents=True, exist_ok=False)
    plots = output / "plots"
    plots.mkdir()
    for record in records:
        # Same sorted-top-level MD5 naming convention as gts.utils.get_hashed_path.
        digest = hashlib.md5(json.dumps(dict(sorted(record.items()))).encode()).hexdigest()
        (plots / (digest + ".json")).write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    (output / "results.json").write_text(json.dumps(records, indent=2, allow_nan=False) + "\n")


def load_jobs(repo, config):
    """metadata() of every configured macro, checking the configuration."""
    macros = json.loads((repo / config).read_text())["macros"]
    if not isinstance(macros, list) or not macros or len(set(macros)) != len(macros):
        raise ValueError("config 'macros' must be a non-empty list of distinct macro paths")
    parser = load_parser(repo)
    jobs = {}
    for macro in macros:
        macro_path = (repo / "macro" / macro).resolve()
        if not macro_path.is_relative_to(repo / "macro"):
            raise ValueError("Macro must be inside macro/: " + macro)
        jobs[macro] = parser.metadata(read_macro(macro_path))
        if not jobs[macro].get("TEST"):
            raise ValueError(macro + ": metadata() must set TEST")
    return parser, jobs


def matrix(args):
    _, jobs = load_jobs(args.repo.resolve(), args.config)
    print(json.dumps({"include": [{"macro": m, "id": hashlib.sha256(m.encode()).hexdigest()[:16]}
                                  for m in jobs]}))


def export(args):
    parser, jobs = load_jobs(args.repo.resolve(), args.config)
    if args.macro not in jobs:
        raise SystemExit("%s is not listed in %s" % (args.macro, args.config))
    version = (args.version or geant4_version()).strip()
    if not version:
        raise ValueError("Empty Geant4 version")
    job = dict(jobs[args.macro], path=str(args.input.resolve()), VERSION=version)
    records = list(parser.parse(job))
    write_results(records, args.output)
    (args.output / "job.json").write_text(json.dumps(job, indent=2) + "\n")
    print("Exported %d plots to %s" % (len(records), args.output))


def collect(args):
    records = []
    for path in sorted(args.input.glob("*/results.json")):
        records.extend(json.loads(path.read_text()))
    write_results(records, args.output)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)

    def command(name, function, help):
        sub = commands.add_parser(name, help=help, description=help)
        sub.set_defaults(function=function)
        return sub

    def repository(sub):
        sub.add_argument("--repo", type=Path, default=Path("."), help="test repository (default: .)")
        sub.add_argument("--config", default="validation/config.json",
                         help="validation config, relative to --repo (default: %(default)s)")

    sub = command("matrix", matrix, "check the config and metadata() of every macro; "
                  "print the CI job matrix")
    repository(sub)
    sub = command("export", export, "run parse() on the output of one macro and write portal JSON")
    repository(sub)
    sub.add_argument("--macro", required=True, help="macro listed in the config")
    sub.add_argument("--input", type=Path, required=True, help="run directory with the outputs")
    sub.add_argument("--output", type=Path, required=True, help="new directory for the JSON files")
    sub.add_argument("--version", help="Geant4 version (default: geant4-config --version)")
    sub = command("collect", collect, "merge the results.json of every exported macro")
    sub.add_argument("--input", type=Path, required=True, help="directory of export outputs")
    sub.add_argument("--output", type=Path, required=True, help="new directory for the merged JSON")

    args = cli.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
