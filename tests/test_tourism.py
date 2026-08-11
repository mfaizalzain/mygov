import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import collect_tourism as ct


def test_malay_to_num():
    assert ct.malay_to_num("mac") == 3
    assert ct.malay_to_num("dis") == 12
    assert ct.malay_to_num("may") == 5
    assert ct.malay_to_num("mei") is None  # wrong slug - files use 'may'


def test_month_label():
    assert ct.month_label(2026, 5) == "May 2026"
    assert ct.month_label(2026, 3) == "March 2026"


def test_num_parser():
    assert ct._num("1,696,732") == 1696732
    assert ct._num("(4.7)") == -4.7
    assert ct._num("11.9") == 11.9
    assert ct._num("-") is None
    assert ct._num("") is None
    assert ct._num(None) is None
    assert ct._num("92") == 92


def test_parse_visitor_pdf_fixture():
    """Parse the REAL May 2026 PDF (version-pinned in tests/fixtures) -
    the strongest layout-drift guard, since it exercises the true table."""
    path = os.path.join(os.path.dirname(__file__), "fixtures",
                        "top_51_may_2026_visitor.pdf")
    with open(path, "rb") as f:
        pdf = f.read()
    rows, totals = ct.parse_visitor_pdf(pdf)
    assert len(rows) == 52                 # 51 countries + OTHERS
    assert rows[0]["country"] == "Singapore"
    assert rows[0]["rank"] == 1
    assert rows[0]["cur"] == 1899217       # May 2026 arrivals
    assert rows[0]["prev"] == 1696732      # April 2026
    assert rows[0]["g_mom"] == 11.9
    assert rows[0]["ytd26"] == 8737229
    assert rows[1]["country"] == "China"
    assert rows[1]["cur"] == 384290
    assert rows[1]["g_mom"] == -4.7        # parenthesised = negative
    assert totals is not None
    assert totals["cur"] == 3497541        # GRAND TOTAL May 2026
    assert totals["ytd26"] == 17513742
    # every country rank 1..52 present, unique
    ranks = [r["rank"] for r in rows]
    assert ranks == sorted(ranks) and len(set(ranks)) == 52
    # totals > any single country
    assert totals["cur"] > rows[0]["cur"]
