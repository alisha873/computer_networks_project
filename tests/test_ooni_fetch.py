import json

from src.ech_study.ooni import fetch

def test_fetch_saves_raw_data_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "API_OUTPUT", tmp_path / "api.jsonl")
    monkeypatch.setattr(fetch, "RAW_OUTPUT", tmp_path / "raw.jsonl")
    monkeypatch.setattr(fetch, "SUMMARY_OUTPUT", tmp_path / "summary.jsonl")
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    uid = "test_measurement_001"
    raw_url = "https://api.ooni.io/api/v1/raw_measurement?test=1"

    metadata = {
        "measurement_uid": uid,
        "measurement_url": raw_url,
        "probe_cc": "IN",
        "test_name": "web_connectivity",
        "anomaly": True,
        "confirmed": False,
        "failure": False,
    }

    raw = {
        "probe_cc": "IN",
        "test_name": "web_connectivity",
        "measurement_start_time": "2026-10-10 00:00:00",
        "test_keys": {
            "accessible": False,
            "blocking": "dns",
            "dns_consistency": "inconsistent",
        },
    }

    def fake_get_json(url, timeout=30):
        if url == raw_url:
            return raw
        return {
            "results": [metadata],
            "metadata": {"next_url": None},
        }

    monkeypatch.setattr(fetch, "get_json", fake_get_json)

    fetch.fetch_sample(limit=1, pause_seconds=0)

    api_rows = [
        json.loads(line)
        for line in (tmp_path / "api.jsonl").read_text().splitlines()
    ]
    raw_rows = [
        json.loads(line)
        for line in (tmp_path / "raw.jsonl").read_text().splitlines()
    ]
    summaries = [
        json.loads(line)
        for line in (tmp_path / "summary.jsonl").read_text().splitlines()
    ]

    assert len(api_rows) == len(raw_rows) == len(summaries) == 1
    assert raw_rows[0]["raw_measurement"] == raw
    assert summaries[0]["measurement_uid"] == uid
    assert summaries[0]["anomaly"] is True
    assert summaries[0]["confirmed"] is False
    assert summaries[0]["blocking"] == "dns"
    assert summaries[0]["accessible"] is False


def test_fetch_skips_existing_measurement(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "API_OUTPUT", tmp_path / "api.jsonl")
    monkeypatch.setattr(fetch, "RAW_OUTPUT", tmp_path / "raw.jsonl")
    monkeypatch.setattr(fetch, "SUMMARY_OUTPUT", tmp_path / "summary.jsonl")
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    uid = "already_downloaded"
    metadata = {
        "measurement_uid": uid,
        "measurement_url": "https://example.invalid/raw",
    }
    raw_record = {
        "measurement_uid": uid,
        "raw_measurement": {"test_keys": {}},
    }
    summary = {"measurement_uid": uid, "is_ech_measurement": False}

    (tmp_path / "api.jsonl").write_text(json.dumps(metadata) + "\n")
    (tmp_path / "raw.jsonl").write_text(json.dumps(raw_record) + "\n")
    (tmp_path / "summary.jsonl").write_text(json.dumps(summary) + "\n")

    def fake_get_json(url, timeout=30):
        if url.startswith(fetch.API_BASE + "?"):
            return {
                "results": [metadata],
                "metadata": {"next_url": None},
            }
        raise AssertionError(f"Unexpected raw fetch: {url}")

    monkeypatch.setattr(fetch, "get_json", fake_get_json)

    fetch.fetch_sample(limit=1, pause_seconds=0)

    assert len((tmp_path / "api.jsonl").read_text().splitlines()) == 1
    assert len((tmp_path / "raw.jsonl").read_text().splitlines()) == 1
    assert len((tmp_path / "summary.jsonl").read_text().splitlines()) == 1


def test_fetch_follows_multiple_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "API_OUTPUT", tmp_path / "api.jsonl")
    monkeypatch.setattr(fetch, "RAW_OUTPUT", tmp_path / "raw.jsonl")
    monkeypatch.setattr(fetch, "SUMMARY_OUTPUT", tmp_path / "summary.jsonl")
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    page2_url = "https://api.ooni.io/page2"

    def metadata(uid):
        return {
            "measurement_uid": uid,
            "measurement_url": f"https://example.test/{uid}",
            "probe_cc": "IN",
            "test_name": "web_connectivity",
        }

    first = metadata("page1_uid")
    second = metadata("page2_uid")
    requested_urls = []

    def fake_get_json(url, timeout=30):
        requested_urls.append(url)

        if url.startswith(fetch.API_BASE + "?"):
            return {
                "results": [first],
                "metadata": {"next_url": page2_url},
            }

        if url == page2_url:
            return {
                "results": [second],
                "metadata": {"next_url": None},
            }

        if url in (first["measurement_url"], second["measurement_url"]):
            return {
                "test_keys": {"accessible": True},
                "probe_cc": "IN",
                "test_name": "web_connectivity",
            }

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(fetch, "get_json", fake_get_json)

    fetch.fetch_sample(limit=2, pause_seconds=0)

    summaries = [
        json.loads(line)
        for line in (tmp_path / "summary.jsonl").read_text().splitlines()
    ]

    assert {row["measurement_uid"] for row in summaries} == {
        "page1_uid",
        "page2_uid",
    }
    assert page2_url in requested_urls
    assert len(summaries) == 2


def test_failed_raw_download_can_be_retried(tmp_path, monkeypatch):
    from urllib.error import URLError

    monkeypatch.setattr(fetch, "API_OUTPUT", tmp_path / "api.jsonl")
    monkeypatch.setattr(fetch, "RAW_OUTPUT", tmp_path / "raw.jsonl")
    monkeypatch.setattr(fetch, "SUMMARY_OUTPUT", tmp_path / "summary.jsonl")
    monkeypatch.setattr(fetch.time, "sleep", lambda _: None)

    uid = "retry_measurement"
    raw_url = "https://example.test/retry-raw"
    metadata = {
        "measurement_uid": uid,
        "measurement_url": raw_url,
        "probe_cc": "IN",
        "test_name": "web_connectivity",
    }
    raw = {
        "probe_cc": "IN",
        "test_name": "web_connectivity",
        "test_keys": {"accessible": True},
    }
    raw_attempts = 0

    def fake_get_json(url, timeout=30):
        nonlocal raw_attempts

        if url.startswith(fetch.API_BASE + "?"):
            return {
                "results": [metadata],
                "metadata": {"next_url": None},
            }

        if url == raw_url:
            raw_attempts += 1
            if raw_attempts == 1:
                raise URLError("temporary network failure")
            return raw

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(fetch, "get_json", fake_get_json)

    # First run: the raw download fails.
    fetch.fetch_sample(limit=1, pause_seconds=0)
    assert not (tmp_path / "summary.jsonl").exists() or (
        (tmp_path / "summary.jsonl").read_text().strip() == ""
    )

    # Second run: the same UID must be retried successfully.
    fetch.fetch_sample(limit=1, pause_seconds=0)

    summaries = [
        json.loads(line)
        for line in (tmp_path / "summary.jsonl").read_text().splitlines()
    ]
    assert raw_attempts == 2
    assert len(summaries) == 1
    assert summaries[0]["measurement_uid"] == uid
    assert fetch.completed_uids() == {uid}
