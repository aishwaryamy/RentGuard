"""Address resolution with verification.

Why this exists
---------------
NYC's Geosearch API only knows NYC and fuzzy-matches whatever it is given, so
"47 Grace St, Jersey City, NJ" comes back as "47 Grace Court, Brooklyn".
`search_addresses` returns that top hit without checking it against what the
user typed. This module sits in front of it and never lets a result through
unless it agrees with the input.

Three layers:
  1. Scope gate   - refuse input that names a non-NYC state, city or ZIP.
  2. Verification - compare house number, street name, suffix, direction,
                    borough and ZIP of every candidate with the typed text.
  3. Confidence   - only an exact agreement is auto-accepted. Near misses are
                    returned as "confirm" and the user has to click.

`resolve_address` returns a Resolution whose `status` is one of:
  ok           exactly one verified building
  choose       several verified buildings (e.g. same address in two boroughs)
  confirm      close but not exact; ask the user "did you mean ...?"
  outside_nyc  input is outside the five boroughs
  incomplete   no house number / street
  no_match     nothing in NYC agrees with the input
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------- vocabularies
NON_NY_STATES = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca",
    "colorado": "co", "connecticut": "ct", "delaware": "de", "florida": "fl", "georgia": "ga",
    "hawaii": "hi", "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia",
    "kansas": "ks", "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv", "new hampshire": "nh",
    "new jersey": "nj", "new mexico": "nm", "north carolina": "nc", "north dakota": "nd",
    "ohio": "oh", "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa", "rhode island": "ri",
    "south carolina": "sc", "south dakota": "sd", "tennessee": "tn", "texas": "tx",
    "utah": "ut", "vermont": "vt", "virginia": "va", "washington": "wa",
    "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy", "district of columbia": "dc",
}
STATE_CODES = set(NON_NY_STATES.values())
# Codes that are also ordinary words / street suffixes: only trusted when they
# follow a comma or sit next to a ZIP code ("Court" is "Ct", "Drive" is "Dr").
AMBIGUOUS_CODES = {"ct", "or", "in", "me", "ok", "hi", "de", "la", "al", "id", "oh", "ma", "co", "pa"}

NON_NYC_PLACES = {
    "jersey city", "hoboken", "newark", "weehawken", "union city", "west new york",
    "bayonne", "secaucus", "fort lee", "edgewater", "hackensack", "paterson", "elizabeth",
    "yonkers", "mount vernon", "new rochelle", "white plains", "pelham", "port chester",
    "stamford", "greenwich", "norwalk", "bridgeport", "hempstead", "garden city",
    "great neck", "mineola", "freeport", "long beach", "valley stream", "westchester",
    "nassau county", "suffolk county", "philadelphia", "boston", "washington dc",
}

BOROUGHS = {
    "manhattan": "Manhattan", "new york county": "Manhattan", "mn": "Manhattan",
    "brooklyn": "Brooklyn", "bk": "Brooklyn", "kings county": "Brooklyn", "bklyn": "Brooklyn",
    "bronx": "Bronx", "the bronx": "Bronx", "bx": "Bronx",
    "queens": "Queens", "qns": "Queens", "queens county": "Queens",
    "staten island": "Staten Island", "si": "Staten Island", "richmond county": "Staten Island",
}
# "New York", "NYC" and "NY" are accepted but do not pin a borough.
GENERIC_NYC = {"new york", "nyc", "ny", "new york city", "new york ny", "ny ny", "new york, ny"}

NYC_PLACES = {
    "astoria", "long island city", "flushing", "jamaica", "forest hills", "jackson heights",
    "sunnyside", "woodside", "elmhurst", "corona", "ridgewood", "bayside", "far rockaway",
    "rockaway", "howard beach", "ozone park", "richmond hill", "kew gardens", "rego park",
    "williamsburg", "greenpoint", "bushwick", "bed-stuy", "bedford stuyvesant", "crown heights",
    "park slope", "prospect heights", "brooklyn heights", "dumbo", "fort greene", "clinton hill",
    "cobble hill", "carroll gardens", "red hook", "gowanus", "sunset park", "bay ridge",
    "bensonhurst", "coney island", "brighton beach", "flatbush", "midwood", "sheepshead bay",
    "canarsie", "east new york", "brownsville", "borough park", "windsor terrace",
    "harlem", "east harlem", "washington heights", "inwood", "upper west side",
    "upper east side", "midtown", "chelsea", "greenwich village", "east village",
    "west village", "soho", "tribeca", "lower east side", "chinatown", "financial district",
    "murray hill", "gramercy", "kips bay", "hell's kitchen", "morningside heights",
    "riverdale", "fordham", "mott haven", "south bronx", "pelham bay", "throgs neck",
    "st george", "stapleton", "tottenville", "new brighton",
}

SUFFIX_CANON = {
    "street": "st", "st": "st", "avenue": "ave", "ave": "ave", "av": "ave", "court": "ct",
    "ct": "ct", "place": "pl", "pl": "pl", "road": "rd", "rd": "rd", "boulevard": "blvd",
    "blvd": "blvd", "drive": "dr", "dr": "dr", "lane": "ln", "ln": "ln", "parkway": "pkwy",
    "pkwy": "pkwy", "terrace": "ter", "ter": "ter", "terr": "ter", "square": "sq", "sq": "sq",
    "plaza": "plz", "plz": "plz", "highway": "hwy", "hwy": "hwy", "way": "way",
    "turnpike": "tpke", "tpke": "tpke", "walk": "walk", "path": "path", "alley": "aly",
    "loop": "loop", "row": "row", "slip": "slip",
}
DIRECTIONS = {"east": "e", "e": "e", "west": "w", "w": "w", "north": "n", "n": "n",
              "south": "s", "s": "s"}
ORDINAL_WORDS = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
                 "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10"}

NYC_ZIP_RE = re.compile(r"^\d{5}$")


def is_nyc_zip(z: str) -> bool:
    if not NYC_ZIP_RE.match(z or ""):
        return False
    n = int(z)
    return (10001 <= n <= 10499) or (11004 <= n <= 11005) or (11101 <= n <= 11499) \
        or (11690 <= n <= 11699)


# ------------------------------------------------------------------- parsing
@dataclass
class Parsed:
    raw: str
    house: str = ""
    street_raw: str = ""
    core: tuple = ()
    suffix: str = ""
    direction: str = ""
    borough: str = ""
    zip: str = ""
    locality: str = ""       # leftover place text that is not a borough / generic NYC


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def normalize_street(street: str) -> tuple[tuple, str, str]:
    """-> (core tokens, canonical suffix, direction)."""
    s = street.lower().replace(".", "").replace("'", "")
    s = re.sub(r"(\d+)\s*(st|nd|rd|th)\b", r"\1", s)
    toks = [t for t in re.split(r"[\s,]+", s) if t]
    toks = [ORDINAL_WORDS.get(t, t) for t in toks]
    if len(toks) > 1 and toks[0] == "st":
        toks[0] = "saint"
    if len(toks) > 1 and toks[0] == "mt":
        toks[0] = "mount"
    suffix = ""
    if toks and toks[-1] in SUFFIX_CANON and len(toks) > 1:
        suffix = SUFFIX_CANON[toks.pop()]
    direction = ""
    core = []
    for i, t in enumerate(toks):
        # only a leading E/W/N/S/East/... is a direction
        if i == 0 and t in DIRECTIONS and len(toks) > 1:
            direction = DIRECTIONS[t]
        else:
            core.append(SUFFIX_CANON.get(t, t) if t in ("avenue", "av") else t)
    return tuple(core), suffix, direction


def parse_input(text: str) -> Parsed:
    raw = _squash(text or "")
    p = Parsed(raw=raw)
    t = raw.replace(".", "")
    # ZIP: last standalone 5-digit group that is not the leading house number
    zips = [z for z in re.findall(r"(?<![\w-])(\d{5})(?:-\d{4})?(?![\w-])", t)]
    if zips and not (t.startswith(zips[-1] + " ") and len(zips) == 1):
        p.zip = zips[-1]
    segs = [x.strip() for x in t.split(",") if x.strip()]

    street_part = segs[0] if segs else ""
    tail = segs[1:]
    if len(segs) == 1:
        # no commas: peel trailing ZIP / state / borough words off the street text
        s = re.sub(r"\s+\d{5}(?:-\d{4})?\s*$", "", street_part) if p.zip else street_part
        s = re.sub(r"\s+ny\s*$", "", s, flags=re.I)
        low = s.lower()
        for name in sorted(list(BOROUGHS) + ["nyc", "new york city", "new york"], key=len, reverse=True):
            if low.endswith(" " + name):
                if name in BOROUGHS:
                    p.borough = BOROUGHS[name]
                s = s[: -(len(name) + 1)]
                break
        street_part = s
    street_part = re.split(r"\b(?:apt|unit|suite|ste|fl|floor|#)\b", street_part, flags=re.I)[0].strip()

    m = re.match(r"^(\d+(?:-\d+)?[A-Za-z]?)\s+(.+)$", street_part)
    if m:
        p.house = m.group(1).upper()
        p.street_raw = m.group(2).strip()
        p.core, p.suffix, p.direction = normalize_street(p.street_raw)

    loc = []
    for seg in tail:
        sl = re.sub(r"\s*\d{5}(?:-\d{4})?\s*$", "", seg.lower()).strip()
        sl = re.sub(r"\s+ny$", "", sl).strip()
        if not sl or sl in GENERIC_NYC or sl == "ny" or is_state_code(sl):
            continue
        if sl in BOROUGHS:
            p.borough = BOROUGHS[sl]
        else:
            loc.append(sl)
    p.locality = ", ".join(loc)
    return p


def is_state_code(s: str) -> bool:
    return s in STATE_CODES


# ------------------------------------------------------------------ scope gate
def detect_outside_nyc(text: str) -> str | None:
    """Return a human-readable reason if the input clearly names somewhere outside NYC."""
    t = " " + _squash((text or "").lower().replace(".", "")) + " "
    for name in sorted(NON_NY_STATES, key=len, reverse=True):
        if re.search(rf"[\s,]{re.escape(name)}[\s,]", t):
            return name.title()
    for city in NON_NYC_PLACES:
        if re.search(rf"[\s,]{re.escape(city)}[\s,]", t):
            return city.title()
    # two-letter codes: after a comma, or glued to a ZIP; unambiguous ones also at the end
    for m in re.finditer(r",\s*([a-z]{2})\b", t):
        if m.group(1) in STATE_CODES:
            return m.group(1).upper()
    for m in re.finditer(r"\b([a-z]{2})\s+(\d{5})\b", t):
        if m.group(1) in STATE_CODES:
            return m.group(1).upper()
    m = re.search(r"\s([a-z]{2})\s*$", t)
    if m and m.group(1) in STATE_CODES and m.group(1) not in AMBIGUOUS_CODES:
        return m.group(1).upper()
    for z in re.findall(r"(?<![\w-])(\d{5})(?![\w-])", t):
        # only treat as ZIP when it is not the house number (first token)
        if not t.strip().startswith(z + " ") and not is_nyc_zip(z):
            return f"ZIP {z}"
    return None


# ----------------------------------------------------------------- verification
@dataclass
class Verdict:
    level: str                 # "exact" | "soft" | "reject"
    reasons: list = field(default_factory=list)


def _cand_parts(c: dict) -> tuple[str, tuple, str, str]:
    name = (c.get("name") or c.get("label") or "").strip()
    m = re.match(r"^(\d+(?:-\d+)?[A-Za-z]?)\s+(.+)$", name)
    if not m:
        return "", (), "", ""
    core, suffix, direction = normalize_street(m.group(2))
    return m.group(1).upper(), core, suffix, direction


def _similar(a: tuple, b: tuple) -> float:
    return difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()


def verify_candidate(p: Parsed, c: dict) -> Verdict:
    house, core, suffix, direction = _cand_parts(c)
    v = Verdict("exact")

    def reject(msg):
        v.level = "reject"
        v.reasons.append(msg)

    def soft(msg):
        if v.level == "exact":
            v.level = "soft"
        v.reasons.append(msg)

    if not house or house.replace("-", "") != p.house.replace("-", ""):
        reject(f"house number {p.house} vs {house or '?'}")
        return v
    if core != p.core:
        if _similar(core, p.core) >= 0.85:
            soft(f"street name '{' '.join(p.core)}' vs '{' '.join(core)}'")
        else:
            reject(f"street name '{' '.join(p.core)}' vs '{' '.join(core)}'")
            return v
    if p.suffix and suffix and p.suffix != suffix:
        soft(f"street type '{p.suffix}' vs '{suffix}'")
    if p.direction and direction and p.direction != direction:
        reject("direction differs")
        return v
    if direction and not p.direction:
        soft(f"no direction given (record is on '{direction.upper()}')")
    if p.zip and c.get("zip") and p.zip != str(c["zip"]):
        reject(f"ZIP {p.zip} vs {c['zip']}")
        return v
    if p.borough and c.get("borough") and p.borough.lower() != str(c["borough"]).lower():
        reject(f"borough {p.borough} vs {c['borough']}")
        return v
    if p.locality:
        blob = " ".join(str(c.get(k) or "") for k in ("neighborhood", "borough", "label")).lower()
        if not (p.locality in NYC_PLACES or p.locality in blob):
            soft(f"'{p.locality}' not recognised as part of NYC")
    return v


# --------------------------------------------------------------------- resolve
@dataclass
class Resolution:
    status: str
    message: str = ""
    candidates: list = field(default_factory=list)   # verified (ok / choose)
    suggestions: list = field(default_factory=list)  # near misses to confirm (confirm)
    debug: list = field(default_factory=list)


def resolve_address(text: str, search=None) -> Resolution:
    if search is None:
        from lookup.live import search_addresses as search  # lazy: keeps tests offline

    text = _squash(text or "")
    outside = detect_outside_nyc(text)
    if outside:
        return Resolution(
            "outside_nyc",
            f"“{outside}” is outside New York City. RentGuard only covers NYC's five boroughs "
            "(Manhattan, Brooklyn, Queens, the Bronx and Staten Island), because it relies on "
            "NYC's own HPD and 311 records. I haven't guessed a similar NYC address.",
        )

    p = parse_input(text)
    if not p.house or not p.core:
        return Resolution(
            "incomplete",
            "Please include the street number and street name, like “219 13th St, Brooklyn”.",
        )

    seen, pool = set(), []
    queries = [text]
    bare = f"{p.house} {p.street_raw}" + (f", {p.borough}" if p.borough else "")
    if bare.lower() != text.lower():
        queries.append(bare)
    for q in queries:
        for c in search(q, size=10):
            key = c.get("bbl") or c.get("label")
            if key not in seen:
                seen.add(key)
                pool.append(c)

    exact, soft_hits, debug = [], [], []
    for c in pool:
        v = verify_candidate(p, c)
        debug.append((c.get("label"), v.level, v.reasons))
        if v.level == "exact":
            exact.append(c)
        elif v.level == "soft":
            soft_hits.append((c, v.reasons))

    if len(exact) == 1:
        return Resolution("ok", candidates=exact, debug=debug)
    if len(exact) > 1:
        return Resolution(
            "choose",
            "That address exists in more than one place. Pick the right one.",
            candidates=exact, debug=debug,
        )
    if soft_hits:
        return Resolution(
            "confirm",
            "I couldn't find that exact address, but these are close. Is one of them the building you mean?",
            suggestions=[c for c, _ in soft_hits[:5]], debug=debug,
        )
    return Resolution(
        "no_match",
        "I couldn't find that address in NYC's records, so I won't guess. Check the street number "
        "and spelling and add the borough, for example “219 13th St, Brooklyn”.",
        debug=debug,
    )
