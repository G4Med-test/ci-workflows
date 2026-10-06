"""Geant Validation Portal format, imported from geant-config-generator gts/utils.py.
Source commit: 0bf42953c9c98ac6ecccf077e7c7fe2c4ceb7307.
"""

COMMON_KEYS = {"inspireId", "mctool_name", "mctool_version", "mctool_model", "testName",
               "observableName", "reaction", "targetName", "beamParticle", "beamEnergies",
               "secondaryParticle", "parameters", "title", "xAxisName", "yAxisName",
               "yStatErrorsPlus", "yStatErrorsMinus", "ySysErrorsPlus", "ySysErrorsMinus"}
CHART_KEYS = COMMON_KEYS | {"xValues", "yValues", "xStatErrorsPlus", "xStatErrorsMinus",
                            "xSysErrorsPlus", "xSysErrorsMinus"}
HISTOGRAM_KEYS = COMMON_KEYS | {"binEdgeLow", "binEdgeHigh", "binContent", "binLabel"}


def getJSON(job, charttype="chart", **kwargs):
    # Unlike the original, reject misspelled or misplaced arguments instead of
    # silently replacing them with defaults.
    allowed = {"chart": CHART_KEYS, "histogram": HISTOGRAM_KEYS}.get(charttype)
    if allowed is None:
        raise ValueError("charttype must be 'chart' or 'histogram', not %r" % charttype)
    unknown = sorted(set(kwargs) - allowed)
    if unknown:
        raise TypeError("getJSON(%r) got unknown arguments: %s" % (charttype, ", ".join(unknown)))
    if job is None:
        job = {}
    j = {
        "article": {
            "inspireId": kwargs.get("inspireId", -1)
        },
        "mctool": {
            "name":  kwargs.get("mctool_name"),
            "version": kwargs.get("mctool_version", '' if 'VERSION' not in job else job['VERSION']),
            "model": kwargs.get("mctool_model")
        },
        "testName":  kwargs.get("testName", '' if 'TEST' not in job else job['TEST']),
        "metadata": {
            "observableName": kwargs.get("observableName"),
            "reaction": kwargs.get("reaction", "reaction name"),
            "targetName": kwargs.get("targetName"),
            "beamParticle": kwargs.get('beamParticle'),
            "beamEnergies": kwargs.get("beamEnergies"),
            "secondaryParticle": kwargs.get("secondaryParticle", "None"),
            "parameters": kwargs.get("parameters", [])
        },
        "plotType": "SCATTER2D" if charttype == "chart" else "TH1"
    }
    if charttype == "chart":
        j["chart"] = {
            "nPoints": len(kwargs.get("xValues")),
            "title": kwargs.get("title", "title"),
            "xAxisName": kwargs.get("xAxisName", "x axis"),
            "yAxisName": kwargs.get("yAxisName", "y axis"),
            "xValues": kwargs.get("xValues"),
            "yValues": kwargs.get("yValues"),
            "xStatErrorsPlus": kwargs.get("xStatErrorsPlus", []),
            "xStatErrorsMinus": kwargs.get("xStatErrorsMinus", []),
            "yStatErrorsPlus": kwargs.get("yStatErrorsPlus", []),
            "yStatErrorsMinus": kwargs.get("yStatErrorsMinus", []),
            "xSysErrorsPlus": kwargs.get("xSysErrorsPlus", []),
            "xSysErrorsMinus": kwargs.get("xSysErrorsMinus", []),
            "ySysErrorsPlus": kwargs.get("ySysErrorsPlus", []),
            "ySysErrorsMinus": kwargs.get("ySysErrorsMinus", [])
        }
    if charttype == "histogram":
        j["histogram"] = {
            "nBins": [len(kwargs.get("binContent"))],
            "title": kwargs.get("title", "title"),
            "xAxisName": kwargs.get("xAxisName", "x axis"),
            "yAxisName": kwargs.get("yAxisName", "y axis"),
            "binEdgeLow": kwargs.get("binEdgeLow"),
            "binEdgeHigh": kwargs.get("binEdgeHigh"),
            "binContent": kwargs.get("binContent"),
            "yStatErrorsPlus": kwargs.get("yStatErrorsPlus", []),
            "yStatErrorsMinus": kwargs.get("yStatErrorsMinus", []),
            "ySysErrorsPlus": kwargs.get("ySysErrorsPlus", []),
            "ySysErrorsMinus": kwargs.get("ySysErrorsMinus", []),
            "binLabel": kwargs.get("binLabel", [])
        }
    return j


def read_macro(path):
    """Read explicit, self-contained macros; never guess unresolved substitutions."""
    commands = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        command, value = parts[0], parts[1] if len(parts) > 1 else ""
        if command in ("/control/execute", "/control/loop", "/control/foreach", "/control/alias") or "{" in value:
            raise ValueError("Expand macro includes/aliases before validation: " + line)
        commands.append((command, value.strip()))
    return commands


def one_command(commands, name, default=None):
    values = [value for command, value in commands if command == name]
    if not values and default is not None:
        return default
    if len(values) != 1:
        raise ValueError("Expected exactly one " + name)
    return values[0]


def single_run(commands):
    events = int(one_command(commands, "/run/beamOn"))
    if events <= 0:
        raise ValueError("beamOn must be positive")
    return events


ENERGY_UNITS_MEV = {"eV": 1e-6, "keV": 1e-3, "MeV": 1., "GeV": 1e3, "TeV": 1e6}


def energy_mev(value):
    """Convert a Geant4 energy argument such as '3600 MeV' to MeV."""
    number, unit = value.split()
    return float(number) * ENERGY_UNITS_MEV[unit]
