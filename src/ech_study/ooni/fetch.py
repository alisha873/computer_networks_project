"""Fetch OONI web-connectivity observations with retry-safe persistence."""

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ech_study.ooni.ingest import summarize_raw_measurement

API_BASE = "https://api.ooni.io/api/v1/measurements"
RAW_BASE = "https://api.ooni.io/api/v1/raw_measurement"

API_OUTPUT = Path("data/raw/ooni_api_records.jsonl")
RAW_OUTPUT = Path("data/raw/ooni_measurements.jsonl")
SUMMARY_OUTPUT = Path("data/processed/ooni_summaries.jsonl")

NETWORK_ERRORS = (
    HTTPError,
    URLError,
    TimeoutError,
    json.JSONDecodeError,
)


def get_json(url, timeout=30):
    request = Request(
        url,
        headers={"User-Agent": "ech-india-study/0.1 (research)"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path):
    """Read valid JSONL records, ignoring blank or malformed lines."""
    if not path.exists():
        return []

    records = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def completed_uids(raw_path=None, summary_path=None):
    """Return UIDs with both a valid raw body and a normalized summary."""
    raw_path = raw_path or RAW_OUTPUT
    summary_path = summary_path or SUMMARY_OUTPUT

    raw_uids = {
        row.get("measurement_uid")
        for row in read_jsonl(raw_path)
        if row.get("measurement_uid")
        and isinstance(row.get("raw_measurement"), dict)
        and not row.get("fetch_error")
    }
    summary_uids = {
        row.get("measurement_uid")
        for row in read_jsonl(summary_path)
        if row.get("measurement_uid")
    }
    return raw_uids & summary_uids


def fetch_sample(
    since="2026-10-01",
    until="2026-10-10",
    limit=20,
    pause_seconds=0.25,
):
    """Fetch up to `limit` new complete India web-connectivity records.

    These observations are contextual network data, not ECH-specific tests.
    Incomplete raw downloads remain eligible for retry on subsequent runs.
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")

    for path in (API_OUTPUT, RAW_OUTPUT, SUMMARY_OUTPUT):
        path.parent.mkdir(parents=True, exist_ok=True)

    metadata_rows = read_jsonl(API_OUTPUT)
    metadata_uids = {
        row.get("measurement_uid")
        for row in metadata_rows
        if row.get("measurement_uid")
    }
    complete = completed_uids()

    params = urlencode({
        "probe_cc": "IN",
        "test_name": "web_connectivity",
        "since": since,
        "until": until,
        "limit": min(limit, 100),
        "order": "desc",
    })
    next_url = f"{API_BASE}?{params}"

    fetched = 0
    skipped = 0
    errors = 0
    retried = 0

    while next_url and fetched < limit:
        try:
            page = get_json(next_url)
        except NETWORK_ERRORS as exc:
            print(f"API page fetch failed: {exc}")
            errors += 1
            break

        results = page.get("results") or []
        if not results:
            break

        for metadata in results:
            if fetched >= limit:
                break

            uid = metadata.get("measurement_uid")
            if not uid:
                skipped += 1
                continue

            if uid in complete:
                skipped += 1
                continue

            if uid in metadata_uids:
                retried += 1
            else:
                append_jsonl(API_OUTPUT, metadata)
                metadata_uids.add(uid)

            try:
                raw_url = metadata.get("measurement_url")
                if not raw_url:
                    raw_url = (
                        f"{RAW_BASE}?"
                        f"{urlencode({'measurement_uid': uid})}"
                    )
                raw = get_json(raw_url)

                if not isinstance(raw, dict) or not isinstance(
                    raw.get("test_keys"), dict
                ):
                    raise ValueError(
                        f"Unexpected raw measurement structure for {uid}"
                    )

                summary = summarize_raw_measurement(
                    raw, metadata=metadata
                )
                summary["measurement_uid"] = uid

            except (*NETWORK_ERRORS, ValueError) as exc:
                append_jsonl(RAW_OUTPUT, {
                    "measurement_uid": uid,
                    "fetch_error": str(exc),
                })
                errors += 1
                print(f"Raw measurement fetch failed for {uid}: {exc}")
                continue

            # Persist the raw record and summary only after both are ready.
            append_jsonl(RAW_OUTPUT, {
                "measurement_uid": uid,
                "raw_measurement": raw,
            })
            append_jsonl(SUMMARY_OUTPUT, summary)

            complete.add(uid)
            fetched += 1
            print(f"Fetched {fetched}/{limit}: {uid}")
            time.sleep(pause_seconds)

        next_url = (page.get("metadata") or {}).get("next_url")

    print("\nFetch complete")
    print(f"New complete measurements: {fetched}")
    print(f"Already complete or missing UID: {skipped}")
    print(f"Previously recorded UIDs retried: {retried}")
    print(f"Fetch errors: {errors}")
    print(f"API metadata: {API_OUTPUT}")
    print(f"Raw measurements: {RAW_OUTPUT}")
    print(f"Normalized summaries: {SUMMARY_OUTPUT}")


if __name__ == "__main__":
    fetch_sample()
