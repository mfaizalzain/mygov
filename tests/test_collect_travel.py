"""Unit tests for tools/collect_travel.py - the Travel Outlook collector."""
import datetime as dt
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import collect_travel as ct  # noqa: E402


def sample_slow():
    return {
        "holidays": [
            ["2026-08-25", "Prophet Muhammad's Birthday", 1,
             ["*"]],
            ["2026-08-31", "National Day", 1,
             ["*"]],
            ["2026-09-16", "Malaysia Day", 1,
             ["*"]],
            ["2026-10-03", "Some Minor Holiday", 0,
             ["selangor"]],
        ],
        "school": [
            {"type": "cuti_penggal", "group": "B", "start": "2026-08-29",
             "end": "2026-09-06", "name": "Term 2 Break", "days": 9},
        ],
    }


class TestBuildFacts(unittest.TestCase):
    def test_window_filter(self):
        start = "2026-08-11"
        end = "2026-10-06"
        hol, breaks = ct.build_facts(sample_slow(), start, end)
        self.assertEqual(len(hol), 4)           # all four in window
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0]["name"], "Term 2 Break")

    def test_outside_window_dropped(self):
        slow = sample_slow()
        slow["holidays"].append(["2026-11-15", "Far Future Holiday", 1, ["*"]])
        hol, _ = ct.build_facts(slow, "2026-08-11", "2026-10-06")
        self.assertNotIn("Far Future Holiday", [h["name"] for h in hol])

    def test_break_clamped_to_today(self):
        """A break that started before today must only show today+ dates -
        Gemini never sees or emits a past date."""
        slow = {
            "holidays": [],
            "school": [
                {"type": "cuti", "group": "B", "start": "2026-08-05",
                 "end": "2026-08-20", "name": "Ongoing Break", "days": 16},
                {"type": "cuti", "group": "B", "start": "2026-07-01",
                 "end": "2026-07-10", "name": "Past Break", "days": 10},
            ],
        }
        hol, breaks = ct.build_facts(slow, "2026-08-11", "2026-10-06")
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0]["start"], "2026-08-11")  # clamped to today
        self.assertEqual(breaks[0]["end"], "2026-08-20")
        # The past break is gone entirely.
        self.assertNotIn("Past Break", [b["name"] for b in breaks])

    def test_fallback_never_emits_past_dates(self):
        slow = {
            "holidays": [["2026-08-05", "Ancient Holiday", 0, ["*"]]],
            "school": [
                {"type": "cuti", "group": "B", "start": "2026-08-01",
                 "end": "2026-08-30", "name": "Ongoing Break", "days": 30},
            ],
        }
        hol, breaks = ct.build_facts(slow, "2026-08-11", "2026-10-06")
        out = ct.fallback("2026-08-11", hol, breaks)
        self.assertEqual(len(hol), 0)  # holiday before today dropped
        for p in out["periods"]:
            self.assertGreaterEqual(p["start"], "2026-08-11")
            self.assertGreaterEqual(p["end"], "2026-08-11")


class TestImpact(unittest.TestCase):
    def test_extreme_when_major_in_break(self):
        self.assertEqual(ct.impact_of(["National Day"], True), "extreme")

    def test_high_when_break_alone(self):
        self.assertEqual(ct.impact_of([], True), "high")

    def test_high_when_major_alone(self):
        self.assertEqual(ct.impact_of(["Malaysia Day"], False), "high")

    def test_moderate_otherwise(self):
        self.assertEqual(ct.impact_of(["Some Minor Holiday"], False), "moderate")


class TestFallback(unittest.TestCase):
    def test_break_plus_major_is_extreme(self):
        hol, breaks = ct.build_facts(sample_slow(), "2026-08-11", "2026-10-06")
        out = ct.fallback("2026-08-11", hol, breaks)
        periods = out["periods"]
        self.assertTrue(any(p["impact"] == "extreme" for p in periods))
        # The extreme period spans the school break and names National Day.
        extreme = next(p for p in periods if p["impact"] == "extreme")
        self.assertEqual(extreme["start"], "2026-08-29")
        self.assertEqual(extreme["end"], "2026-09-06")
        self.assertIn("National Day", extreme["holidays"])
        self.assertTrue(extreme["t_en"])

    def test_periods_sorted(self):
        hol, breaks = ct.build_facts(sample_slow(), "2026-08-11", "2026-10-06")
        out = ct.fallback("2026-08-11", hol, breaks)
        starts = [p["start"] for p in out["periods"]]
        self.assertEqual(starts, sorted(starts))

    def test_texts_present_and_english_only(self):
        """The outlook is English-only - a stray t_ms would render nowhere
        and would only be a translation the prompt no longer asks for."""
        hol, breaks = ct.build_facts(sample_slow(), "2026-08-11", "2026-10-06")
        out = ct.fallback("2026-08-11", hol, breaks)
        for p in out["periods"]:
            self.assertTrue(p["t_en"])
            self.assertNotIn("t_ms", p)
        for t in out["tips"]:
            self.assertTrue(t["t_en"])
            self.assertNotIn("t_ms", t)
        self.assertGreaterEqual(len(out["tips"]), 2)


class TestParseJson(unittest.TestCase):
    def test_fenced_json(self):
        text = '```json\n{"a": 1}\n```'
        self.assertEqual(ct.parse_json(text), {"a": 1})

    def test_prose_wrapped_json(self):
        text = 'Here you go: {"periods": []} Hope that helps!'
        self.assertEqual(ct.parse_json(text), {"periods": []})

    def test_garbage(self):
        self.assertIsNone(ct.parse_json("not json at all"))

    # The four shapes below all returned None before the parser was hardened,
    # which silently demoted a real outlook to the deterministic fallback.
    def test_raw_newline_inside_string(self):
        text = '{"periods": [{"t_en": "Term 2 Break.\nBook early."}]}'
        out = ct.parse_json(text)
        self.assertEqual(out["periods"][0]["t_en"],
                         "Term 2 Break.\nBook early.")

    def test_raw_tab_inside_string(self):
        self.assertEqual(ct.parse_json('{"t_en": "a\tb"}'), {"t_en": "a\tb"})

    def test_trailing_commas(self):
        text = '{"periods": [{"impact": "high",},],}'
        self.assertEqual(ct.parse_json(text), {"periods": [{"impact": "high"}]})

    def test_trailing_prose_containing_a_brace(self):
        """rfind("}") used to swallow the closing brace of the real object."""
        text = '{"periods": []}\n\nNote: use {name} as the driver field.'
        self.assertEqual(ct.parse_json(text), {"periods": []})

    def test_escaped_quote_survives(self):
        text = r'{"t_en": "the \"peak\" week"}'
        self.assertEqual(ct.parse_json(text), {"t_en": 'the "peak" week'})


class TestBuildOutlookFallback(unittest.TestCase):
    def test_no_key_writes_deterministic(self):
        old = os.environ.get("GOOGLE_API_KEY")
        os.environ.pop("GOOGLE_API_KEY", None)
        try:
            out = ct.build_outlook(sample_slow(), dt.date(2026, 8, 11))
            self.assertEqual(out["source"], "fallback")
            self.assertTrue(out["periods"])
        finally:
            if old is not None:
                os.environ["GOOGLE_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
