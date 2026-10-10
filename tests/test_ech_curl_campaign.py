import json

import pytest

from ech_study.probe import ech_curl_campaign as campaign


def test_campaign_records_complete_randomized_pairs(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign.time, "sleep", lambda _: None)
    calls = []

    def fake_run_trial(mode, endpoint=campaign.ENDPOINT,
                       doh_url=campaign.DOH_URL):
        calls.append((mode, endpoint, doh_url))
        return {
            "requested_mode": mode,
            "outcome": "ech_success" if mode == "true" else "control_success",
            "timestamp_utc": "2026-10-11T10:00:00+00:00",
        }

    monkeypatch.setattr(campaign, "run_trial", fake_run_trial)

    output = tmp_path / "campaign.jsonl"
    campaign.run_campaign(
        pairs=3,
        output=output,
        pause_seconds=0,
        seed=7,
    )

    records = [json.loads(line) for line in output.read_text().splitlines()]

    assert len(records) == 6

    for pair_number in range(1, 4):
        pair_id = f"pair-{pair_number:04d}"
        pair = [r for r in records if r["pair_id"] == pair_id]
        assert len(pair) == 2
        assert {r["requested_mode"] for r in pair} == {"true", "false"}
        assert {r["pair_position"] for r in pair} == {1, 2}
        assert all(r["network"] == "current_connection" for r in pair)
        assert all(r["endpoint"] == campaign.ENDPOINT for r in pair)

    assert len(calls) == 6


def test_campaign_runs_complete_pairs_for_each_destination(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(campaign.time, "sleep", lambda _: None)
    calls = []

    def fake_run_trial(mode, endpoint=campaign.ENDPOINT,
                       doh_url=campaign.DOH_URL):
        calls.append((mode, endpoint, doh_url))
        return {
            "requested_mode": mode,
            "outcome": "ech_success" if mode == "true" else "control_success",
        }

    monkeypatch.setattr(campaign, "run_trial", fake_run_trial)

    destinations = [
        "https://one.example/test",
        "https://two.example/test",
    ]
    output = tmp_path / "multi.jsonl"

    campaign.run_campaign(
        pairs=2,
        output=output,
        pause_seconds=0,
        seed=11,
        destinations=destinations,
    )

    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(records) == 8

    for endpoint in destinations:
        endpoint_records = [r for r in records if r["endpoint"] == endpoint]
        assert len(endpoint_records) == 4

        for pair_id in {r["pair_id"] for r in endpoint_records}:
            pair = [r for r in endpoint_records if r["pair_id"] == pair_id]
            assert len(pair) == 2
            assert {r["requested_mode"] for r in pair} == {"true", "false"}

    assert len(calls) == 8


def test_campaign_refuses_to_overwrite_existing_file(tmp_path):
    output = tmp_path / "existing.jsonl"
    output.write_text('{"preserve": true}\n')

    with pytest.raises(FileExistsError):
        campaign.run_campaign(
            pairs=1,
            output=output,
            pause_seconds=0,
            seed=1,
        )

    assert output.read_text() == '{"preserve": true}\n'


def test_campaign_rejects_invalid_arguments(tmp_path):
    with pytest.raises(ValueError):
        campaign.run_campaign(pairs=0, output=tmp_path / "zero.jsonl")

    with pytest.raises(ValueError):
        campaign.run_campaign(
            pairs=1,
            output=tmp_path / "negative-pause.jsonl",
            pause_seconds=-1,
        )

    with pytest.raises(ValueError):
        campaign.run_campaign(
            pairs=1,
            output=tmp_path / "no-destinations.jsonl",
            destinations=[],
        )

    with pytest.raises(ValueError):
        campaign.run_campaign(
            pairs=1,
            output=tmp_path / "bad-destination.jsonl",
            destinations=["http://example.com"],
        )
