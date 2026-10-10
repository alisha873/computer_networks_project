"""Summarize paired ECH campaign records without inferring censorship."""

import argparse
import json
from collections import Counter
from pathlib import Path


def read_records(path):
    records = []
    with Path(path).open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise ValueError(f"Expected object on line {line_number}")
            records.append(record)
    return records


def summarize(records):
    outcomes = Counter(
        str(record.get("outcome", "unknown"))
        for record in records
    )
    modes = Counter(
        str(record.get("requested_mode", "unknown"))
        for record in records
    )

    grouped = {}
    for record in records:
        pair_id = record.get("pair_id")
        if pair_id is None:
            continue
        grouped.setdefault(str(pair_id), []).append(record)

    complete_pairs = 0
    incomplete_pairs = 0
    duplicate_mode_pairs = 0
    both_success = 0
    ech_only_success = 0
    control_only_success = 0
    neither_success = 0
    pair_details = []

    for pair_id, pair in sorted(grouped.items()):
        ech = [r for r in pair if r.get("requested_mode") == "true"]
        control = [r for r in pair if r.get("requested_mode") == "false"]

        valid = len(ech) == 1 and len(control) == 1 and len(pair) == 2
        if not valid:
            incomplete_pairs += 1
            if len(ech) > 1 or len(control) > 1:
                duplicate_mode_pairs += 1
            pair_details.append({
                "pair_id": pair_id,
                "complete": False,
                "records": len(pair),
                "ech_trials": len(ech),
                "control_trials": len(control),
            })
            continue

        complete_pairs += 1
        ech_success = ech[0].get("outcome") == "ech_success"
        control_success = control[0].get("outcome") == "control_success"

        if ech_success and control_success:
            both_success += 1
        elif ech_success:
            ech_only_success += 1
        elif control_success:
            control_only_success += 1
        else:
            neither_success += 1

        pair_details.append({
            "pair_id": pair_id,
            "complete": True,
            "ech_outcome": ech[0].get("outcome", "unknown"),
            "control_outcome": control[0].get("outcome", "unknown"),
            "ech_http_status": ech[0].get("http_status"),
            "control_http_status": control[0].get("http_status"),
        })

    return {
        "total_records": len(records),
        "mode_counts": dict(sorted(modes.items())),
        "outcome_counts": dict(sorted(outcomes.items())),
        "unique_pairs": len(grouped),
        "complete_pairs": complete_pairs,
        "incomplete_or_malformed_pairs": incomplete_pairs,
        "pairs_with_duplicate_modes": duplicate_mode_pairs,
        "paired_outcomes": {
            "both_success": both_success,
            "ech_only_success": ech_only_success,
            "control_only_success": control_only_success,
            "neither_success": neither_success,
        },
        "pair_details": pair_details,
        "interpretation": (
            "Descriptive results only. A failed request is not by itself "
            "evidence of censorship. ECH-specific attribution requires "
            "validated evidence about the failure stage and plausible "
            "alternative explanations."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = summarize(read_records(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nSaved report to {args.output}")


if __name__ == "__main__":
    main()
