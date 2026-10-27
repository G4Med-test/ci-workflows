from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare
from geantval import getJSON


def histogram(content, errors=None, title="h", edges=None, version="11.4.3"):
    n = len(content)
    lo = edges or [float(i) for i in range(n)]
    return getJSON({"TEST": "T", "VERSION": version}, "histogram", mctool_name="GEANT4", mctool_model="QGSP_BIC",
                   observableName="dN/dE", targetName="C", beamParticle="proton", beamEnergies=[100],
                   title=title, binEdgeLow=lo, binEdgeHigh=[x + 1 for x in lo], binContent=content,
                   yStatErrorsPlus=errors or [], yStatErrorsMinus=errors or [])


def chart(y, title="c"):
    return getJSON({"TEST": "T", "VERSION": "11.4.3"}, "chart", title=title, xValues=[1.0, 2.0, 3.0], yValues=y)


class CompareTests(unittest.TestCase):
    def status(self, ref, cand):
        return compare.compare([ref], [cand])["plots"][0]["status"]

    def test_chi2_survival_function(self):
        for chi2, ndf, p in ((3.841, 1, 0.05), (18.307, 10, 0.05), (124.342, 100, 0.05), (0.5, 4, 0.9735)):
            self.assertAlmostEqual(compare.chi2_sf(chi2, ndf), p, places=4)
        self.assertEqual(compare.chi2_sf(0, 3), 1.0)

    def test_version_order(self):
        versions = ["11.4.0", "11.10.0", "11.4.0.beta", "11.3.2", "v11.4.1"]
        self.assertEqual(sorted(versions, key=compare.version_key),
                         ["11.3.2", "11.4.0.beta", "11.4.0", "v11.4.1", "11.10.0"])

    def test_statuses(self):
        base = histogram([100, 200, 300], [10, 14, 17])
        self.assertEqual(self.status(base, histogram([100, 200, 300], [10, 14, 17], version="11.4.4")), "same")
        self.assertEqual(self.status(base, histogram([105, 195, 310], [10, 14, 17])), "compatible")
        self.assertEqual(self.status(base, histogram([150, 260, 400], [10, 14, 17])), "changed")
        self.assertEqual(self.status(base, histogram([100, 200, 300], [10, 14, 17], edges=[0.0, 2.0, 4.0])),
                         "incomparable")

    def test_points_without_uncertainties_use_the_relative_tolerance(self):
        self.assertEqual(self.status(chart([1.0, 2.0, 3.0]), chart([1.01, 2.0, 3.0])), "compatible")
        self.assertEqual(self.status(chart([1.0, 2.0, 3.0]), chart([1.2, 2.0, 3.0])), "changed")

    def test_matching_ignores_the_version_and_reports_new_and_removed(self):
        ref = [histogram([1, 2], title="a"), histogram([1, 2], title="b")]
        cand = [histogram([1, 2], title="a", version="11.5.0"), histogram([1, 2], title="c")]
        result = compare.compare(ref, cand)
        self.assertEqual({p["title"]: p["status"] for p in result["plots"]}, {"a": "same", "b": "removed", "c": "new"})
        self.assertEqual(result["summary"]["same"], 1)

    def test_changed_plots_come_first_with_data(self):
        ref = [histogram([1, 2], [1, 1], title="a"), histogram([10, 20], [1, 1], title="b")]
        cand = [histogram([1, 2], [1, 1], title="a"), histogram([30, 50], [1, 1], title="b")]
        result = compare.compare(ref, cand, with_data=True)
        self.assertEqual(result["plots"][0]["title"], "b")
        self.assertEqual(result["plots"][0]["data"]["cand"]["y"], [30, 50])
        self.assertEqual(result["plots"][0]["worst"], 1)


if __name__ == "__main__":
    unittest.main()
