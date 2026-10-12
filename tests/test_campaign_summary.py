from ech_study.probe.campaign_summary import summarize


def trial(pair_id, mode, outcome, destination_id="dest-01", endpoint="https://one.test/"):
    return {
        "pair_id": pair_id,
        "requested_mode": mode,
        "outcome": outcome,
        "destination_id": destination_id,
        "endpoint": endpoint,
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
    assert report["paired_outcomes"]["at_least_one_outcome_unresolved"] == 1


def test_pair_categories_distinguish_known_errors_and_unresolved_outcomes():
    records = [
        trial("both", "true", "ech_success"),
        trial("both", "false", "control_success"),
        trial("ech-only", "true", "ech_success"),
        trial("ech-only", "false", "http_error"),
        trial("control-only", "true", "http_error"),
        trial("control-only", "false", "control_success"),
        trial("neither-known", "true", "http_error"),
        trial("neither-known", "false", "http_error"),
        trial("probe-error", "true", "ech_success"),
        trial("probe-error", "false", "probe_error"),
        trial("inconclusive", "true", "inconclusive"),
        trial("inconclusive", "false", "unknown"),
        trial("connection-error", "true", "connection_error"),
        trial("connection-error", "false", "http_error"),
    ]

    report = summarize(records)

    assert report["paired_outcomes"] == {
        "both_success": 1,
        "ech_only_success": 1,
        "control_only_success": 1,
        "neither_success_both_outcomes_known": 1,
        "at_least_one_outcome_unresolved": 3,
    }
    assert report["ech_outcome_counts"]["ech_success"] == 3
    assert report["control_outcome_counts"]["control_success"] == 2


def test_missing_outcome_is_unresolved_not_a_confirmed_failure():
    records = [
        trial("p1", "true", "ech_success"),
        trial("p1", "false", None),
    ]

    report = summarize(records)

    assert report["paired_outcomes"]["at_least_one_outcome_unresolved"] == 1
    assert report["paired_outcomes"]["ech_only_success"] == 0
    assert report["outcome_counts"]["missing"] == 1


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
    assert report["pairs_missing_or_unexpected_trials"] == 2


def test_summary_flags_pairs_with_mismatched_destinations_or_endpoints():
    records = [
        trial("p1", "true", "ech_success", "dest-01", "https://one.test/"),
        trial("p1", "false", "control_success", "dest-02", "https://two.test/"),
    ]

    report = summarize(records)

    assert report["complete_pairs"] == 0
    assert report["incomplete_or_malformed_pairs"] == 1
    assert report["pairs_with_mismatched_destinations_or_endpoints"] == 1
    assert report["pair_details"][0]["validation_errors"] == [
        "mismatched_destinations_or_endpoints"
    ]


def test_summary_flags_endpoint_mismatch_even_when_destination_id_matches():
    records = [
        trial("p1", "true", "ech_success", "dest-01", "https://one.test/"),
        trial("p1", "false", "control_success", "dest-01", "https://two.test/"),
    ]

    report = summarize(records)

    assert report["complete_pairs"] == 0
    assert report["pairs_with_mismatched_destinations_or_endpoints"] == 1


def test_summary_does_not_validate_pairs_without_destination_metadata():
    records = [
        {"pair_id": "p1", "requested_mode": "true", "outcome": "ech_success"},
        {"pair_id": "p1", "requested_mode": "false", "outcome": "control_success"},
    ]

    report = summarize(records)

    assert report["complete_pairs"] == 0
    assert report["pairs_missing_destination_or_endpoint"] == 1


def test_summary_reports_attempts_outcomes_and_pairs_per_destination():
    records = [
        trial("p1", "true", "ech_success", "dest-01", "https://one.test/"),
        trial("p1", "false", "control_success", "dest-01", "https://one.test/"),
        trial("p2", "true", "http_error", "dest-02", "https://two.test/"),
        trial("p2", "false", "probe_error", "dest-02", "https://two.test/"),
    ]

    report = summarize(records)

    assert report["attempted_records"] == 4
    assert len(report["per_destination"]) == 2
    first, second = report["per_destination"]
    assert (first["destination_id"], first["endpoint"]) == (
        "dest-01", "https://one.test/"
    )
    assert first["attempted_records"] == 2
    assert first["complete_pairs"] == 1
    assert first["paired_outcomes"]["both_success"] == 1
    assert (second["destination_id"], second["endpoint"]) == (
        "dest-02", "https://two.test/"
    )
    assert second["attempted_records"] == 2
    assert second["ech_outcome_counts"] == {"http_error": 1}
    assert second["control_outcome_counts"] == {"probe_error": 1}
    assert second["paired_outcomes"]["at_least_one_outcome_unresolved"] == 1


def test_records_without_pair_ids_are_not_counted_as_pairs():
    records = [
        {"requested_mode": "true", "outcome": "ech_success"},
        {"requested_mode": "false", "outcome": "control_success"},
    ]

    report = summarize(records)

    assert report["total_records"] == 2
    assert report["unique_pairs"] == 0
    assert report["complete_pairs"] == 0
