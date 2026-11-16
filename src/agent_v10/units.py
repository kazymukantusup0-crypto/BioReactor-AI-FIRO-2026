"""Unit normalisation: everything becomes litres (volume) or kilograms (mass).

Supported words in Russian, Kazakh and English. A bucket is assumed to be
10 litres; that assumption is returned so the agent can tell the user.
"""
from __future__ import annotations

import re

BUCKET_LITRES = 10.0
# A "мешок" (sack) is not a fixed unit. 50 L is a common polypropylene sack; always shown as an assumption.
BAG_LITRES = 50.0
BUCKET_ASSUMPTION = "1 ведро = 10 л"
BAG_ASSUMPTION = "1 мешок ≈ 50 л"

# (regex, family, factor to L or kg, assumption text or None)
UNIT_PATTERNS: list[tuple[str, str, float, str | None]] = [
    (r"(?:м3|м³|куб\w*|кубометр\w*|m3|m³|cubic\s*met\w*)", "volume", 1000.0, None),
    (r"(?:литр\w*|л|l|liter\w*|litre\w*)", "volume", 1.0, None),
    # "ведро, ведра, вёдер, ведер, ведрами"
    (r"(?:в[её]д[её]р\w*|ведр\w*|шелек\w*|bucket\w*)", "volume", BUCKET_LITRES, BUCKET_ASSUMPTION),
    (r"(?:меш[оке]\w*|мешочк\w*|қап\w*|bags?|sacks?)", "volume", BAG_LITRES, BAG_ASSUMPTION),
    (r"(?:тонн\w*|т|t|tonn?e?s?|ton)", "mass", 1000.0, None),
    # "50 кил", "50 кило", "50 килов" — spoken forms (manual check 3).
    (r"(?:килограмм\w*|кг|kg|kilo\w*|кило\w*|кил)", "mass", 1.0, None),
]

# A number: 200 | 1,5 | 1.5 | 1 000
NUMBER = r"\d+(?:[  ]\d{3})*(?:[.,]\d+)?"


def parse_number(text: str) -> float:
    """'1 000,5' -> 1000.5"""
    return float(text.replace(" ", "").replace(" ", "").replace(",", "."))


def normalize_unit(word: str) -> tuple[str, float, str | None] | None:
    """Return (family, factor, assumption) for a unit word, or None if unknown."""
    cleaned = word.strip().lower().rstrip(".")
    for pattern, family, factor, assumption in UNIT_PATTERNS:
        if re.fullmatch(pattern, cleaned):
            return family, factor, assumption
    return None


def to_base(amount: float, unit: str) -> dict:
    """Convert an amount to litres or kilograms.

    >>> to_base(2, "ведра")
    {'family': 'volume', 'value': 20.0, 'unit': 'L', 'assumption': '1 ведро = 10 л'}
    """
    normalized = normalize_unit(unit)
    if normalized is None:
        raise ValueError(f"Unknown unit: {unit}")
    family, factor, assumption = normalized
    return {
        "family": family,
        "value": amount * factor,
        "unit": "L" if family == "volume" else "kg",
        "assumption": assumption,
    }


# "200 л", "30 кг", "1,5 т", "2 ведра", "0.5 m3", "a 150-liter reactor"
QUANTITY_RE = re.compile(
    rf"(?P<number>{NUMBER})(?:\s*|-)(?P<unit>м3|м³|m3|m³|[a-zа-яёәғқңөұүһі]+)\b\.?",
    re.IGNORECASE,
)


def find_quantities(text: str) -> list[dict]:
    """Find every 'number + unit' in a text, with its position."""
    found = []
    for match in QUANTITY_RE.finditer(text):
        normalized = normalize_unit(match.group("unit"))
        if normalized is None:
            continue
        amount = parse_number(match.group("number"))
        base = to_base(amount, match.group("unit"))
        found.append({
            "amount": amount,
            "unit_word": match.group("unit"),
            "start": match.start(),
            "end": match.end(),
            **base,
        })
    return found
