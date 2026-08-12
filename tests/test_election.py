import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import collect_election as ce


def test_num_parser():
    assert ce._num("24,267") == 24267
    assert ce._num("1,696,732") == 1696732
    assert ce._num(None) is None
    assert ce._num("abc") is None


def test_token_of():
    assert ce.token_of('<input type="hidden" name="_token" value="ABCD1234">') == "ABCD1234"
    assert ce.token_of('var formData = {"_token": "WXYZ9999", "kategori": "PRU"};') == "WXYZ9999"


def test_parse_result():
    j = {
        "pilihanraya": [{
            "NamaSingkatan": "PRU KE - 15 (2022)",
            "TarikhPengundian": "19 Nov 2022",
            "penamaan": [
                {"NamaUndiCalon": "A", "StatusCalon": "MNG", "BilUndi": "1,000",
                 "parti": {"Penerangan": "PERIKATAN NASIONAL (PN)", "NamaSingkatan": "PN",
                           "WarnaParti": "#002e4d"}, "parti_bebas": None},
                {"NamaUndiCalon": "B", "StatusCalon": "HD", "BilUndi": "400",
                 "parti": {"Penerangan": "PARTI A", "NamaSingkatan": "PA",
                           "WarnaParti": "#ff0000"}, "parti_bebas": None},
            ],
        }],
        "namaParDun": "P.001 PADANG BESAR",
        "penamaanMenang": {"NamaUndiCalon": "A", "BilUndi": "1,000",
                           "parti": {"NamaSingkatan": "PN", "WarnaParti": "#002e4d"}},
    }
    seat = ce.parse_result(j, "pru")
    assert seat["election"] == "PRU KE - 15 (2022)"
    assert seat["date"] == "19 Nov 2022"
    assert seat["totalVotes"] == 1400
    assert seat["majority"] == 600
    assert len(seat["candidates"]) == 2
    assert seat["candidates"][0]["isWinner"] is True
    assert seat["candidates"][0]["votes"] == 1000
    assert seat["candidates"][1]["partyShort"] == "PA"


def test_parse_result_no_penamaan():
    """When the JSON only carries the winner (no full candidate list)."""
    j = {"pilihanraya": [{"NamaSingkatan": "PRK", "TarikhPengundian": "9 Jul 2026"}],
         "penamaanMenang": {"NamaUndiCalon": "W", "BilUndi": "5,000",
                            "parti": {"Penerangan": "PARTI X", "NamaSingkatan": "PX",
                                      "WarnaParti": "#123456"}}}
    seat = ce.parse_result(j, "prk")
    assert len(seat["candidates"]) == 1
    assert seat["candidates"][0]["isWinner"] is True
