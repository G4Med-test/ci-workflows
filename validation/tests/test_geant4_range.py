import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import geant4_range

# (field, tag, allowed): shared with the bash copy in tests/test_local_pipeline.py.
CASES = [
    ({"min": "11.4", "reason": "r"}, "v11.4.0.beta", True),
    ({"min": "11.4", "reason": "r"}, "v11.3.2", False),
    ({"min": "11.4", "reason": "r"}, "v12.0.0", True),
    ({"min": "11.4", "max": "11.4", "reason": "r"}, "v11.4.3", True),
    ({"min": "11.4", "max": "11.4", "reason": "r"}, "v11.5.0.beta", False),
    ({"min": "11.4", "max": "11.4", "reason": "r"}, "v11.2.2", False),
    ({"max": "11.3", "reason": "r"}, "v11.3.9", True),
    ({"max": "11.3", "reason": "r"}, "v11.4.0", False),
    ({"min": "11.2.1", "max": "11.3.2", "reason": "r"}, "v11.2.0", False),
    ({"min": "11.2.1", "max": "11.3.2", "reason": "r"}, "v11.2.1", True),
    ({"min": "11.2.1", "max": "11.3.2", "reason": "r"}, "v11.3.2", True),
    ({"min": "11.2.1", "max": "11.3.2", "reason": "r"}, "v11.3.3", False),
    ({"min": "10.7", "reason": "r"}, "v11.0.0", True),
]


class Geant4RangeTests(unittest.TestCase):
    def test_allows(self):
        for field, tag, allowed in CASES:
            self.assertEqual(geant4_range.allows(geant4_range.parse(field), tag), allowed, (field, tag))
        self.assertTrue(geant4_range.allows(None, "v9.6.4"))

    def test_invalid_fields_fail(self):
        for field in ({}, {"reason": "r"}, {"min": "11.4"}, {"min": "11.4", "reason": " "},
                      {"min": "v11.4", "reason": "r"}, {"min": "11", "reason": "r"},
                      {"min": 11.4, "reason": "r"}, {"min": "11.5", "max": "11.4", "reason": "r"},
                      {"min": "11.4", "reason": "r", "note": "x"}, ["11.4"]):
            with self.assertRaises(ValueError, msg=field):
                geant4_range.parse(field)

    def test_excluded_says_why(self):
        config = {"macros": ["a.mac"], "geant4": {"min": "11.4", "max": "11.4", "reason": "GATE 9.4.2"}}
        self.assertIsNone(geant4_range.excluded(config, "v11.4.3"))
        self.assertEqual(geant4_range.excluded(config, "v11.2.2"), "requires Geant4 11.4: GATE 9.4.2")
        self.assertIsNone(geant4_range.excluded({"macros": ["a.mac"]}, "v11.2.2"))
        self.assertEqual(geant4_range.describe({"min": "11.3", "max": "11.4"}), "Geant4 11.3 to 11.4")
        self.assertEqual(geant4_range.describe({"min": "11.3"}), "Geant4 >= 11.3")

    def test_check_reads_the_tag_default_of_the_apptainer_definition(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, definition = Path(tmp, "config.json"), Path(tmp, "Apptainer.def")
            config.write_text(json.dumps({"macros": ["a.mac"],
                                          "geant4": {"min": "11.4", "reason": "opengate"}}))
            definition.write_text("%arguments\n    TAG=v11.4.3\n    OPENGATE_TAG=10.1.1\n")
            run = lambda *a: geant4_range.main(["check", "--config", str(config), *a])
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(run("--apptainer-def", str(definition)), 0)
                self.assertEqual(run("--tag", "v11.3.2"), 1)
                self.assertEqual(geant4_range.main(["check", "--config", str(Path(tmp, "none.json")),
                                                    "--tag", "v11.3.2"]), 0)
            self.assertIn("::error::Geant4 v11.3.2 is not supported by this test: it requires "
                          "Geant4 >= 11.4: opengate", out.getvalue())


if __name__ == "__main__":
    unittest.main()
