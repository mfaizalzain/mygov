import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import collect_radar as cr


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
                "pub": "Fri, 14 Aug 2026 08:00:00 +0800",
                "description": "<p>Dana khas disalurkan segera kepada pihak berkuasa tempatan.</p>"
            },
            {
                "source": "malaymail",
                "lang": "en",
                "title": "Police arrest suspect linked to online investment fraud",
                "url": "https://www.malaymail.com/news/123",
                "pub": "Fri, 14 Aug 2026 07:30:00 +0800",
                "description": "Commercial Crime Investigation Department confirmed the arrest."
            },
            # Duplicate / near-identical title check
            {
                "source": "freemalaysiatoday",
                "lang": "en",
                "title": "Police arrest suspect linked to online investment fraud",
                "url": "https://www.freemalaysiatoday.com/news/456",
                "pub": "Fri, 14 Aug 2026 07:35:00 +0800",
                "description": "Duplicate news report."
            },
            # Sebenarnya signal should be excluded from breaking news
            {
                "source": "sebenarnya",
                "lang": "ms",
                "title": "Penjelasan mengenai dakwaan palsu bantuan tunai",
                "url": "https://sebenarnya.my/penjelasan-123",
                "pub": "Fri, 14 Aug 2026 06:00:00 +0800",
                "description": "Fact check item."
            }
        ]

        breaking = cr.extract_breaking_news(signals, limit=10)
        self.assertEqual(len(breaking), 2)
        self.assertEqual(breaking[0]["rank"], 1)
        self.assertEqual(breaking[0]["source_name"], "Bernama")
        self.assertEqual(breaking[0]["category"], "politik")
        self.assertNotIn("<p>", breaking[0]["summary"])
        self.assertEqual(breaking[1]["rank"], 2)
        self.assertEqual(breaking[1]["source_name"], "Malay Mail")
        self.assertEqual(breaking[1]["category"], "jenayah")


if __name__ == "__main__":
    unittest.main()
