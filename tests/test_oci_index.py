import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("oci_index", Path(__file__).parents[1] / "scripts/oci_index.py")
oci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oci)
A, B = "a" * 64, "b" * 64


def manifest(sif_sha256):
    return json.dumps({"schemaVersion": 2, "mediaType": oci.MANIFEST, "layers": [
        {"mediaType": "application/vnd.sylabs.sif.layer.v1.sif", "digest": "sha256:" + sif_sha256, "size": 1}]}).encode()


class DescriptorTests(unittest.TestCase):
    def test_descriptor_carries_the_architecture_platform(self):
        result = oci.descriptor("amd64", manifest(A))
        self.assertEqual(result["mediaType"], oci.MANIFEST)
        self.assertEqual(result["platform"], {"architecture": "amd64", "os": "linux"})
        self.assertEqual(result["digest"], "sha256:" + hashlib.sha256(manifest(A)).hexdigest())
        self.assertEqual(result["size"], len(manifest(A)))


if __name__ == "__main__": unittest.main()
