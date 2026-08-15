import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import collect_tomtom_traffic as tt


def _incident(**over):
    base = {
        "type": "Feature",
        "geometry": {"type": "LineString",
                     "coordinates": [[101.45, 3.08], [101.46, 3.09]]},
        "properties": {
            "iconCategory": 6,
            "magnitudeOfDelay": 2,
            "startTime": "2026-08-15T10:08:00Z",
            "endTime": "2026-08-15T10:56:00Z",
            "from": "Bandar Bukit Raja",
            "to": "Bandar Bukit Raja",
            "roadNumbers": ["3217"],
            "events": [{"code": 108, "description": "Queuing traffic"}],
        },
    }
    base["properties"].update(over.get("properties", {}))
    return base


def test_slim_keeps_driver_fields():
    i = tt.slim(_incident())
    assert i["cat"] == 6
    # 6 is Jam, not Accident. These tests previously asserted a hand-written
    # map that was shifted against TomTom's published v5 taxonomy, which is
    # how 875 of 1,084 jams came to be published as accidents.
    assert i["catName"] == "Jam"
    assert i["from"] == "Bandar Bukit Raja"
    assert i["lat"] == 3.08 and i["lon"] == 101.45  # first point
    assert i["roads"] == ["3217"]
    assert i["start"].startswith("2026-08-15")
    assert i["delay"] == 2
    assert i["events"] == ["Queuing traffic"]


def test_slim_drops_the_polyline():
    """The frontend renders text, never a line - and polylines were ~90% of the file."""
    assert "polyline" not in tt.slim(_incident())


def test_cat_map_matches_tomtom_v5_taxonomy():
    """Every id -> name pair here is from TomTom's published enum."""
    assert tt.CATS[1] == "Accident"
    assert tt.CATS[6] == "Jam"
    assert tt.CATS[7] == "Lane closed"
    assert tt.CATS[8] == "Road closed"
    assert tt.CATS[9] == "Road works"
    assert tt.CATS[11] == "Flooding"
    assert tt.CATS[14] == "Broken down vehicle"
    # 12, 13, 15-19 do not exist in the enum and must not be invented
    for ghost in (12, 13, 15, 16, 17, 18, 19):
        assert ghost not in tt.CATS


def test_keep_cats_covers_accidents_closures_works():
    assert 1 in tt.KEEP_CATS      # Accident
    assert 6 in tt.KEEP_CATS      # Jam
    assert 7 in tt.KEEP_CATS      # Lane closed
    assert 8 in tt.KEEP_CATS      # Road closed
    assert 9 in tt.KEEP_CATS      # Road works
    assert 11 in tt.KEEP_CATS     # Flooding - it rains here
    assert 14 in tt.KEEP_CATS     # Broken down vehicle
    assert 2 not in tt.KEEP_CATS  # Fog
    assert 4 not in tt.KEEP_CATS  # Rain
    assert 5 not in tt.KEEP_CATS  # Ice
    assert 10 not in tt.KEEP_CATS  # Wind
    # Nothing may be kept that the category map cannot name
    assert not tt.KEEP_CATS - set(tt.CATS)


def test_dedupe_collapses_repeats_and_reciprocals():
    """One jam reported per road segment, in both directions, is one jam."""
    def inc(frm, to, cat=6, event="Stationary traffic"):
        return {"cat": cat, "from": frm, "to": to, "events": [event]}

    out = tt.dedupe([
        inc("A", "B"),
        inc("A", "B"),            # exact repeat
        inc("B", "A"),            # same closure, other direction
        inc("A", "B", event="Roadworks"),   # different event -> kept
        inc("A", "B", cat=8, event="Closed"),  # different category -> kept
        inc("C", "D"),
    ])
    assert len(out) == 4
    assert out[0]["from"] == "A" and out[0]["to"] == "B"


def test_severity_puts_numbered_roads_and_closures_first():
    closed_lane = {"cat": 8, "roads": [], "delay": 4}          # back street
    closed_road = {"cat": 8, "roads": ["E1"], "delay": 4}      # trunk road
    jam_road = {"cat": 6, "roads": ["E2"], "delay": 3}
    works_road = {"cat": 9, "roads": ["B27"], "delay": 1}
    order = sorted([closed_lane, jam_road, works_road, closed_road],
                   key=tt.severity)
    # Numbered roads lead, and within them the worst category leads
    assert order[0] is closed_road
    # A jam is happening now; a roadworks layout has been there for weeks
    assert order[1] is jam_road
    assert order[2] is works_road
    assert order[-1] is closed_lane


def test_per_region_cap_is_small_enough_to_ship():
    """Every visitor downloads this file on every load."""
    assert tt.PER_REGION <= 60


def test_regions_defined():
    assert len(tt.REGIONS) >= 8
    slugs = [r[0] for r in tt.REGIONS]
    for need in ("kl-selangor", "johor", "penang", "melaka",
                 "pahang-cameron", "kuching"):
        assert need in slugs
    # bbox must be 4 numbers (sw lon, sw lat, ne lon, ne lat)
    for _, _, bbox in tt.REGIONS:
        assert len(bbox) == 4
        assert all(isinstance(x, (int, float)) for x in bbox)


def test_take_holds_slots_back_from_roadworks():
    """Roadworks never expire, so on rank alone they fill a region."""
    works = [{"cat": 9, "from": f"W{i}"} for i in range(30)]
    jams = [{"cat": 6, "from": f"J{i}"} for i in range(30)]
    # Ranked order puts jams first now, but feed works first to prove the cap
    out = tt.take(works + jams, 12)
    assert len(out) == 12
    assert sum(1 for i in out if i["cat"] == 9) == 12 // tt.ROADWORKS_SHARE
    assert sum(1 for i in out if i["cat"] == 6) == 12 - 12 // tt.ROADWORKS_SHARE


def test_take_lets_roadworks_spill_rather_than_ship_a_short_region():
    """If roadworks are all there is, a half-empty ticker helps nobody."""
    works = [{"cat": 9, "from": f"W{i}"} for i in range(30)]
    out = tt.take(works, 12)
    assert len(out) == 12
    assert all(i["cat"] == 9 for i in out)


def test_jams_outrank_roadworks_for_a_live_ticker():
    assert tt.CAT_RANK[6] < tt.CAT_RANK[9]
    # ...but never above the things that block a road
    for blocking in (8, 7, 1, 11):
        assert tt.CAT_RANK[blocking] < tt.CAT_RANK[6]
