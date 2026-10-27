import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release

REPOS = ["G4Med-test/A", "G4Med-test/B", "G4Med-test/C"]
MEDIANS = {"G4Med-test/A": 900, "G4Med-test/B": 300, "G4Med-test/C": None}


def median(repo):
    return MEDIANS[repo]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "G4Med-test/ci-workflows"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def started(self, repos=REPOS, explicit=False, state=None):
        state = state or release.new_state("v11.4.4")
        release.start_tests(state, repos, explicit, median=median)
        return state

    def test_queue_is_fastest_first_unknown_last(self):
        state = self.started()
        self.assertEqual([t["repo"] for t in release.queue_order(state["tests"])],
                         ["G4Med-test/B", "G4Med-test/A", "G4Med-test/C"])

    def test_body_round_trip(self):
        state = self.started()
        self.assertEqual(release.parse_state(release.render(state)), state)
        self.assertIn("queued #1", release.render(state))

    def test_duplicate_request_leaves_a_running_validation_alone(self):
        state = self.started()
        state["tests"][0].update(state="in_progress", run_id=1)
        state["tests"][1].update(state="success", run_id=2)
        release.start_tests(state, REPOS + ["G4Med-test/D"], False, median=lambda r: 5)
        self.assertEqual([t["state"] for t in state["tests"]], ["in_progress", "success", "todo", "todo"])

    def test_explicit_rerun_resets_only_finished_tests(self):
        state = self.started()
        state["tests"][0].update(state="failure", run_id=1)
        state["tests"][1].update(state="in_progress", run_id=2)
        release.start_tests(state, ["G4Med-test/A", "G4Med-test/B"], True, median=median)
        self.assertEqual([(t["state"], t["run_id"]) for t in state["tests"][:2]], [("todo", None), ("in_progress", 2)])

    def test_finished_validation_starts_again(self):
        state = self.started()
        for t in state["tests"]:
            t["state"] = "success"
        state["phase"] = "done"
        release.start_tests(state, REPOS, False, median=median)
        self.assertEqual({t["state"] for t in state["tests"]}, {"todo"})

    def test_waiting_image_keeps_the_requested_tests(self):
        state = release.new_state("v11.4.4")
        state.update(phase="waiting-image", requested=["G4Med-test/C"])
        release.start_tests(state, REPOS, False, median=median)
        self.assertEqual([t["repo"] for t in state["tests"]], ["G4Med-test/C"])

    def test_select(self):
        self.assertEqual(release.select("", REPOS), REPOS)
        self.assertEqual(release.select("b, g4med-test/a b", REPOS), ["G4Med-test/B", "G4Med-test/A"])
        with self.assertRaises(SystemExit):
            release.select("Nope", REPOS)

    def test_report_compares_with_the_previous_version(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
        from geantval import getJSON

        def results(content):
            return [getJSON({"TEST": "A"}, "histogram", title="h", binEdgeLow=[0, 1], binEdgeHigh=[1, 2],
                            binContent=content, yStatErrorsPlus=[1, 1], yStatErrorsMinus=[1, 1])]
        with tempfile.TemporaryDirectory() as tmp:
            for version, content in (("11.4.2", [0, 0]), ("11.4.3", [10, 10]), ("11.4.4", [10, 30])):
                d = Path(tmp, "A", "versions", version)
                d.mkdir(parents=True)
                (d / "results.json").write_text(json.dumps(results(content)))
            state = self.started(repos=["G4Med-test/A"])
            state["tests"][0].update(state="success", duration_s=600, url="https://x")
            state["requested_by"] = "carlomt"
            with mock.patch.dict(os.environ, {"RESULTS_DIR": tmp}):
                text = release.report(state)
        self.assertTrue(text.startswith("@carlomt "))
        self.assertIn("1 of 1 changed vs 11.4.3", text)


if __name__ == "__main__":
    unittest.main()
