from ech_study.probe.campaign_summary import summarize


def trial(pair_id, mode, outcome):
    return {
        "pair_id": pair_id,
        "requested_mode": mode,
        "outcome": outcome,
        "http_status": 200 if outcome in {
            "ech_success", "control_success"
        } else None,
    }


def test_summary_counts_complete_pairs_and_outcomes():
    records = [
        trial("p1", "true", "ech_success"),
        trial("p1", "false", "control_success"),
        trial("p2", "true", "connection_error"),
        trial("p2", "false", "control_success"),
    ]

    report = summarize(records)

    assert report["total_records"] == 4
    assert report["unique_pairs"] == 2
    assert report["complete_pairs"] == 2
    assert report["incomplete_or_malformed_pairs"] == 0
    assert report["paired_outcomes"]["both_success"] == 1
    assert report["paired_outcomes"]["control_only_success"] == 1


def test_summary_detects_incomplete_and_duplicate_pairs():
    records = [
        trial("p1", "true", "ech_success"),
        trial("p2", "true", "ech_success"),
        trial("p2", "true", "ech_success"),
        trial("p2", "false", "control_success"),
    ]

    report = summarize(records)

    assert report["unique_pairs"] == 2
    assert report["complete_pairs"] == 0
    assert report["incomplete_or_malformed_pairs"] == 2
    assert report["pairs_with_duplicate_modes"] == 1


def test_records_without_pair_ids_are_not_counted_as_pairs():
    records = [
        {"requested_mode": "true", "outcome": "ech_success"},
        {"requested_mode": "false", "outcome": "control_success"},
    ]

    report = summarize(records)

    assert report["total_records"] == 2
    assert report["unique_pairs"] == 0
    assert report["complete_pairs"] == 0
