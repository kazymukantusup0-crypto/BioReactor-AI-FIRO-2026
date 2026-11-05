"""Shared syntactic roles for quantities; later mentions cannot relabel a tank."""
import re


def reactor_field(text, start, end):
    before = re.split(r'[,;!?]|\.(?!\d)', text[:start])[-1]
    after = text[end:]
    # Immediate feedstock binding wins over an earlier mention of a reactor.
    from src.advisor.catalog import matches
    if re.match(r'\s*(?:of\s+)?(?:навоз|сырь|отход|manure|food|көң)', after, re.I) or any(
            hit['start'] <= 2 for hit in matches(after[:80])):
        return None
    suffix = re.match(r'\s*[-–]?\s*(?:реактор|reactor|digester)', after, re.I)
    prefix = re.search(r'(?:реактор\w*|reactor|digester|рабоч\w*\s+объ[её]м|working\s+volume|жұмыс\w*\s+көлем)[^\d]{0,70}$', before, re.I)
    if not (prefix or suffix):
        return None
    return 'reactor_working_volume_l' if re.search(r'рабоч|working|жұмыс', prefix.group() if prefix else suffix.group(), re.I) else 'reactor_total_volume_l'
