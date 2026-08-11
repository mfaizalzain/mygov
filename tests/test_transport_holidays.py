import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from collect_transport import count_trips_for_day
from collect_slow import parse_mycal_holidays


# ── count_trips_for_day (GTFS calendar logic) ─────────────────────────
def _cal():
    """Weekday + weekend services, valid 2026-01-01 .. 2026-12-31."""
    return {
        "weekday": {"days": ["1", "1", "1", "1", "1", "0", "0"],
                    "start": "2026-01-01", "end": "2026-12-31"},
        "weekend": {"days": ["0", "0", "0", "0", "0", "1", "1"],
                    "start": "2026-01-01", "end": "2026-12-31"},
    }


def test_weekday_counts_weekday_service_only():
    # 2026-08-11 is a Tuesday
    n = count_trips_for_day(_cal(), {}, ["weekday", "weekend", "weekday"], "2026-08-11")
    assert n == 2          # both weekday trips run


def test_weekend_counts_weekend_service_only():
    # 2026-08-15 is a Saturday
    n = count_trips_for_day(_cal(), {}, ["weekday", "weekend", "weekday"], "2026-08-15")
    assert n == 1          # only the weekend trip runs


def test_outside_service_window_returns_zero():
    n = count_trips_for_day(_cal(), {}, ["weekday"], "2027-06-01")
    assert n == 0


def test_calendar_dates_adds_service():
    cal = _cal()
    dates = {"weekend": {"2026-08-11": True}}     # Saturday service on Tuesday
    n = count_trips_for_day(cal, dates, ["weekend"], "2026-08-11")
    assert n == 1


def test_calendar_dates_removes_service():
    dates = {"weekday": {"2026-08-11": False}}    # public holiday - no weekday service
    n = count_trips_for_day(_cal(), dates, ["weekday"], "2026-08-11")
    assert n == 0


def test_unknown_service_is_inactive():
    n = count_trips_for_day(_cal(), {}, ["ghost_service"], "2026-08-11")
    assert n == 0


def test_empty_services_counts_zero():
    assert count_trips_for_day(_cal(), {}, [], "2026-08-11") == 0


def test_sunday_uses_index_6():
    # 2026-08-16 is a Sunday - the index-6 bug (weekday[:5] slice) would crash
    n = count_trips_for_day(_cal(), {}, ["weekend"], "2026-08-16")
    assert n == 1


# ── parse_mycal_holidays (mycal payload shaping) ──────────────────────
def test_holiday_shape_and_sort():
    rows = parse_mycal_holidays([
        {"date": "2026-08-31", "name": {"en": "National Day"},
         "states": ["kuala-lumpur", "selangor", "johor", "kedah", "kelantan",
                    "terengganu", "perlis", "pahang", "perak", "sabah",
                    "sarawak", "melaka", "negeri-sembilan", "wp-putrajaya",
                    "wp-labuan", "pulau-pinang"]},
        {"date": "2026-08-25", "name": {"en": "Maulidur Rasul"},
         "states": ["kuala-lumpur", "selangor", "johor", "kedah", "kelantan",
                    "terengganu", "perlis", "pahang", "perak", "sabah",
                    "sarawak", "melaka", "negeri-sembilan", "wp-putrajaya",
                    "wp-labuan", "pulau-pinang"]},
    ])
    assert [r[0] for r in rows] == ["2026-08-25", "2026-08-31"]   # sorted
    assert rows[0][1] == "Maulidur Rasul"
    assert rows[1][3][:2] == ["kuala-lumpur", "selangor"]          # states kept
    assert len(rows[1][3]) == 16                                   # federal = all


def test_holiday_major_flag():
    rows = parse_mycal_holidays([
        {"date": "2026-02-17", "name": {"en": "Chinese New Year's Day"},
         "states": ["selangor", "kuala-lumpur"]},
        {"date": "2026-01-01", "name": {"en": "New Year's Day"},
         "states": ["selangor", "kuala-lumpur"]},
    ])
    by_date = {r[0]: r for r in rows}
    assert by_date["2026-02-17"][2] == 1      # CNY is major (travel-moving)
    assert by_date["2026-01-01"][2] == 0      # NYD is not


def test_holiday_drops_observances_and_states():
    rows = parse_mycal_holidays([
        {"date": "2026-02-14", "name": {"en": "Valentine's Day"},
         "states": ["selangor", "kuala-lumpur"]},   # NOT_HOLIDAYS -> dropped
        {"date": "2026-05-01", "name": {"en": "Labour Day"},
         "states": ["selangor", "kuala-lumpur"]},   # kept
        {"date": "2026-06-01", "name": {"en": "No States Day"},
         "states": []},                              # no states -> dropped
    ])
    assert [r[1] for r in rows] == ["Labour Day"]


def test_holiday_ignores_missing_name():
    rows = parse_mycal_holidays([
        {"date": "2026-07-01", "name": {}, "states": ["selangor"]},
    ])
    assert rows == []


def test_holiday_empty_payload_is_safe():
    assert parse_mycal_holidays(None) == []
    assert parse_mycal_holidays([]) == []
