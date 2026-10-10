import json

import pytest

from ech_study.schema import Trial, append_jsonl, new_trial, read_jsonl


def test_new_trial_has_unknowns_as_none():
    trial = new_trial(
        network="test-network",
        resolver="system",
        domain="example.com",
        requested_mode="real",
    )

    assert trial.https_record_present is None
    assert trial.tcp_result is None
    assert trial.ech_accepted is None
    assert trial.classification == "inconclusive"


def test_valid_trial_serializes():
    trial = new_trial("test-network", "system", "example.com")
    record = json.loads(trial.to_json())

    assert record["domain"] == "example.com"
    assert record["ech_accepted"] is None


def test_invalid_classification_is_rejected():
    trial = new_trial("test-network", "system", "example.com")
    trial.classification = "censorship_proven"

    with pytest.raises(ValueError):
        trial.validate()


def test_jsonl_round_trip(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = new_trial("test-network", "system", "example.com")

    append_jsonl(str(path), trial)
    records = read_jsonl(str(path))

    assert len(records) == 1
    assert records[0]["domain"] == "example.com"
