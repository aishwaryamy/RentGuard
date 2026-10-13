"""Offline tests for lookup/resolve.py. No network: Geosearch is replaced by a fake that
imitates its real behaviour (NYC-only, fuzzy, always returns its closest guess).

Run:  python -m tests.test_resolve
"""
import sys

from lookup.resolve import detect_outside_nyc, is_nyc_zip, parse_input, resolve_address

DB = [
    dict(name="47 Grace Court", label="47 Grace Court, Brooklyn, NY, USA", bbl="3002510029",
         borough="Brooklyn", neighborhood="Brooklyn Heights", zip="11201"),
    dict(name="219 13th Street", label="219 13th Street, Brooklyn, NY, USA", bbl="3010150025",
         borough="Brooklyn", neighborhood="Park Slope", zip="11215"),
    dict(name="2612 Broadway", label="2612 Broadway, Manhattan, NY, USA", bbl="1018790001",
         borough="Manhattan", neighborhood="Upper West Side", zip="10025"),
    dict(name="537 East 13th Street", label="537 East 13th Street, Manhattan, NY, USA",
         bbl="1004050045", borough="Manhattan", neighborhood="East Village", zip="10009"),
    dict(name="537 West 13th Street", label="537 West 13th Street, Manhattan, NY, USA",
         bbl="1006500001", borough="Manhattan", neighborhood="West Village", zip="10014"),
    dict(name="100 Main Street", label="100 Main Street, Brooklyn, NY, USA", bbl="3000010001",
         borough="Brooklyn", neighborhood="DUMBO", zip="11201"),
    dict(name="100 Main Street", label="100 Main Street, Queens, NY, USA", bbl="4000010001",
         borough="Queens", neighborhood="Flushing", zip="11354"),
]


def fake_search(text, size=5):
    """Fuzzy like Pelias: ranks by token overlap and ALWAYS returns something."""
    toks = {t.strip(",.").lower() for t in text.split()}
    scored = sorted(DB, key=lambda c: -len(toks & set(c["label"].lower().replace(",", "").split())))
    return scored[:size]


CASES = [
    # (input, expected status, expected bbl or None)
    ("47 Grace St, Jersey City, NJ", "outside_nyc", None),                # the original bug
    ("47 Grace St, Jersey City, NJ 07307", "outside_nyc", None),
    ("47 Grace St Jersey City NJ", "outside_nyc", None),
    ("47 Grace Court, Hoboken", "outside_nyc", None),
    ("47 Grace St, New Jersey", "outside_nyc", None),
    ("47 Grace St 07307", "outside_nyc", None),
    ("219 13th St, Stamford, CT 06901", "outside_nyc", None),
    ("1 Main St, Yonkers, NY 10701", "outside_nyc", None),                # NY state, not NYC
    ("47 Grace Court, Brooklyn, NY 11201", "ok", "3002510029"),
    ("47 Grace Ct, Brooklyn", "ok", "3002510029"),
    ("47 Grace Court", "ok", "3002510029"),
    ("219 13th St, Brooklyn", "ok", "3010150025"),
    ("219 13th Street Brooklyn NY 11215", "ok", "3010150025"),
    ("2612 Broadway, Manhattan", "ok", "1018790001"),
    ("2612 Broadway, New York, NY 10025", "ok", "1018790001"),
    ("537 E 13th St, Manhattan", "ok", "1004050045"),
    ("537 East 13th Street, Manhattan", "ok", "1004050045"),
    ("47 Grace St, Brooklyn", "confirm", None),                           # wrong suffix -> ask
    ("537 13th St, Manhattan", "confirm", None),                          # no E/W -> ask
    ("47 Grace Court, Smalltown", "confirm", None),                       # unknown locality -> ask
    ("47 Grace Court, Brooklyn Heights", "ok", "3002510029"),
    ("48 Grace Court, Brooklyn", "no_match", None),                       # wrong number
    ("219 13th St, Queens", "no_match", None),                            # wrong borough
    ("219 13th St, Brooklyn 10001", "no_match", None),                    # ZIP contradicts
    ("9999 Fake Blvd, Brooklyn", "no_match", None),
    ("Grace Court", "incomplete", None),
    ("100 Main St", "choose", None),                                      # exists in 2 boroughs
    ("100 Main St, Queens", "ok", "4000010001"),
    ("1 Pine St, Seattle, WA 98101", "outside_nyc", None),
    ("500 Main St, Austin, TX 78701", "outside_nyc", None),
    ("1600 Pennsylvania Ave, Washington, DC", "outside_nyc", None),
    ("1 Pine St, Seattle", "no_match", None),
]


def main() -> int:
    fails = 0
    for text, want, bbl in CASES:
        r = resolve_address(text, search=fake_search)
        got_bbl = r.candidates[0]["bbl"] if r.status == "ok" else None
        good = r.status == want and (bbl is None or got_bbl == bbl)
        fails += not good
        print(f"{'PASS' if good else 'FAIL'}  {text!r:48} -> {r.status:11} (want {want})")
        if not good:
            print("      ", r.debug)

    # unit checks
    assert is_nyc_zip("11201") and is_nyc_zip("10025") and is_nyc_zip("10314")
    assert not is_nyc_zip("07307") and not is_nyc_zip("10701") and not is_nyc_zip("06901")
    assert detect_outside_nyc("47 Grace Ct") is None          # "Ct" is a street type, not Connecticut
    assert detect_outside_nyc("12345 Foo Dr, Brooklyn") is None  # 5-digit house number
    assert parse_input("21-10 31st Ave, Queens").house == "21-10"
    print("unit checks OK")
    print(f"\n{len(CASES) - fails}/{len(CASES)} cases passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
