import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from collect_cars import aggregate

import pandas as pd


def _df():
    rows = [
        # Jan: 2 petrol, 1 electric (EV share 33.3%)
        {"date_reg": "2026-01-05", "type": "motokar", "maker": "Perodua",
         "model": "Axia", "colour": "white", "fuel": "petrol", "state": "Rakan Niaga"},
        {"date_reg": "2026-01-12", "type": "motokar", "maker": "Proton",
         "model": "Saga", "colour": "silver", "fuel": "petrol", "state": "Selangor"},
        {"date_reg": "2026-01-20", "type": "motokar", "maker": "BYD",
         "model": "Seal", "colour": "blue", "fuel": "electric", "state": "Johor"},
        # Feb: 1 petrol, 1 electric (EV share 50%), new maker Chery
        {"date_reg": "2026-02-03", "type": "motokar", "maker": "Perodua",
         "model": "Myvi", "colour": "red", "fuel": "petrol", "state": "Rakan Niaga"},
        {"date_reg": "2026-02-15", "type": "motokar", "maker": "Chery",
         "model": "iCaur V23", "colour": "orange", "fuel": "electric",
         "state": "Rakan Niaga"},
    ]
    return pd.DataFrame(rows)


def test_monthly_totals_and_fuels():
    d = aggregate(_df())
    assert d["months"] == ["2026-01", "2026-02"]
    assert d["total"] == [3, 2]
    assert d["byFuel"]["petrol"] == [2, 1]
    assert d["byFuel"]["electric"] == [1, 1]
    assert d["byFuel"]["diesel"] == [0, 0]       # absent fuels are zero-filled


def test_ev_share():
    d = aggregate(_df())
    assert d["evShare"] == [33.3, 50.0]


def test_top_makers_ordered():
    d = aggregate(_df())
    # Perodua 2, then Proton/BYD/Chery 1 each
    assert d["topMakers"][0] == {"name": "Perodua", "n": 2}
    names = [m["name"] for m in d["topMakers"]]
    assert names[:4] == ["Perodua", "Proton", "BYD", "Chery"]


def test_fuel_mix_and_state_split():
    d = aggregate(_df())
    assert d["fuelMix"]["petrol"] == 3
    assert d["fuelMix"]["electric"] == 2
    assert d["rows"] == 5
    assert d["asOf"] == "2026-02-15"
    assert d["year"] == 2026


def test_ev_share_none_when_empty_month():
    df = _df()
    # a third month with zero rows must not divide by zero
    d = aggregate(df[df.date_reg < "2026-02-01"])
    assert d["evShare"] == [33.3]
