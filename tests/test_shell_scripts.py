"""The bash scripts shared by the workflows and the runs outside GitHub Actions.

Apptainer is replaced by a stub that records its working directory and arguments and
prints $FAKE_STDOUT; the scripts run with the bash of the machine (3.2 on macOS).
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).parents[1] / "scripts"
STUB = """#!/bin/sh
{ pwd; for arg in "$@"; do echo "$arg"; done; } > "$FAKE_LOG"
printf '%s' "$FAKE_STDOUT"
exit "${FAKE_STATUS:-0}"
"""


class ScriptTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        (self.tmp / "bin").mkdir()
        (self.tmp / "bin/apptainer").write_text(STUB)
        (self.tmp / "bin/apptainer").chmod(0o755)
        (self.tmp / "g4data").mkdir()
        (self.tmp / "test.sif").write_text("")
        (self.tmp / "repo/macro").mkdir(parents=True)
        (self.tmp / "repo/macro/a.mac").write_text("/run/beamOn 1\n")
        (self.tmp / "repo/validation").mkdir()
        (self.tmp / "repo/validation/config.json").write_text('{"macros": ["a.mac"]}')
        self.env = dict(os.environ, PATH=f"{self.tmp / 'bin'}:{os.environ['PATH']}",
                        FAKE_LOG=str(self.tmp / "apptainer.log"), FAKE_STDOUT="", GITHUB_ACTIONS="")
        self.env.pop("G4DATA", None)

    def run_script(self, name, *args, **env):
        return subprocess.run(["bash", str(SCRIPTS / name), *map(str, args)], capture_output=True,
                              text=True, env=dict(self.env, **env), cwd=self.tmp)

    def apptainer_call(self):
        cwd, *args = (self.tmp / "apptainer.log").read_text().splitlines()
        return cwd, args


class RunMacroTests(ScriptTestCase):
    def run_macro(self, **env):
        return self.run_script("run-macro.sh", "--sif", "test.sif", "--macro", "repo/macro/a.mac",
                               "--work", "work", "--g4data", self.tmp / "g4data", **env)

    def test_runs_the_macro_copy_in_the_empty_outputs_directory(self):
        result = self.run_macro(FAKE_STDOUT="Run terminated.\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        work = self.tmp / "work"
        self.assertEqual(self.apptainer_call()[1], [
            "run", "--unsquash", "-B", f"{self.tmp}/g4data:/g4data:ro", "-B", f"{work}/macros:/macro:ro",
            "-B", f"{work}/outputs:/outputs", "--pwd", "/outputs", "test.sif", "/macro/a.mac"])
        self.assertEqual((work / "macros/a.mac").read_text(), "/run/beamOn 1\n")
        self.assertEqual((work / "outputs/test_stdout.txt").read_text(), "Run terminated.\n")
        self.assertTrue((work / "outputs/test_stderr.txt").exists())

    def test_geant4_errors_fail_the_run(self):
        result = self.run_macro(FAKE_STDOUT="*** Fatal Exception ***\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to export", result.stderr)

    def test_simulation_failure_fails_the_run(self):
        self.assertNotEqual(self.run_macro(FAKE_STATUS="3").returncode, 0)

    def test_refuses_a_used_outputs_directory(self):
        (self.tmp / "work/outputs").mkdir(parents=True)
        (self.tmp / "work/outputs/old.root").write_text("")
        result = self.run_macro()
        self.assertEqual(result.returncode, 1)
        self.assertIn("not empty", result.stderr)
        self.assertFalse((self.tmp / "apptainer.log").exists())

    def test_datasets_default_to_G4DATA(self):
        result = self.run_script("run-macro.sh", "--sif", "test.sif", "--macro", "repo/macro/a.mac",
                                 "--work", "work", G4DATA=str(self.tmp / "g4data"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"{self.tmp}/g4data:/g4data:ro", self.apptainer_call()[1])

    def test_errors_are_annotations_on_github(self):
        result = self.run_script("run-macro.sh", "--sif", "missing.sif", "--macro", "repo/macro/a.mac",
                                 "--work", "work", GITHUB_ACTIONS="true")
        self.assertEqual(result.returncode, 1)
        self.assertIn("::error::image not found: missing.sif", result.stderr)


class ExportMacroTests(ScriptTestCase):
    def test_exports_inside_the_image(self):
        (self.tmp / "work/outputs").mkdir(parents=True)
        result = self.run_script("export-macro.sh", "--sif", "test.sif", "--repo", "repo",
                                 "--macro", "a.mac", "--work", "work")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.apptainer_call()[1], [
            "exec", "--unsquash", "-B", f"{self.tmp}/repo:/validation:ro",
            "-B", f"{SCRIPTS.parent.resolve()}:/ci-tools:ro", "-B", f"{self.tmp}/work:/work",
            "--pwd", "/validation", "test.sif", "/opt/venv/bin/python3", "/ci-tools/validation/export.py",
            "export", "--repo", "/validation", "--config", "validation/config.json", "--macro", "a.mac",
            "--input", "/work/outputs", "--output", "/work/json"])

    def test_refuses_an_existing_output(self):
        (self.tmp / "work/outputs").mkdir(parents=True)
        (self.tmp / "work/json").mkdir()
        result = self.run_script("export-macro.sh", "--sif", "test.sif", "--repo", "repo",
                                 "--macro", "a.mac", "--work", "work")
        self.assertEqual(result.returncode, 1)
        self.assertIn("already exists", result.stderr)


class RunUnitTests(ScriptTestCase):
    def test_runs_in_the_outputs_directory_with_the_macro_path(self):
        result = self.run_script("run-unit.sh", "--sif", "test.sif", "--macro", "repo/macro/a.mac",
                                 "--work", "work", "--g4data", self.tmp / "g4data")
        self.assertEqual(result.returncode, 0, result.stderr)
        cwd, args = self.apptainer_call()
        macro_dir = self.tmp / "repo/macro"
        self.assertEqual(Path(cwd).resolve(), self.tmp / "work/outputs")
        self.assertEqual(args, [
            "run", "--unsquash", "-B", f"{self.tmp}/g4data:/g4data:ro", "-B", f"{macro_dir}:{macro_dir}:ro",
            "-B", f"{self.tmp}/work/outputs:/outputs", f"{self.tmp}/test.sif", f"{macro_dir}/a.mac"])


class PublishResultsTests(ScriptTestCase):
    def collected(self, version, plots=("p1",)):
        out = Path(tempfile.mkdtemp(dir=self.tmp))
        (out / "plots").mkdir()
        (out / "results.json").write_text(json.dumps([version]))
        for plot in plots:
            (out / f"plots/{plot}.json").write_text("{}")
        provenance = {"test_repo": {"url": "https://github.com/G4Med-test/T", "sha": "abc"},
                      "container_repo": None, "image": None, "geant4_version": version}
        (out / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        return out

    def publish(self, collected):
        return self.run_script("publish-results.sh", "--input", collected, "--results", "results", "--test", "T")

    def test_replaces_the_latest_results_and_those_of_the_version(self):
        (self.tmp / "results").mkdir()
        self.assertEqual(self.publish(self.collected("11.3.2", plots=("old",))).stdout, "11.3.2\n")
        result = self.publish(self.collected("11.4.0"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "11.4.0\n")
        test = self.tmp / "results/T"
        self.assertEqual(sorted(p.name for p in test.iterdir()), ["plots", "provenance.json", "results.json", "versions"])
        self.assertEqual(json.loads((test / "results.json").read_text()), ["11.4.0"])
        self.assertEqual([p.name for p in (test / "plots").iterdir()], ["p1.json"])
        self.assertEqual(sorted(p.name for p in (test / "versions").iterdir()), ["11.3.2", "11.4.0"])
        self.assertEqual([p.name for p in (test / "versions/11.3.2/plots").iterdir()], ["old.json"])

        result = self.publish(self.collected("11.3.2", plots=("new",)))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p.name for p in (test / "versions/11.3.2/plots").iterdir()], ["new.json"])
        self.assertEqual(json.loads((test / "versions/11.4.0/results.json").read_text()), ["11.4.0"])

    def test_rejects_a_missing_or_unexpected_version(self):
        (self.tmp / "results").mkdir()
        for version in (None, "../11.3.2", "main"):
            collected = self.collected("x")
            prov = json.loads((collected / "provenance.json").read_text())
            prov["geant4_version"] = version
            (collected / "provenance.json").write_text(json.dumps(prov))
            result = self.publish(collected)
            self.assertEqual(result.returncode, 1, version)
            self.assertIn("Unexpected Geant4 version", result.stderr)
        self.assertEqual(list((self.tmp / "results").iterdir()), [])

    def test_rejects_a_test_name_that_is_a_path(self):
        (self.tmp / "results").mkdir()
        result = self.run_script("publish-results.sh", "--input", self.collected("11.3.2"),
                                 "--results", "results", "--test", "../T")
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid test name", result.stderr)


if __name__ == "__main__": unittest.main()
