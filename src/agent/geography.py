"""Resolve conversational mentions to the application's supported region IDs.

Only regions represented by the market catalogue are emitted. A bare inflected
Karaganda/Almaty oblast adjective is treated as the oblast; the city has its own
explicit name and code.
"""
import re


_DISTRICTS = (
    (r"абайск\w*", "Abay"),
    (r"бухар[ -]жырауск\w*", "Bukhar-Zhyrau"),
    (r"нуринск\w*", "Nura"),
    (r"осакаровск\w*", "Osakarov"),
    (r"каркаралинск\w*", "Karkaraly"),
)


def resolve_region(text: str) -> str | None:
    """Return a namespaced region ID for a clear supported place mention."""
    if not isinstance(text, str):
        return None
    value = text.casefold().replace("ё", "е")
    # Keep the most specific supported Karaganda districts.
    for stem, code in _DISTRICTS:
        if re.search(stem + r"(?:\s+(?:район|district))?\b", value, re.I):
            return f"KZ-Karaganda-{code}-district"

    # City names and their ordinary Russian/Kazakh cases.
    if re.search(r"\b(?:в|из|для|городе|города)?\s*караганд(?:а|е|у|ой|ою|у|ы|е)?\b|\bkaraganda\b|қарағанд", value, re.I):
        return "KZ-Karaganda"
    if re.search(r"\b(?:в|из|для)?\s*алмат(?:ы|е|у|ой|ою)?\b|\balmaty\b", value, re.I):
        return "KZ-Almaty"

    # A standalone adjective is a common answer to "which oblast?".
    if re.search(r"карагандинск\w*|қарағанды\s+(?:облыс|облысында)", value, re.I):
        return "KZ-Karaganda-oblast"
    if re.search(r"алматинск\w*", value, re.I):
        return "KZ-Almaty-oblast"
    if re.search(r"\b(?:казахстан|рк|kazakhstan)\b|қазақстан", value, re.I):
        return "KZ-national"
    return None
