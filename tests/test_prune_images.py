from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prune_images

NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)


def build(sha, day, arches=True):
    """The three versions pushed by one build, created on 2026-<day>."""
    created = f"2026-{day}T12:00:00Z"
    tags = [[sha]] + ([[f"{sha}-amd64"], [f"{sha}-arm64"]] if arches else [])
    return [{"id": f"{t[0]}", "name": "sha256:" + t[0], "created_at": created,
             "metadata": {"container": {"tags": t}}} for t in tags]


class PruneTests(unittest.TestCase):
    def tags(self, versions):
        return sorted(t for v in versions for t in v["metadata"]["container"]["tags"])

    def test_keeps_newest_recent_and_referenced_builds(self):
        versions = (build("a", "01-01") + build("b", "02-01") + build("c", "03-01") + build("d", "10-20")
                    + [{"id": "u1", "name": "sha256:old", "created_at": "2026-01-01T00:00:00Z", "metadata": {"container": {"tags": []}}},
                       {"id": "u2", "name": "sha256:new", "created_at": "2026-10-26T00:00:00Z", "metadata": {"container": {"tags": []}}}])
        kept, deleted = prune_images.plan(versions, keep=1, days=14, referenced={"a"}, now=NOW)
        self.assertEqual(self.tags(deleted), ["b", "b-amd64", "b-arm64", "c", "c-amd64", "c-arm64"])
        self.assertEqual([v["id"] for v in deleted if not v["metadata"]["container"]["tags"]], ["u1"])
        self.assertIn("a-arm64", self.tags(kept))

    def test_versioned_tags_are_separate_builds(self):
        versions = build("a", "01-01") + build("a-v11.4.3", "01-02")
        _, deleted = prune_images.plan(versions, keep=1, days=0, referenced=set(), now=NOW)
        self.assertEqual(self.tags(deleted), ["a", "a-amd64", "a-arm64"])

    def test_referenced_tags_from_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            for sub, image in (("", "oras://ghcr.io/g4med-test/lowefrag:abc"),
                               ("versions/11.3.2", "oras://ghcr.io/g4med-test/lowefrag:def-v11.3.2"),
                               ("versions/11.4.3", "oras://ghcr.io/g4med-test/other:zzz")):
                d = Path(tmp, "LowEFrag", sub)
                d.mkdir(parents=True, exist_ok=True)
                (d / "provenance.json").write_text(json.dumps({"image": image}))
            self.assertEqual(prune_images.referenced_tags(tmp, "LowEFrag", "lowefrag"), {"abc", "def-v11.3.2"})


if __name__ == "__main__":
    unittest.main()
