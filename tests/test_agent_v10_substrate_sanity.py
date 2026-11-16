"""Every feed against ONE reference table (KTBL 2025): in the ±30 % corridor and in the same order.

The table itself is written by scripts/substrate_sanity.py to docs/substrate_sanity.md.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("substrate_sanity", ROOT / "scripts" / "substrate_sanity.py")
sanity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sanity)


@pytest.fixture(scope="module")
def rows():
    return sanity.rows()


def test_every_feed_with_a_reference_is_in_the_corridor(rows):
    outside = [f"{r['material']}/{r['state']}" for r in rows if r.get("in_corridor") is False]
    assert outside == []


def test_order_of_directly_matched_feeds_follows_the_reference(rows):
    assert sanity.order_problems(rows) == []


def test_every_feed_of_the_agent_has_numbers(rows):
    assert [f"{r['material']}/{r['state']}" for r in rows if not r["ours"]] == []


def test_pig_slurry_gives_less_than_cattle_slurry_like_ktbl(rows):
    by = {(r["material"], r["state"]): r for r in rows}
    pig, cow = by[("swine_manure", "slurry")]["ours"]["biogas"], by[("cattle_manure", "slurry")]["ours"]["biogas"]
    assert (pig["low"] + pig["high"]) < (cow["low"] + cow["high"])
