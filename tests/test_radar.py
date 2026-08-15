import datetime as dt
import email.utils
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


if __name__ == "__main__":
    unittest.main()
