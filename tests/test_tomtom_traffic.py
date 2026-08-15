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
            "startTime": "2026-08-15T10:08:00Z",
            "endTime": "2026-08-15T10:56:00Z",
            "from": "Bandar Bukit Raja",
            "to": "Bandar Bukit Raja",
            "roadNumbers": ["3217"],
        },
    }
    base["properties"].update(over.get("properties", {}))
    return base


def test_slim_keeps_driver_fields():
    i = tt.slim(_incident())
    assert i["cat"] == 6
    assert i["catName"] == "Accident"
    assert i["from"] == "Bandar Bukit Raja"
    assert i["lat"] == 3.08 and i["lon"] == 101.45  # first point
    assert i["roads"] == ["3217"]
    assert i["start"].startswith("2026-08-15")


def test_slim_drops_weather_noise():
    """Weather (iconCategory 15) and fog (2) are not driver-relevant -> dropped."""
    weather = tt.slim(_incident(properties={"iconCategory": 15}))
    assert weather["cat"] == 15
    assert weather["catName"] == "Weather"
    # The keep filter is applied in main(), but the CATS map must cover it
    assert 15 not in tt.KEEP_CATS


def test_keep_cats_covers_accidents_closures_works():
    assert 6 in tt.KEEP_CATS      # Accident
    assert 7 in tt.KEEP_CATS      # Road closed
    assert 8 in tt.KEEP_CATS      # Road works
    assert 9 in tt.KEEP_CATS      # Hazard
    assert 10 in tt.KEEP_CATS     # Jam
    assert 2 not in tt.KEEP_CATS  # Fog
    assert 5 not in tt.KEEP_CATS  # Ice


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
