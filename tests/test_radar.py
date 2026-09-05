import datetime as dt
import email.utils
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import collect_radar as cr

MYT = dt.timezone(dt.timedelta(hours=8))


def hours_ago(h):
    """An RFC-2822 pub date `h` hours before now.

    Fixtures here must be anchored to now, never to a fixed date: two separate
    parts of the collector read the clock, and a hardcoded timestamp walks
    through both of them as real time passes.

      - extract_breaking_news() drops anything older than MAX_STORY_AGE_HOURS
        (24), so stale fixtures eventually yield an empty feed
      - breaking_score()'s recency term, max(0, 3.0 - age/4.0), clamps to zero
        at 12h, at which point ranking is decided by corroboration alone and
        the expected order silently inverts

    The original fixtures were dated 14 Aug 2026, so this test passed for about
    twelve hours, ranked wrongly for the next twelve, and returned nothing at
    all after that."""
    return email.utils.format_datetime(dt.datetime.now(MYT) - dt.timedelta(hours=h))


class TestRadar(unittest.TestCase):
    def test_categorize_headline(self):
        self.assertEqual(cr.categorize_headline("Sidang Parlimen lulus usul peruntukan tambahan"), "politik")
        self.assertEqual(cr.categorize_headline("Bursa Malaysia opens higher as Ringgit strengthens"), "ekonomi")
        self.assertEqual(cr.categorize_headline("Polis tahan lima lelaki disyaki terlibat kes samun"), "jenayah")
        self.assertEqual(cr.categorize_headline("Amaran banjir kilat dan tanah runtuh di pantai timur"), "bencana")
        self.assertEqual(cr.categorize_headline("KKM tingkat kawalan denggi di hospital"), "kesihatan")
        self.assertEqual(cr.categorize_headline("Skuad badminton negara buru kejuaraan Liga Dunia"), "sukan")
        self.assertEqual(cr.categorize_headline("Pameran seni kebangsaan bermula hujung minggu ini"), "nasional")

    def test_extract_breaking_news(self):
        signals = [
            {
                "source": "bernama_bm",
                "lang": "ms",
                "title": "Kerajaan umum peruntukan khas RM100 juta baik pulih jambatan",
                "url": "https://www.bernama.com/bm/am/news1.php",
                "pub": hours_ago(2),
                "description": "<p>Dana khas disalurkan segera kepada pihak berkuasa tempatan.</p>"
            },
            {
                "source": "malaymail",
                "lang": "en",
                "title": "Police arrest suspect linked to online investment fraud",
                "url": "https://www.malaymail.com/news/123",
                "pub": hours_ago(2.5),
                "description": "Commercial Crime Investigation Department confirmed the arrest."
            },
            # Duplicate / near-identical title check
            {
                "source": "freemalaysiatoday",
                "lang": "en",
                "title": "Police arrest suspect linked to online investment fraud",
                "url": "https://www.freemalaysiatoday.com/news/456",
                "pub": hours_ago(2 + 25 / 60),
                "description": "Duplicate news report."
            },
            # Sebenarnya signal should be excluded from breaking news
            {
                "source": "sebenarnya",
                "lang": "ms",
                "title": "Penjelasan mengenai dakwaan palsu bantuan tunai",
                "url": "https://sebenarnya.my/penjelasan-123",
                "pub": hours_ago(4),
                "description": "Fact check item."
            }
        ]

        # The fixtures above sit inside both clock-sensitive windows on
        # purpose. Assert that rather than leaving a future threshold change
        # to surface as "0 != 2" or an inverted order, which is how this test
        # failed before the pub dates were anchored to now.
        oldest = 4
        self.assertLess(oldest, cr.MAX_STORY_AGE_HOURS,
                        "fixtures aged out of the breaking-news window")
        self.assertGreater(3.0 - oldest / 4.0, 0,
                           "fixtures fell outside breaking_score's recency ramp, "
                           "so ranking is decided by corroboration alone")

        # Pin the editor offline. gemini_key() falls back to ~/.hermes/.env,
        # so on a developer machine that has one this test would post the
        # fixtures to Gemini and assert against whatever the model returned -
        # a network call and a non-deterministic ranking, where CI (no key)
        # silently ran the deterministic path instead. The assertions below
        # describe that deterministic path: `rank` is only set there, and
        # `category` is categorize_headline's output, not the editor's.
        with mock.patch.object(cr, "gemini_key", return_value=None):
            breaking = cr.extract_breaking_news(signals, limit=10)

        # Four signals in, two out: the sebenarnya fact-check is excluded as a
        # non-news source, and the FreeMalaysiaToday copy of the police story
        # is dropped as a duplicate headline.
        self.assertEqual(len(breaking), 2)
        self.assertEqual([b["source_name"] for b in breaking],
                         ["Malay Mail", "Bernama"])
        self.assertEqual([b["rank"] for b in breaking], [1, 2])
        self.assertNotIn("freemalaysiatoday", [b["source"] for b in breaking])
        self.assertNotIn("sebenarnya", [b["source"] for b in breaking])

        # Malay Mail leads on consequence, not recency - it is the older of
        # the two. Asserting the order this way round is the point of the
        # test: 0054d2c replaced "newest first" with breaking_score(), and
        # these expectations were left describing the recency ranking, which
        # is why CI went red on that commit and stayed red.
        self.assertGreater(breaking[0]["breaking_score"],
                           breaking[1]["breaking_score"])

        self.assertEqual(breaking[0]["category"], "jenayah")
        self.assertEqual(breaking[1]["category"], "politik")
        # Descriptions arrive as feed HTML and must be cleaned before display.
        self.assertNotIn("<p>", breaking[1]["summary"])


class TestParseJsonTruncation(unittest.TestCase):
    """Regression tests for the MAX_TOKENS truncation repair (see commit for
    the 2026-09-05 viral-list fix).

    Root cause: Gemini's finishReason=MAX_TOKENS cuts the response mid-JSON.
    The old parse_json_text balanced-brace scan then threw 'no JSON object
    found', which every caller treated as total failure -> the crude keyword
    cluster (single garbage words like 'Makluman', 'Tidak', 'Snapshot' as
    'top issues'), plus the grounded fact-check and the breaking-news editor
    each silently returning nothing. These fixtures are the exact truncated
    shapes (mid-string, mid-key, mid-value) and must now recover the complete
    leading structure instead of failing.
    """
    def test_mid_string_value(self):
        # Fact-check cut mid fact_details value.
        t = ('{"claim": "Sindiket penipuan dikesan menggunakan dokumen Pesanan '
             'Kerajaan palsu.", "verdict": "TRUE", "fact_details": "Jabatan Alam '
             'Sekitar Wilayah Persekutuan Kuala Lumpur (JAS WPKL) mengesahkan telah '
             'mengesan sekurang-kurangnya tiga percubaan penipuan membabitkan')
        parsed = cr.parse_json_text(t)
        self.assertEqual(parsed["verdict"], "TRUE")
        self.assertIn("claim", parsed)

    def test_cluster_truncated(self):
        # Clustered issues cut inside the first issue's fact_data.
        t = ('{"top_issues": [{"rank": 1, "title_bm": "Penipuan Pesanan Palsu", '
             '"title_en": "Fake order scam", "category": "jenayah", "claim": '
             '"Dokumen palsu", "fact_details": "Butiran penuh masih')
        parsed = cr.parse_json_text(t)
        self.assertIn("top_issues", parsed)
        self.assertEqual(parsed["top_issues"][0]["rank"], 1)

    def test_editor_truncated(self):
        # Breaking-news editor cut inside the bullets array.
        t = ('{"items": [{"id": 1, "index": 0, "summary": "Menteri umumkan dasar '
             'baru", "category": "nasional", "urgency": "high", "bullets": '
             '["Apa yang berlaku", "Siapa terlibat"')
        parsed = cr.parse_json_text(t)
        self.assertIn("items", parsed)
        self.assertEqual(parsed["items"][0]["id"], 1)

    def test_complete_json_still_parses(self):
        # A well-formed response must be unaffected by the new repair path.
        t = '{"verdict": "TRUE", "claim": "x", "sources": ["SEBENARNYA.MY"]}'
        parsed = cr.parse_json_text(t)
        self.assertEqual(parsed["verdict"], "TRUE")

    def test_deeply_nested_truncation(self):
        # Nested array inside object inside array, cut mid-string.
        t = ('{"top_issues": [{"rank": 1, "sources": [{"name": "malaymail", '
             '"title": "Some headline here that keeps going and may get"')
        parsed = cr.parse_json_text(t)
        self.assertIn("top_issues", parsed)
        self.assertEqual(parsed["top_issues"][0]["rank"], 1)

    def test_gemini_post_retries_on_max_tokens(self):
        # The auto-retry on MAX_TOKENS must bump the budget, not resend the
        # same truncation.
        calls = {"n": 0}
        req_bodies = []

        def fake_urlopen(req, timeout=None):
            body = req.data.decode()
            req_bodies.append(body)
            calls["n"] += 1
            if calls["n"] == 1:
                return _FakeResp({"candidates": [{"finishReason": "MAX_TOKENS"}]})
            return _FakeResp({"candidates": [{"finishReason": "STOP",
                                              "content": {"parts": [{"text": "{}"}]}}]})

        with mock.patch.object(cr.urllib.request, "urlopen", side_effect=fake_urlopen):
            d = cr.gemini_post("http://x", json.dumps({
                "generationConfig": {"maxOutputTokens": 8192}}).encode())
        self.assertEqual(calls["n"], 2)
        # Second request carried a doubled budget.
        self.assertIn("maxOutputTokens\": 16384", req_bodies[1])


class _FakeResp:
    def __init__(self, d):
        self._d = d

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._d).encode()


if __name__ == "__main__":
    unittest.main()
