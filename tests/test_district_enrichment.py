import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from collect_geo import build_district_socio, district_eth_sx, num


def _cur():
    """A tiny stand-in for the latest-year slice of population_district:
    pure-python rows that support the same attribute access as itertuples."""
    class Row:
        def __init__(self, **kw):
            self.__dict__.update(kw)
    rows = [
        # sex == both, age == overall -> ethnicity rows
        Row(state="Selangor", district="Petaling", sex="both", age="overall",
            ethnicity="bumi_malay", population=1300.0),
        Row(state="Selangor", district="Petaling", sex="both", age="overall",
            ethnicity="chinese", population=500.0),
        Row(state="Selangor", district="Petaling", sex="both", age="overall",
            ethnicity="overall", population=2370.6),
        # age == overall, ethnicity == overall -> sex rows
        Row(state="Selangor", district="Petaling", sex="male", age="overall",
            ethnicity="overall", population=1200.0),
        Row(state="Selangor", district="Petaling", sex="female", age="overall",
            ethnicity="overall", population=1170.6),
        # a district with no sex rows -> eth only
        Row(state="Kelantan", district="Jeli", sex="both", age="overall",
            ethnicity="bumi_malay", population=55.0),
        Row(state="Kelantan", district="Jeli", sex="both", age="overall",
            ethnicity="overall", population=58.2),
        # a district with no ethnicity rows -> sx only
        Row(state="Sarawak", district="Bukit Mabong", sex="male", age="overall",
            ethnicity="overall", population=5.5),
        Row(state="Sarawak", district="Bukit Mabong", sex="female", age="overall",
            ethnicity="overall", population=5.2),
    ]
    # The function filters with pandas-style boolean masks on the frame; feed
    # it a tiny real DataFrame so the groupby/filter code path runs.
    import pandas as pd
    return pd.DataFrame([r.__dict__ for r in rows])


def test_district_eth_sx_full():
    out = district_eth_sx(_cur())
    pet = out[("Selangor", "Petaling")]
    assert pet["eth"]["bumi_malay"] == 1300.0
    assert pet["eth"]["chinese"] == 500.0
    assert pet["sx"] == {"male": 1200.0, "female": 1170.6}
    assert "overall" not in pet["eth"]       # totals excluded


def test_district_eth_only_when_no_sex_rows():
    out = district_eth_sx(_cur())
    jeli = out[("Kelantan", "Jeli")]
    assert jeli["eth"]["bumi_malay"] == 55.0
    assert "sx" not in jeli


def test_district_sx_only_when_no_ethnicity_rows():
    out = district_eth_sx(_cur())
    bm = out[("Sarawak", "Bukit Mabong")]
    assert bm["sx"] == {"male": 5.5, "female": 5.2}
    assert "eth" not in bm


def test_district_socio_joins_on_state_district():
    rows = [
        {"n": "Petaling", "s": "Selangor", "p": 2370.6, "g": 0.46},
        {"n": "Jeli", "s": "Kelantan", "p": 58.2, "g": 0.5},
    ]

    def fake_api(ds, **params):
        if ds == "hh_income_district":
            return [{"date": "2024-01-01", "state": "Selangor", "district": "Petaling",
                     "income_mean": 11800, "income_median": 10688},
                    {"date": "2024-01-01", "state": "Kelantan", "district": "Jeli",
                     "income_mean": 3200, "income_median": 3008},
                    {"date": "2022-01-01", "state": "Selangor", "district": "Petaling",
                     "income_mean": 10000, "income_median": 9000}]
        if ds == "hh_poverty_district":
            return [{"date": "2024-01-01", "state": "Kelantan", "district": "Jeli",
                     "poverty_absolute": 10.1}]
        if ds == "hh_inequality_district":
            return [{"date": "2024-01-01", "state": "Selangor", "district": "Petaling",
                     "gini": 0.387}]
        return []

    import collect_geo
    orig = collect_geo.api
    collect_geo.api = fake_api
    try:
        socio = build_district_socio(rows)
    finally:
        collect_geo.api = orig

    pet = socio[("Selangor", "Petaling")]
    assert pet["inc"] == 10688            # newest year wins (2024, not 2022)
    assert pet["gini"] == 0.387
    jeli = socio[("Kelantan", "Jeli")]
    assert jeli["inc"] == 3008
    assert jeli["pov"] == 10.1
    assert "gini" not in jeli             # absent dataset -> key omitted
    assert len(socio) == 2


def test_district_socio_skips_unwanted_districts():
    def fake_api(ds, **params):
        return [{"date": "2024-01-01", "state": "Pahang", "district": "Cameron Highlands",
                 "income_mean": 9999, "income_median": 8888}]
    import collect_geo
    orig = collect_geo.api
    collect_geo.api = fake_api
    try:
        socio = build_district_socio([{"n": "Petaling", "s": "Selangor"}])
    finally:
        collect_geo.api = orig
    assert socio == {}


def test_num_rounding():
    assert num(1.23456, 2) == 1.23
    assert num("3.0", 0) == 3.0
    assert num(None) is None
