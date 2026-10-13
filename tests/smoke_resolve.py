"""Live check against the real Geosearch API. Run on your own machine:  python -m tests.smoke_resolve"""
from lookup.resolve import resolve_address

CASES = [
    ("47 Grace St, Jersey City, NJ", "outside_nyc"),   # the original bug
    ("47 Grace St, Jersey City, NJ 07307", "outside_nyc"),
    ("47 Grace Court, Brooklyn, NY 11201", "ok"),
    ("219 13th St, Brooklyn", "ok"),
    ("2612 Broadway, Manhattan", "ok"),
    ("537 E 13th St, Manhattan", "ok"),
    ("47 Grace St, Brooklyn", "confirm"),
    ("9999 Fake Blvd, Brooklyn", "no_match"),
]
bad = 0
for text, want in CASES:
    r = resolve_address(text)
    got = r.candidates[0]["label"] if r.candidates else (r.suggestions[0]["label"] if r.suggestions else "-")
    flag = "PASS" if r.status == want else "FAIL"
    bad += r.status != want
    print(f"{flag}  {text!r:40} -> {r.status:11} {got}")
    if flag == "FAIL":
        print("      ", r.debug[:4])
print("\nall good" if not bad else f"\n{bad} unexpected result(s), paste this output to me")
