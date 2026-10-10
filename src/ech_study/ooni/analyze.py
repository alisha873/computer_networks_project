"""Summarize OONI web-connectivity observations without inferring censorship."""

import json
from collections import Counter
from pathlib import Path

INPUT = Path("data/processed/ooni_summaries.jsonl")
OUTPUT = Path("results/ooni_summary_report.json")


def read_jsonl(path):
    records = []
    if not path.exists():
        raise FileNotFoundError(
            f"Input not found: {path}. Run the OONI fetcher first."
        )

    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {path}"
                ) from exc

            if not isinstance(record, dict):
                raise ValueError(
                    f"Expected a JSON object on line {line_number}"
                )
            records.append(record)

    return records


def count_values(records, field):
    """Count true, false, and missing/other values explicitly."""
    counts = Counter()
    for record in records:
        value = record.get(field)
        if value is True:
            counts["true"] += 1
        elif value is False:
            counts["false"] += 1
        else:
            counts["unknown_or_missing"] += 1
    return dict(counts)


def analyze(records):
    blocking = Counter(
        str(record.get("blocking") or "unknown")
        for record in records
    )

    ech_records = [
        record for record in records
        if record.get("is_ech_measurement") is True
    ]

    return {
        "source": "OONI web_connectivity",
        "total_measurements": len(records),
        "unique_measurement_uids": len({
            record["measurement_uid"]
            for record in records
            if record.get("measurement_uid")
        }),
        "accessible": count_values(records, "accessible"),
        "anomaly": count_values(records, "anomaly"),
        "confirmed": count_values(records, "confirmed"),
        "failure": count_values(records, "failure"),
        "blocking_reasons": dict(sorted(blocking.items())),
        "ech_measurements": len(ech_records),
        "interpretation": (
            "OONI web-connectivity observations provide contextual "
            "connectivity evidence, not direct evidence of ECH censorship. "
            "An anomaly or accessibility failure alone does not establish "
            "censorship. ECH-specific attribution requires separate "
            "controlled measurements."
        ),
    }


def main():
    records = read_jsonl(INPUT)
    report = analyze(records)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport saved to: {OUTPUT}")


if __name__ == "__main__":
    main()
