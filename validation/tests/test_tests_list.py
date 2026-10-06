import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests_list


class TestsListTests(unittest.TestCase):
    def check(self, tests):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tests.json"
            path.write_text(json.dumps({"tests": tests}))
            return tests_list.load(path)

    def test_repository_file_is_valid(self):
        self.assertTrue(tests_list.load())

    def test_valid_entries(self):
        tests = [{"repo": "G4Med-test/LowEFrag", "ref": "main"}, {"repo": "G4Med-test/X", "ref": "3f2a9c1"}]
        self.assertEqual(self.check(tests), tests)

    def test_invalid_entries_fail(self):
        for tests in ([], [{"repo": "LowEFrag", "ref": "main"}],
                      [{"repo": "G4Med-test/LowEFrag", "ref": "main; echo"}],
                      [{"repo": "G4Med-test/LowEFrag"}],
                      [{"repo": "G4Med-test/A", "ref": "main"}] * 2):
            with self.assertRaises((ValueError, KeyError)):
                self.check(tests)


if __name__ == "__main__": unittest.main()
