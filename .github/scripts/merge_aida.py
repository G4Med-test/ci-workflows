#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
import math

histos = defaultdict(lambda: defaultdict(lambda: {"height": 0.0, "error2": 0.0, "entries": 0}))

for fname in sys.argv[1:]:
    tree = ET.parse(fname)
    root = tree.getroot()
    for h in root.findall(".//histogram1d"):
        name = h.attrib["name"]
        bins = h.find("data1d").findall("bin1d")
        for b in bins:
            binNum = b.attrib["binNum"]
            height = float(b.attrib["height"])
            error = float(b.attrib["error"])
            entries = int(b.attrib["entries"])
            hbin = histos[name][binNum]
            hbin["height"] += height
            hbin["error2"] += error**2
            hbin["entries"] += entries

print('<?xml version="1.0" encoding="UTF-8"?>')
print('<!DOCTYPE aida SYSTEM "http://aida.freehep.org/schemas/3.2.1/aida.dtd">')
print('<aida version="3.2.1">')

for name, bins in histos.items():
    print(f'  <histogram1d name="{name}" path="/" title="{name}">')
    print(f'    <axis direction="x"/>')
    print(f'    <data1d>')
    for binNum, values in sorted(bins.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
        height = values["height"]
        error = math.sqrt(values["error2"])
        entries = values["entries"]
        print(f'      <bin1d binNum="{binNum}" entries="{entries}" height="{height}" error="{error:.10f}"/>')
    print(f'    </data1d>')
    print(f'  </histogram1d>')

print('</aida>')
