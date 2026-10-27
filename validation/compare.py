#!/usr/bin/env python3
"""Compare the plots of one test between two Geant4 versions (two results.json).

Plots are matched by everything that identifies them except the Geant4 version:
test, plot type, model, metadata, title and axis names. For each matched pair:

- same:         identical values;
- compatible:   chi2 test of the differences, with the uncertainties of both versions
                (statistical and systematic in quadrature), p >= alpha; points without
                uncertainties must agree within rel_tol;
- changed:      p < alpha, or a point without uncertainties differs by more than rel_tol;
- incomparable: different bins or x values, so no point-by-point comparison;
- new/removed:  the plot exists in only one version.

Only the standard library is used: the dashboard and the release report import it.
"""
import argparse
import json
import math
from pathlib import Path
import re
import sys

ALPHA = 0.01     # p-value below which a plot counts as changed
REL_TOL = 0.05   # largest relative difference of points without uncertainties
STATUS_ORDER = ["changed", "incomparable", "removed", "new", "compatible", "same"]


def version_key(version):
    """Sort key of a Geant4 version or tag: 11.4.0.beta < 11.4.0 < 11.4.1."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)(.*)", version)
    if not m:
        return (-1, -1, -1, False, version)
    return (int(m[1]), int(m[2]), int(m[3]), not m[4], m[4])


def load(path):
    """results.json, or a directory containing it."""
    path = Path(path)
    return json.loads((path / "results.json" if path.is_dir() else path).read_text())


def plot_key(record):
    data = record.get("histogram") or record.get("chart") or {}
    mctool = record.get("mctool") or {}
    return json.dumps([record.get("testName"), record.get("plotType"), mctool.get("name"),
                       mctool.get("model"), record.get("metadata"), data.get("title"),
                       data.get("xAxisName"), data.get("yAxisName")], sort_keys=True)


def keyed(records):
    """Records by plot_key; repeated keys get a counter, in file order."""
    out, seen = {}, {}
    for record in records:
        key = plot_key(record)
        seen[key] = seen.get(key, 0) + 1
        out[key if seen[key] == 1 else f"{key}#{seen[key]}"] = record
    return out


def _errors(data, n, axis="y"):
    def arr(name):
        values = data.get(name) or []
        return [abs(v) for v in values] if len(values) == n else [0.0] * n
    stat = [max(p, m) for p, m in zip(arr(f"{axis}StatErrorsPlus"), arr(f"{axis}StatErrorsMinus"))]
    syst = [max(p, m) for p, m in zip(arr(f"{axis}SysErrorsPlus"), arr(f"{axis}SysErrorsMinus"))]
    return [math.hypot(s, t) for s, t in zip(stat, syst)]


def series(record):
    """x (bin centre or point), bin edges if any, y and its total uncertainty."""
    if record.get("plotType") == "TH1":
        h = record["histogram"]
        lo, hi, y = h["binEdgeLow"], h["binEdgeHigh"], h["binContent"]
        return {"x": [(a + b) / 2 for a, b in zip(lo, hi)], "lo": lo, "hi": hi, "y": y, "err": _errors(h, len(y))}
    c = record["chart"]
    y = c["yValues"]
    return {"x": c["xValues"], "lo": None, "hi": None, "y": y, "err": _errors(c, len(y))}


def chi2_sf(chi2, ndf):
    """P(X >= chi2) for a chi2 distribution: regularized upper incomplete gamma Q(ndf/2, chi2/2)."""
    if chi2 <= 0:
        return 1.0
    a, x = ndf / 2, chi2 / 2
    gln = math.lgamma(a)
    if x < a + 1:  # series for P, then Q = 1 - P
        term = total = 1 / a
        for n in range(1, 1000):
            term *= x / (a + n)
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return max(0.0, 1 - total * math.exp(-x + a * math.log(x) - gln))
    # Continued fraction for Q (Lentz).
    tiny = 1e-300
    b, c, d = x + 1 - a, 1 / tiny, 1 / (x + 1 - a)
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return min(1.0, math.exp(-x + a * math.log(x) - gln) * h)


def _close(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def compare_plot(ref, cand, alpha=ALPHA, rel_tol=REL_TOL):
    """Status and statistics of one pair of matched plots."""
    a, b = series(ref), series(cand)
    out = {"status": None, "chi2": None, "ndf": 0, "p": None, "max_rel_diff": None, "worst": None}
    if len(a["x"]) != len(b["x"]) or not all(_close(p, q) for p, q in zip(a["x"], b["x"])):
        out.update(status="incomparable", reason="bins or x values differ")
        return out
    if all(p == q for p, q in zip(a["y"], b["y"])):
        out.update(status="same", max_rel_diff=0.0)
        return out
    chi2, ndf, unexplained, worst, worst_score, max_rel = 0.0, 0, False, None, -1.0, 0.0
    for i, (ya, yb, ea, eb) in enumerate(zip(a["y"], b["y"], a["err"], b["err"])):
        scale = max(abs(ya), abs(yb))
        rel = abs(ya - yb) / scale if scale else 0.0
        max_rel = max(max_rel, rel)
        var = ea * ea + eb * eb
        if var > 0:
            pull2 = (ya - yb) ** 2 / var
            chi2, ndf = chi2 + pull2, ndf + 1
            score = math.sqrt(pull2)
        else:
            unexplained = unexplained or rel > rel_tol
            score = rel * 1e6 if rel > rel_tol else rel  # unexplained differences are the worst
        if score > worst_score:
            worst, worst_score = i, score
    p = chi2_sf(chi2, ndf) if ndf else None
    changed = unexplained or (p is not None and p < alpha)
    out.update(status="changed" if changed else "compatible", chi2=chi2 if ndf else None, ndf=ndf, p=p,
               max_rel_diff=max_rel, worst=worst)
    return out


def describe(record):
    data = record.get("histogram") or record.get("chart") or {}
    meta = record.get("metadata") or {}
    return {"title": data.get("title"), "plotType": record.get("plotType"), "model": (record.get("mctool") or {}).get("model"),
            "observable": meta.get("observableName"), "beam": meta.get("beamParticle"),
            "energies": meta.get("beamEnergies"), "target": meta.get("targetName"),
            "secondary": meta.get("secondaryParticle"), "parameters": meta.get("parameters"),
            "xAxisName": data.get("xAxisName"), "yAxisName": data.get("yAxisName")}


def compare(ref_records, cand_records, alpha=ALPHA, rel_tol=REL_TOL, with_data=False):
    """Summary and per-plot results; with_data adds both series, for plotting."""
    ref, cand = keyed(ref_records), keyed(cand_records)
    plots = []
    for key in list(ref) + [k for k in cand if k not in ref]:
        r, c = ref.get(key), cand.get(key)
        if r and c:
            res = compare_plot(r, c, alpha, rel_tol)
        else:
            res = {"status": "removed" if r else "new"}
        res.update(describe(r or c))
        if with_data:
            res["data"] = {"ref": series(r) if r else None, "cand": series(c) if c else None}
        plots.append(res)
    plots.sort(key=lambda p: (STATUS_ORDER.index(p["status"]), p.get("p") if p.get("p") is not None else 2,
                              -(p.get("max_rel_diff") or 0)))
    summary = {s: 0 for s in STATUS_ORDER}
    for p in plots:
        summary[p["status"]] += 1
    return {"alpha": alpha, "rel_tol": rel_tol, "summary": summary, "plots": plots}


def main():
    cli = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("reference", help="results.json (or its directory) of the reference version")
    cli.add_argument("candidate", help="results.json (or its directory) of the version to check")
    cli.add_argument("--alpha", type=float, default=ALPHA, help="p-value threshold (default: %(default)s)")
    cli.add_argument("--rel-tol", type=float, default=REL_TOL,
                     help="relative tolerance of points without uncertainties (default: %(default)s)")
    cli.add_argument("--output", type=Path, help="write the full comparison as JSON")
    cli.add_argument("--fail-on-change", action="store_true", help="exit with 1 if any plot changed")
    args = cli.parse_args()
    result = compare(load(args.reference), load(args.candidate), args.alpha, args.rel_tol, with_data=bool(args.output))
    if args.output:
        args.output.write_text(json.dumps(result, indent=1) + "\n")
    print(", ".join(f"{n} {s}" for s, n in result["summary"].items() if n))
    for p in result["plots"]:
        if p["status"] in ("changed", "incomparable"):
            stat = f"p={p['p']:.2g}" if p.get("p") is not None else p.get("reason", f"max rel diff {p['max_rel_diff']:.1%}")
            print(f"  {p['status']:12} {p['title']} [{p['secondary']}] {stat}")
    sys.exit(1 if args.fail_on_change and result["summary"]["changed"] else 0)


if __name__ == "__main__":
    main()
