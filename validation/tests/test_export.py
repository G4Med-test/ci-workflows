"""Integration/regression tests with the three test repositories as siblings.

Run: python3 -m unittest discover -s ci-workflows/validation/tests -v
Set G4MED_WORKSPACE if the repositories are elsewhere. Legacy regression tests
additionally use the optional geant-config-generator checkout in that workspace.
"""
import contextlib
import importlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
import uproot
from uproot.writing.identify import to_TH1x, to_TAxis

TOOLS = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("G4MED_WORKSPACE", TOOLS.parents[1]))
sys.path.insert(0, str(TOOLS))
import export
from geantval import read_macro

LEGACY = WORKSPACE / "geant-config-generator"
sys.path.insert(0, str(LEGACY))


def load(repo):
    return export.load_parser(WORKSPACE / repo)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def cccs(self):
        # Format emitted by CCCStest/src/Run.cc, including isotope and summary rows.
        (self.path / "test_stdout.txt").write_text(
            "Geant4 startup\n"
            "Li Li6: 25 MeanFreePath= 100 mm CrossSection= 40 [millibarn]\n"
            "Be Be7: 4 MeanFreePath= 100 mm CrossSection= 20 [millibarn]\n"
            "Total 100 800 [millibarn]\nLi 25 40 [millibarn]\nBe 4 20 [millibarn]\nB 9 30 [millibarn]\n")
        parser = load("CCCStest")
        job = parser.metadata(read_macro(WORKSPACE / "CCCStest/macro/test.mac"))
        job.update(path=str(self.path), VERSION="11.3.2")
        with contextlib.redirect_stdout(io.StringIO()):
            result = list(parser.parse(job))
        return job, result

    def attenuation(self):
        parser = load("Attenuation-ilantest")
        macro = WORKSPACE / "Attenuation-ilantest/macro/run_total_attenuation_water_livermore.mac"
        job = parser.metadata(read_macro(macro))
        job.update(path=str(self.path), VERSION="11.3.2")
        (self.path / "AttenuationCoefficient.out").write_text("energy\tvalue\n" +
            "".join("%g 0.125\n" % e for e in job["ENERGIES"]))
        with contextlib.redirect_stdout(io.StringIO()):
            result = list(parser.parse(job))
        return job, result

    def lowefrag(self):
        parser = load("LowEFrag")
        job = parser.metadata(read_macro(WORKSPACE / "LowEFrag/macro/bic.mac"))
        job.update(path=str(self.path), VERSION="11.3.2")
        axes = {}
        with uproot.recreate(self.path / job["OUTPUT"]) as root:
            for a, z, angle, _, n, low, high in parser.binParams:
                name = "h%s%d_%g" % (parser.SYMBOLS[z], a, angle)
                axes[name] = (n, low, high)
                values, variances = np.zeros(n + 2), np.zeros(n + 2)
                # Weighted first bin: sumw=9, sumw2=25. Flow bins are excluded.
                values[0], values[1], values[-1] = 100., 9., 200.
                variances[0], variances[1], variances[-1] = 100., 25., 200.
                root[name] = to_TH1x(
                    fName=name, fTitle=name, data=values, fEntries=304.,
                    fTsumw=9., fTsumw2=25., fTsumwx=0., fTsumwx2=0.,
                    fSumw2=variances,
                    fXaxis=to_TAxis("xaxis", "", n, low, high))
        return job, list(parser.parse(job)), axes

    def test_cccs_normalization_and_uncertainties(self):
        _, records = self.cccs()
        self.assertEqual(len(records), 8)
        hist = records[0]["histogram"]
        self.assertEqual(hist["nBins"], [4])
        self.assertEqual(hist["binContent"], [200., 40., 20., 30.])
        self.assertEqual(hist["yStatErrorsPlus"], [20., 8., 10., 10.])
        lithium = next(r for r in records if r["metadata"]["secondaryParticle"] == "Li")
        self.assertEqual(lithium["histogram"]["binContent"][2], 40.)
        for record in records:
            export.validate_record(record)

    def test_missing_and_repeated_cccs_summaries_fail(self):
        parser = load("CCCStest")
        path = self.path / "stdout.txt"
        for content in ("Startup only\n", "Total 1 1 [millibarn]\nTotal 2 2 [millibarn]\n"):
            path.write_text(content)
            with self.assertRaises(ValueError):
                parser.read_stdout(path)

    def test_cccs_requires_isotope_printing(self):
        parser = load("CCCStest")
        commands = read_macro(WORKSPACE / "CCCStest/macro/test.mac")
        with self.assertRaises(ValueError):
            parser.metadata([c for c in commands if c[0] != "/testhadr/run/printStat"])

    def test_attenuation_incomplete_scan_fails(self):
        job, _ = self.attenuation()
        (self.path / "AttenuationCoefficient.out").write_text("energy value\n0.001 1\n")
        with self.assertRaisesRegex(ValueError, "Incomplete"), contextlib.redirect_stdout(io.StringIO()):
            list(load("Attenuation-ilantest").parse(job))

    def test_attenuation_energy_mismatch_fails(self):
        job, _ = self.attenuation()
        path = self.path / "AttenuationCoefficient.out"
        path.write_text(path.read_text().replace("0.001 0.125", "0.002 0.125"))
        with self.assertRaisesRegex(ValueError, "energies"), contextlib.redirect_stdout(io.StringIO()):
            list(load("Attenuation-ilantest").parse(job))

    def test_attenuation_process_from_macro(self):
        parser = load("Attenuation-ilantest")
        self.assertEqual(self.attenuation()[0]["PROCESS"], "total")
        compton = read_macro(WORKSPACE / "Attenuation-ilantest/macro/run_compton_attenuation_water_opt3.in")
        self.assertEqual(parser.metadata(compton)["PROCESS"], "compton")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            parser.metadata([c for c in compton if c[1] != "phot gamma"])

    def test_lowefrag_output_name_from_macro(self):
        parser = load("LowEFrag")
        self.assertEqual(self.lowefrag()[0]["OUTPUT"], "bic.root")
        self.assertEqual(parser.output_name("unit"), "unit.root")
        for value in ("/tmp/bic.root", "out/bic.root", "/outputs/bic.xml"):
            with self.assertRaises(ValueError):
                parser.output_name(value)

    def test_config_must_list_macros(self):
        for config in ({"macros": {"test.mac": {}}}, {"macros": []}, {"macros": ["a.mac", "a.mac"]}):
            path = self.path / "config.json"
            path.write_text(json.dumps(config))
            result = subprocess.run([sys.executable, str(TOOLS / "export.py"), "matrix", "--repo",
                                     str(WORKSPACE / "CCCStest"), "--config", str(path)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_lowefrag_normalization_weighted_errors_and_flow(self):
        job, records, _ = self.lowefrag()
        self.assertEqual(len(records), 54)
        hist = records[0]["histogram"]
        omega = 2 * math.pi * (math.cos(math.radians(9.9)) - math.cos(math.radians(12.9)))
        scale = 1051.9 / job["NEVENTS"] / omega / 10
        self.assertAlmostEqual(hist["binContent"][0], 9 * scale)
        self.assertAlmostEqual(hist["yStatErrorsPlus"][0], 5 * scale)
        self.assertEqual(hist["binContent"][1:], [0.] * 17)
        for record in records:
            export.validate_record(record)

    def test_lowefrag_incomplete_output_fails(self):
        job, _, _ = self.lowefrag()
        with uproot.update(self.path / job["OUTPUT"]) as root:
            del root["hH1_11.4"]
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            list(load("LowEFrag").parse(job))

    def test_nonfinite_and_negative_errors_rejected(self):
        _, records = self.cccs()
        hist = records[0]["histogram"]
        hist["yStatErrorsPlus"][0] = -1
        with self.assertRaises(ValueError):
            export.validate_record(records[0])
        hist["yStatErrorsPlus"][0] = 1
        hist["binContent"][0] = math.inf
        with self.assertRaises(ValueError):
            export.validate_record(records[0])

    def test_getjson_rejects_unknown_arguments(self):
        from geantval import getJSON
        with self.assertRaisesRegex(TypeError, "xAxisname"):
            getJSON({}, "chart", xValues=[1], yValues=[1], xAxisname="E")
        with self.assertRaisesRegex(TypeError, "xValues"):  # Chart field in a histogram.
            getJSON({}, "histogram", binEdgeLow=[0], binEdgeHigh=[1], binContent=[1], xValues=[1])
        with self.assertRaises(ValueError):
            getJSON({}, "graph")

    def test_invalid_record_error_names_the_plot(self):
        _, records = self.cccs()
        records[0]["histogram"]["binContent"].pop()
        with self.assertRaisesRegex(ValueError, r"fragments production cross section.*binContent has 3 values, expected 4"):
            export.validate_record(records[0])

    def test_export_and_collection_cli(self):
        _, records = self.cccs()
        output = self.path / "artifacts/one"
        command = [sys.executable, str(TOOLS / "export.py"), "export", "--repo", str(WORKSPACE / "CCCStest"),
                   "--macro", "test.mac", "--input", str(self.path), "--version", "11.3.2", "--output", str(output)]
        subprocess.run(command, check=True, capture_output=True)
        self.assertEqual(json.loads((output / "results.json").read_text()), records)
        self.assertEqual(len(list((output / "plots").glob("*.json"))), 8)
        final = self.path / "final"
        subprocess.run([sys.executable, str(TOOLS / "export.py"), "collect", "--input", str(output.parent),
                        "--output", str(final)], check=True, capture_output=True)
        self.assertEqual(json.loads((final / "results.json").read_text()), records)

    def test_version_from_geant4_config(self):
        self.cccs()
        bin_dir = self.path / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "geant4-config"
        fake.write_text("#!/bin/sh\necho 11.4.3\n")
        fake.chmod(0o755)
        output = self.path / "json"
        command = [sys.executable, str(TOOLS / "export.py"), "export", "--repo", str(WORKSPACE / "CCCStest"),
                   "--macro", "test.mac", "--input", str(self.path), "--output", str(output)]
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"])
        subprocess.run(command, check=True, capture_output=True, env=env)
        self.assertEqual(json.loads((output / "job.json").read_text())["VERSION"], "11.4.3")
        env["PATH"] = os.pathsep.join(p for p in os.environ["PATH"].split(os.pathsep)
                                      if not (Path(p) / "geant4-config").exists())
        result = subprocess.run(command[:-1] + [str(self.path / "json2")], capture_output=True, text=True, env=env)
        self.assertIn("geant4-config not found", result.stderr)

    def test_empty_collection_fails(self):
        result = subprocess.run([sys.executable, str(TOOLS / "export.py"), "collect", "--input", str(self.path),
                                 "--output", str(self.path / "final")], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.path / "final").exists())

    @unittest.skipUnless(LEGACY.exists(), "Legacy checkout required for regression")
    def test_legacy_cccs_and_attenuation_equal(self):
        for name, setup in (("CCCStest", self.cccs), ("attenuation", self.attenuation)):
            job, records = setup()
            module = importlib.import_module("tests.geant4.%s.parser" % name)
            with contextlib.redirect_stdout(io.StringIO()):
                old = list(module.Test("").parse([job]))
            self.assertEqual(records, old)

    @unittest.skipUnless(LEGACY.exists(), "Legacy checkout required for regression")
    def test_legacy_lowefrag_equal(self):
        if importlib.util.find_spec("ROOT") is None:
            self.skipTest("PyROOT required to compare both readers on the same ROOT file")
        job, records, _ = self.lowefrag()
        (self.path / "output.root").symlink_to(job["OUTPUT"])  # Legacy fixed file name.
        module = importlib.import_module("tests.geant4.LowEFrag.parser")
        with contextlib.redirect_stdout(io.StringIO()):
            old = list(module.Test("").parse([job]))
        self.assertEqual(len(records), len(old))
        # Both readers consume the same ROOT file. Float operation ordering may differ.
        for actual, expected in zip(records, old):
            for key in ("binEdgeLow", "binEdgeHigh", "binContent", "yStatErrorsPlus", "yStatErrorsMinus"):
                for a, b in zip(actual["histogram"][key], expected["histogram"][key]):
                    self.assertTrue(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12))
                actual["histogram"][key] = expected["histogram"][key]
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
