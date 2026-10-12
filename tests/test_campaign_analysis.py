import json
import sys

import pytest

from ech_study.probe.campaign_summary import analyze_campaigns, main


def record(pair_id, mode, outcome, *, endpoint="https://a.example/", resolver="https://doh.example/dns-query", destination="dest-01", network="wifi"):
    return {
        "campaign_id": "run-1",
        "timestamp_utc": "2026-10-10T10:00:00+00:00",
        "network": network,
        "destination_id": destination,
        "endpoint": endpoint,
        "resolver": resolver,
        "pair_id": pair_id,
        "pair_position": 1 if mode == "true" else 2,
        "requested_mode": mode,
        "outcome": outcome,
        "ech_status": "succeeded" if mode == "true" and outcome == "ech_success" else "unknown",
        "return_code": 0 if outcome in {"ech_success", "control_success"} else 101,
        "http_status": 200 if outcome in {"ech_success", "control_success"} else 0,
        "ech_rejection_observed": False,
        "ech_retry_config_received": False,
    }


def test_analysis_groups_campaign_endpoint_resolver_mode_and_pairs():
    campaigns = {
        "first_20261010.jsonl": [
            record("p1", "true", "ech_success"),
            record("p1", "false", "control_success"),
            record("p2", "true", "connection_error", endpoint="https://b.example/"),
            record("p2", "false", "control_success", endpoint="https://b.example/"),
        ],
        "second_20261011.jsonl": [
            record("p1", "true", "ech_success", resolver="https://other.example/dns-query"),
            record("p1", "false", "control_success", resolver="https://other.example/dns-query"),
        ],
    }

    report = analyze_campaigns(campaigns)

    assert report["campaign_count"] == 2
    assert report["total_records"] == 6
    first, second = report["campaigns"]
    assert first["pair_count"] == 2
    assert first["field_counts"]["requested_mode"] == {"false": 2, "true": 2}
    assert [item["value"] for item in first["breakdowns"]["endpoint"]] == [
        "https://a.example/", "https://b.example/"
    ]
    assert first["breakdowns"]["resolver"][0]["value"] == "https://doh.example/dns-query"
    assert first["pair_details"][0]["paired_category"] == "both_success"
    assert first["pair_details"][1]["paired_category"] == "at_least_one_outcome_unresolved"
    assert second["pair_count"] == 1
    assert second["campaign_file"] == "second_20261011.jsonl"


def test_analysis_warns_on_filename_date_and_generic_network_label():
    records = [
        record("p1", "true", "ech_success", network="current_connection"),
        record("p1", "false", "control_success", network="current_connection"),
    ]

    report = analyze_campaigns({"hotspot_20261012.jsonl": records})
    campaign = report["campaigns"][0]

    assert campaign["timestamp_utc"]["date_counts"] == {"2026-10-10": 2}
    assert campaign["data_quality_warnings"]["filename_date_differs_from_record_timestamps"] == 1
    assert campaign["data_quality_warnings"]["network_label_does_not_identify_access_type"] == 2


def test_analysis_flags_duplicate_modes_and_missing_or_mismatched_fields():
    records = [
        record("p1", "true", "ech_success"),
        record("p1", "true", "ech_success", endpoint="https://other.example/"),
        record("p2", "false", "control_success"),
    ]
    records[2].pop("resolver")

    report = analyze_campaigns({"campaign.jsonl": records})
    campaign = report["campaigns"][0]
    duplicate_pair = next(pair for pair in campaign["pair_details"] if pair["pair_id"] == "p1")
    missing_pair = next(pair for pair in campaign["pair_details"] if pair["pair_id"] == "p2")

    assert "duplicate_mode" in duplicate_pair["validation_warnings"]
    assert "pair_metadata_mismatch" in duplicate_pair["validation_warnings"]
    assert duplicate_pair["paired_category"] == "invalid_pair"
    assert "missing_or_unexpected_trials" in missing_pair["validation_warnings"]
    assert campaign["missing_field_counts"]["resolver"] == 1
    assert campaign["data_quality_warnings"]["missing_or_null_fields"] == 1


def test_connection_error_is_not_reported_as_a_confirmed_pair_failure():
    report = analyze_campaigns({
        "campaign.jsonl": [
            record("p1", "true", "connection_error"),
            record("p1", "false", "control_success"),
        ]
    })

    pair = report["campaigns"][0]["pair_details"][0]
    assert pair["paired_category"] == "at_least_one_outcome_unresolved"
    assert pair["ech_outcome"] == "connection_error"


def test_analysis_does_not_merge_same_pair_ids_from_different_campaigns():
    records = [record("p1", "true", "ech_success"), record("p1", "false", "control_success")]

    report = analyze_campaigns({"one.jsonl": records, "two.jsonl": records})

    assert [campaign["pair_count"] for campaign in report["campaigns"]] == [1, 1]


def test_analysis_cli_reads_jsonl_and_creates_a_new_report(tmp_path, monkeypatch):
    source = tmp_path / "campaign_20261010.jsonl"
    source.write_text("\n".join([
        json.dumps(record("p1", "true", "ech_success")),
        json.dumps(record("p1", "false", "control_success")),
    ]) + "\n")
    output = tmp_path / "audit.json"
    monkeypatch.setattr(sys, "argv", ["campaign-summary", str(source), "--output", str(output)])

    main()

    report = json.loads(output.read_text())
    assert report["total_records"] == 2
    assert report["campaigns"][0]["pair_count"] == 1


def test_analysis_cli_refuses_to_overwrite_existing_files(tmp_path, monkeypatch):
    source = tmp_path / "campaign.jsonl"
    source.write_text("{}\n")
    output = tmp_path / "audit.json"
    output.write_text("preserve me\n")
    monkeypatch.setattr(sys, "argv", ["campaign-summary", str(source), "--output", str(output)])

    with pytest.raises(SystemExit, match="Refusing to overwrite"):
        main()

    assert output.read_text() == "preserve me\n"
