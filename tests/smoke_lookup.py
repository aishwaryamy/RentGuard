"""Run from the project root:  python tests/smoke_lookup.py"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from lookup.live import build_report, search_addresses

for text in ["537 E 13th St, Manhattan", "219 13th St, Brooklyn", "2612 Broadway, Manhattan"]:
    candidates = search_addresses(text)
    print(f"\n=== {text}")
    if not candidates:
        print("  no candidates")
        continue
    c = candidates[0]
    print(f"  matched: {c['name']} | BBL {c['bbl']} | {c['neighborhood']}, {c['borough']} {c['zip']}")
    rep = build_report(c)
    s = rep["stats"]
    print(f"  violations: {s['total']} total, {s['open']} open, by class {s['by_class']}")
    print(f"  HPD 311 complaints: {s['complaints_total']} total, {s['complaints_3y']} in last 3 yrs")
