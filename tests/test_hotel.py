import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import collect_hotel as ch


def test_quarters():
    assert ch.QUARTERS == {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}
    assert ch.QM_START[1] == "Jan" and ch.QM_END[4] == "Dis"
    assert ch.QM_END[3] == "Sep"


def test_num_parser():
    assert ch._num("RM393.4") == 393.4
    assert ch._num("1,696,732") == 1696732
    assert ch._num("33.5%") == 33.5
    assert ch._num("51.9%") == 51.9
    assert ch._num("") is None
    assert ch._num("x") is None


def test_state_labels_multiword():
    """Multi-word states must anchor on the label CENTER (values sit under
    the middle of 'Negeri Sembilan', not under the first word)."""
    words = [
        (74.1, 765.3, "Negeri"), (112.1, 765.3, "Sembilan"),
        (297.7, 769.0, "Johor"),
        (165.3, 836.1, "Kuala"), (198.4, 836.1, "Lumpur"),
    ]
    labels = dict((st, (x, y)) for st, x, y in ch._state_labels(words))
    assert "Negeri Sembilan" in labels
    ns_x = labels["Negeri Sembilan"][0]
    assert 90 < ns_x < 100, f"center anchor expected ~93, got {ns_x}"
    assert abs(labels["Negeri Sembilan"][1] - 765.3) < 1
    assert labels["Johor"][0] == 297.7
    kl_x = labels["Kuala Lumpur"][0]
    assert 175 < kl_x < 190, f"center anchor expected ~182, got {kl_x}"


def test_match_col():
    row = [(69.1, 618.2, "79,844"), (117.1, 618.2, "80,551"),
           (162.8, 618.2, "149,806")]
    assert ch._match_col(row, 71.6, 618.2, x_tol=28)[2] == "79,844"
    assert ch._match_col(row, 160.2, 618.2, x_tol=28)[2] == "149,806"
    # far away -> None
    assert ch._match_col(row, 400.0, 618.2, x_tol=28) is None
