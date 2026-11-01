"""scripts/local-pipeline.sh, end to end on a synthetic test repository.

The test repository is cloned from a local git repository. Apptainer is replaced by a
stub that maps the bind mounts back to host paths: `run` writes a result file in the
working directory, and the Python of the image is the Python running these tests, so
export.py (which needs only the standard library with this parser) really runs.
sbatch and condor_submit are stubs that record their arguments.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
PIPELINE = TOOLS / "scripts/local-pipeline.sh"

APPTAINER = r'''#!PYTHON
import json, os, subprocess, sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"cwd": os.getcwd(), "args": args}) + "\n")
command = args.pop(0)
if command == "pull":
    sif, ref = [a for a in args if a != "--force"]
    if ref in os.environ.get("FAKE_MISSING", "").split():
        sys.exit("FATAL: no such image")
    Path(sif).write_text(ref)
elif command == "build":
    Path(args[-2]).write_text("built")
else:
    binds, pwd = [], None
    while args[0].startswith("-"):
        option = args.pop(0)
        if option == "-B":
            src, dst = args.pop(0).split(":")[:2]
            binds.append((dst, src))
        elif option == "--pwd":
            pwd = args.pop(0)
    args.pop(0)  # the image
    binds.sort(key=lambda bind: -len(bind[0]))

    def host(path):
        for dst, src in binds:
            if path == dst or path.startswith(dst + "/"):
                return src + path[len(dst):]
        return path

    cwd = host(pwd) if pwd else os.getcwd()
    if command == "run":
        macro = Path(host(args[0])).read_text()
        if "/fake/fail" in macro:
            print("*** Fatal Exception ***")
        events = macro.split()[-1]
        Path(cwd, "result.txt").write_text("1 %s\n2 %s\n" % (events, events))
        print("Run terminated.")
    elif args[0] == "geant4-config" and args[1] == "--version":
        print(os.environ["FAKE_G4_VERSION"])
    elif args[0] == "geant4-config":
        Path(host("/g4data"), "G4EMLOW8.6").mkdir()
    else:
        command = [sys.executable if args[0] == "/opt/venv/bin/python3" else args[0]]
        sys.exit(subprocess.run(command + [host(a) for a in args[1:]], cwd=cwd).returncode)
'''.replace("PYTHON", sys.executable)

RECORDER = '''#!/bin/sh
for arg in "$@"; do echo "$arg"; done >> "$FAKE_LOG.$(basename "$0")"
echo 1234
'''

PARSER = '''from pathlib import Path
from geantval import getJSON, one_command

def metadata(commands):
    return {"TEST": "Fake", "EVENTS": int(one_command(commands, "/run/beamOn"))}

def parse(job):
    rows = [line.split() for line in (Path(job["path"]) / "result.txt").read_text().splitlines()]
    yield getJSON(job, "chart", title="events %d" % job["EVENTS"],
                  xValues=[float(r[0]) for r in rows], yValues=[float(r[1]) for r in rows])
'''


class LocalPipelineTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        for name, text in [("apptainer", APPTAINER), ("sbatch", RECORDER), ("condor_submit", RECORDER),
                           ("geant4-config", '#!/bin/sh\necho "$FAKE_G4_VERSION"\n')]:
            (bin_dir / name).write_text(text)
            (bin_dir / name).chmod(0o755)
        self.log = self.tmp / "apptainer.log"
        self.env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", FAKE_LOG=str(self.log),
                        FAKE_G4_VERSION="11.3.2", G4MED_GIT_URL=str(self.tmp / "G4Med-test"),
                        G4MED_CVMFS_DATA=str(self.tmp / "no-cvmfs"), TMPDIR=str(self.tmp),
                        PYTHONDONTWRITEBYTECODE="1")
        for name in ("G4DATA", "G4MED_RUN_DIR", "APPTAINER_TMPDIR", "APPTAINER_CACHEDIR", "GITHUB_ACTIONS",
                     "GITHUB_REPOSITORY", "GITHUB_SHA", "IMAGE"):
            self.env.pop(name, None)
        self.run_dir = self.tmp / "run"
        self.sha = self.make_test_repo("Fake", {"a.mac": "/run/beamOn 10\n", "b.mac": "/run/beamOn 20\n"})

    def make_test_repo(self, name, macros):
        src = self.tmp / "src" / name
        (src / "macro").mkdir(parents=True)
        (src / "validation").mkdir()
        for macro, text in macros.items():
            (src / "macro" / macro).write_text(text)
        (src / "macro/unit.mac").write_text("/run/beamOn 1\n")
        (src / "validation/config.json").write_text(json.dumps({"macros": sorted(macros)}))
        (src / "validation/parser.py").write_text(PARSER)
        (src / "Apptainer.def").write_text("Bootstrap: oras\n")
        git = ["git", "-C", str(src), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", "-b", "main", str(src)], check=True)
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "test"], check=True)
        subprocess.run(["git", "clone", "-q", "--bare", str(src), str(self.tmp / "G4Med-test" / f"{name}.git")],
                       check=True)
        return subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()

    def pipeline(self, *args, check=True, **env):
        result = subprocess.run(["bash", str(PIPELINE), args[0], "--dir", str(self.run_dir), *map(str, args[1:])],
                                capture_output=True, text=True, env=dict(self.env, **env), cwd=self.tmp)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def calls(self, command):
        if not self.log.exists():
            return []
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [c for c in calls if c["args"][0] == command]

    def jobs(self):
        return [line.split("\t") for line in (self.run_dir / "jobs.txt").read_text().splitlines()]

    def test_prepare_submit_collect(self):
        self.pipeline("prepare", "Fake")
        image = f"oras://ghcr.io/g4med-test/fake:{self.sha}"
        self.assertEqual(self.calls("pull")[0]["args"][-1], image)
        self.assertEqual([macro for _, _, macro in self.jobs()], ["a.mac", "b.mac"])
        self.assertTrue((self.run_dir / "g4data/11.3.2/G4EMLOW8.6").is_dir())

        result = self.pipeline("submit", "local", "-j", "2")
        self.assertIn("2 plots", result.stderr)
        out = self.run_dir / "Fake/validation-json"
        records = json.loads((out / "results.json").read_text())
        self.assertEqual(sorted(r["chart"]["title"] for r in records), ["events 10", "events 20"])
        self.assertEqual(len(list((out / "plots").iterdir())), 2)
        provenance = json.loads((out / "provenance.json").read_text())
        self.assertEqual(provenance, {"test_repo": {"url": "https://github.com/G4Med-test/Fake", "sha": self.sha},
                                      "container_repo": None, "image": image, "geant4_version": "11.3.2"})
        self.assertIn("Fake                           2     2       0", self.pipeline("status").stdout)

        # Done macros are skipped; prepare again keeps them while the image is the same.
        runs = len(self.calls("run"))
        self.pipeline("prepare", "Fake")
        self.assertIn("already done", self.pipeline("run", "1").stderr)
        self.assertEqual(len(self.calls("run")), runs)
        self.pipeline("run", "--force", "Fake", "b.mac")
        self.assertEqual(len(self.calls("run")), runs + 1)

    def test_runs_the_macro_as_the_ci_does(self):
        self.pipeline("prepare", "Fake")
        self.pipeline("run", "Fake", "a.mac")
        _, id_, _ = self.jobs()[0]
        work = self.run_dir / "Fake/runs" / id_
        args = self.calls("run")[0]["args"]
        self.assertEqual(args[:2], ["run", "--unsquash"])
        self.assertIn(f"{self.run_dir}/g4data/11.3.2:/g4data:ro", args)
        self.assertEqual(args[-2:], [str(self.run_dir / "Fake/simulation.sif"), "/macro/a.mac"])
        self.assertEqual((work / "status").read_text(), "done\n")
        self.assertEqual((work / "outputs/test_stdout.txt").read_text(), "Run terminated.\n")
        self.assertTrue((work / "json/results.json").exists())

    def test_failed_macro_blocks_collect(self):
        self.make_test_repo("Broken", {"a.mac": "/fake/fail\n/run/beamOn 10\n"})
        self.pipeline("prepare", "Broken")
        result = self.pipeline("submit", "local", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Broken                         1     0       1", result.stdout)
        result = self.pipeline("collect", "Broken", check=False)
        self.assertIn("not every macro succeeded: a.mac (failed)", result.stderr)
        self.assertFalse((self.run_dir / "Broken/validation-json").exists())

    def test_a_missing_image_does_not_stop_the_other_tests(self):
        self.make_test_repo("Other", {"c.mac": "/run/beamOn 5\n"})
        result = self.pipeline("prepare", "Fake", "Other", check=False,
                               FAKE_MISSING=f"oras://ghcr.io/g4med-test/fake:{self.sha}")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not prepared: Fake", result.stderr)
        self.assertIn("--build builds it here", result.stderr)
        self.assertEqual([(t, m) for t, _, m in self.jobs()], [("Other", "c.mac")])

    def test_build_and_geant4_tag(self):
        result = self.pipeline("prepare", "--build", "--geant4", "v11.4.0", "Fake", APPTAINER_BUILD_FLAGS="--fakeroot")
        build = self.calls("build")[0]
        self.assertEqual(build["cwd"], str(self.run_dir / "Fake/repo"))
        self.assertEqual(build["args"], ["build", "--force", "--fakeroot", "--build-arg", "TAG=v11.4.0",
                                         "--build-arg", "PROJECT_NAME=Fake",
                                         str(self.run_dir / "Fake/simulation.sif.part"), "Apptainer.def"])
        self.pipeline("run", "1")
        provenance = json.loads((self.run_dir / f"Fake/runs/{self.jobs()[0][1]}/json/provenance.json").read_text())
        self.assertIsNone(provenance["image"])
        self.assertEqual(provenance["test_repo"]["sha"], self.sha)

    def test_pulls_the_image_of_the_geant4_tag_and_uses_given_datasets(self):
        (self.tmp / "data").mkdir()
        self.pipeline("prepare", "--geant4", "v11.4.0", "--g4data", self.tmp / "data", "Fake")
        self.assertEqual(self.calls("pull")[0]["args"][-1], f"oras://ghcr.io/g4med-test/fake:{self.sha}-v11.4.0")
        self.assertFalse((self.run_dir / "g4data").exists())
        self.pipeline("run", "1")
        self.assertIn(f"{self.tmp}/data:/g4data:ro", self.calls("run")[0]["args"])

    def test_local_changes_leave_the_commit_out_of_the_provenance(self):
        self.pipeline("prepare", "Fake")
        (self.run_dir / "Fake/repo/validation/parser.py").write_text(PARSER + "\n")
        self.assertIn("local changes", self.pipeline("run", "1").stderr)
        provenance = json.loads((self.run_dir / f"Fake/runs/{self.jobs()[0][1]}/json/provenance.json").read_text())
        self.assertIsNone(provenance["test_repo"])

    def test_unit(self):
        self.pipeline("prepare", "Fake")
        self.pipeline("unit", "Fake")
        call = self.calls("run")[0]
        self.assertEqual(call["cwd"], str(self.run_dir / "Fake/unit/outputs"))
        self.assertEqual(call["args"][-1], str(self.run_dir / "Fake/repo/macro/unit.mac"))

    def test_submit_slurm(self):
        self.pipeline("prepare", "Fake")
        self.pipeline("submit", "slurm", "--", "--partition=long")
        calls = (self.tmp / "apptainer.log.sbatch").read_text().splitlines()
        self.assertEqual(calls, ["--parsable", "--array=1-2", "--partition=long", str(self.run_dir / "slurm-run.sh"),
                                 "--parsable", "--dependency=afterany:1234", "--partition=long",
                                 str(self.run_dir / "slurm-collect.sh")])
        self.assertIn(f'exec bash {PIPELINE} run --dir {self.run_dir} "$SLURM_ARRAY_TASK_ID"',
                      (self.run_dir / "slurm-run.sh").read_text())

    def test_submit_condor(self):
        self.pipeline("prepare", "Fake")
        self.pipeline("submit", "condor", "--", "-a", "request_memory = 4 GB")
        calls = (self.tmp / "apptainer.log.condor_submit").read_text().splitlines()
        self.assertEqual(calls, ["-a", "request_memory = 4 GB", str(self.run_dir / "condor-run.sub")])
        sub = (self.run_dir / "condor-run.sub").read_text()
        self.assertIn(f'arguments = "{PIPELINE} run --dir {self.run_dir} $(test) $(id)"', sub)
        self.assertIn(f"queue test,id,macro from {self.run_dir}/jobs.txt", sub)

    def test_all_reads_tests_json(self):
        result = self.pipeline("prepare", "all", check=False)
        self.assertIn("LowEFrag: checking out", result.stderr)
        self.assertIn("raddecay: checking out", result.stderr)


if __name__ == "__main__": unittest.main()
