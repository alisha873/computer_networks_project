"""Summarize paired ECH campaign records without inferring censorship."""

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

UNRESOLVED_OUTCOMES = {
    "", "unknown", "inconclusive", "probe_error", "connection_error",
}
KNOWN_OUTCOMES = {"ech_success", "control_success", "http_error"}


def _outcome(record):
    value = record.get("outcome")
    return str(value).strip().lower() if value is not None else ""


def _destination_key(record):
    destination_id = record.get("destination_id") or "unknown"
    endpoint = record.get("endpoint") or "unknown"
    return str(destination_id), str(endpoint)


def _pair_summary(pair):
    ech = [r for r in pair if r.get("requested_mode") == "true"]
    control = [r for r in pair if r.get("requested_mode") == "false"]
    destination_keys = {_destination_key(record) for record in pair}

    errors = []
    if len(pair) != 2 or len(ech) != 1 or len(control) != 1:
        errors.append("missing_or_unexpected_trials")
    if len(ech) > 1 or len(control) > 1:
        errors.append("duplicate_modes")
    if any(
        not record.get("destination_id") or not record.get("endpoint")
        for record in pair
    ):
        errors.append("missing_destination_or_endpoint")
    if len(destination_keys) > 1:
        errors.append("mismatched_destinations_or_endpoints")

    complete = not errors
    detail = {
        "complete": complete,
        "records": len(pair),
        "ech_trials": len(ech),
        "control_trials": len(control),
        "destination_ids": sorted({key[0] for key in destination_keys}),
        "endpoints": sorted({key[1] for key in destination_keys}),
        "validation_errors": errors,
    }
    paired_outcome = None
    if complete:
        ech_outcome = _outcome(ech[0])
        control_outcome = _outcome(control[0])
        detail.update({
            "ech_outcome": ech_outcome or "missing",
            "control_outcome": control_outcome or "missing",
            "ech_http_status": ech[0].get("http_status"),
            "control_http_status": control[0].get("http_status"),
        })
        ech_success = ech_outcome == "ech_success"
        control_success = control_outcome == "control_success"
        if (
            ech_outcome in UNRESOLVED_OUTCOMES
            or control_outcome in UNRESOLVED_OUTCOMES
            or ech_outcome not in KNOWN_OUTCOMES
            or control_outcome not in KNOWN_OUTCOMES
            or (not ech_success and ech_outcome != "http_error")
            or (not control_success and control_outcome != "http_error")
        ):
            paired_outcome = "at_least_one_outcome_unresolved"
        elif ech_success and control_success:
            paired_outcome = "both_success"
        elif ech_success:
            paired_outcome = "ech_only_success"
        elif control_success:
            paired_outcome = "control_only_success"
        else:
            paired_outcome = "neither_success_both_outcomes_known"
    return detail, paired_outcome, destination_keys


def _record_counts(records):
    modes = Counter(str(record.get("requested_mode", "unknown")) for record in records)
    outcomes = Counter(_outcome(record) or "missing" for record in records)
    by_mode = {
        mode: dict(sorted(Counter(
            _outcome(record) or "missing"
            for record in records
            if record.get("requested_mode") == mode
        ).items()))
        for mode in ("true", "false")
    }
    return modes, outcomes, by_mode


def _pair_counts(pair_rows):
    counts = Counter()
    for row in pair_rows:
        detail = row["detail"]
        counts["complete_pairs" if detail["complete"] else "incomplete_or_malformed_pairs"] += 1
        if "missing_or_unexpected_trials" in detail["validation_errors"]:
            counts["pairs_missing_or_unexpected_trials"] += 1
        if "duplicate_modes" in detail["validation_errors"]:
            counts["pairs_with_duplicate_modes"] += 1
        if "missing_destination_or_endpoint" in detail["validation_errors"]:
            counts["pairs_missing_destination_or_endpoint"] += 1
        if "mismatched_destinations_or_endpoints" in detail["validation_errors"]:
            counts["pairs_with_mismatched_destinations_or_endpoints"] += 1
        if row["paired_outcome"]:
            counts[row["paired_outcome"]] += 1
    return counts


def _destination_summary(destination_id, endpoint, records, pair_rows):
    modes, outcomes, by_mode = _record_counts(records)
    pair_counts = _pair_counts(pair_rows)
    return {
        "destination_id": destination_id,
        "endpoint": endpoint,
        "attempted_records": len(records),
        "mode_counts": dict(sorted(modes.items())),
        "outcome_counts": dict(sorted(outcomes.items())),
        "ech_outcome_counts": by_mode["true"],
        "control_outcome_counts": by_mode["false"],
        "unique_pairs": len(pair_rows),
        "complete_pairs": pair_counts["complete_pairs"],
        "incomplete_or_malformed_pairs": pair_counts["incomplete_or_malformed_pairs"],
        "pairs_missing_or_unexpected_trials": pair_counts["pairs_missing_or_unexpected_trials"],
        "pairs_with_duplicate_modes": pair_counts["pairs_with_duplicate_modes"],
        "pairs_missing_destination_or_endpoint": pair_counts[
            "pairs_missing_destination_or_endpoint"
        ],
        "pairs_with_mismatched_destinations_or_endpoints": pair_counts[
            "pairs_with_mismatched_destinations_or_endpoints"
        ],
        "paired_outcomes": {
            name: pair_counts[name]
            for name in (
                "both_success",
                "ech_only_success",
                "control_only_success",
                "neither_success_both_outcomes_known",
                "at_least_one_outcome_unresolved",
            )
        },
    }


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


def _counts(records, field, missing="<missing>"):
    return dict(sorted(Counter(
        str(record.get(field)) if record.get(field) is not None else missing
        for record in records
    ).items()))


def _dimension_summary(records, field):
    groups = {}
    for record in records:
        value = record.get(field)
        key = str(value) if value is not None else "<missing>"
        groups.setdefault(key, []).append(record)
    return [
        {
            "value": value,
            "attempted_records": len(group),
            "outcome_counts": _counts(group, "outcome"),
            "mode_counts": _counts(group, "requested_mode"),
        }
        for value, group in sorted(groups.items())
    ]


def _campaign_pair_details(records):
    pairs = {}
    for record in records:
        pair_id = record.get("pair_id")
        if pair_id is None or str(pair_id).strip() == "":
            continue
        pairs.setdefault(str(pair_id), []).append(record)

    details = []
    warning_counts = Counter()
    for pair_id, pair in sorted(pairs.items()):
        ech = [record for record in pair if record.get("requested_mode") == "true"]
        control = [record for record in pair if record.get("requested_mode") == "false"]
        errors = []
        if len(pair) != 2 or len(ech) != 1 or len(control) != 1:
            errors.append("missing_or_unexpected_trials")
        if len(ech) > 1 or len(control) > 1:
            errors.append("duplicate_mode")
        positions = [record.get("pair_position") for record in pair]
        if any(type(position) is not int or position not in (1, 2) for position in positions):
            errors.append("missing_or_invalid_pair_position")
        if len({json.dumps(position, sort_keys=True) for position in positions}) != len(positions):
            errors.append("duplicate_pair_position")
        metadata_fields = ("destination_id", "endpoint", "resolver", "network")
        metadata_by_key = {}
        for record in pair:
            metadata = tuple(record.get(field) for field in metadata_fields)
            metadata_key = tuple(
                json.dumps(value, sort_keys=True, ensure_ascii=False)
                for value in metadata
            )
            metadata_by_key[metadata_key] = metadata
        metadata_keys = set(metadata_by_key)
        if len(metadata_keys) > 1:
            errors.append("pair_metadata_mismatch")
        if any(not record.get(key) for record in pair for key in (
            "destination_id", "endpoint", "resolver", "requested_mode"
        )):
            errors.append("missing_pair_metadata")
        for error in errors:
            warning_counts[error] += 1

        detail = {
            "pair_id": pair_id,
            "record_count": len(pair),
            "modes": _counts(pair, "requested_mode"),
            "outcome_counts": _counts(pair, "outcome"),
            "metadata": [dict(zip(metadata_fields, metadata_by_key[key]))
                         for key in sorted(metadata_keys)],
            "validation_warnings": errors,
        }
        if errors:
            detail["paired_category"] = "invalid_pair"
        if len(ech) == 1 and len(control) == 1:
            ech_value = ech[0].get("outcome")
            control_value = control[0].get("outcome")
            ech_outcome = str(ech_value) if ech_value not in (None, "") else "<missing>"
            control_outcome = str(control_value) if control_value not in (None, "") else "<missing>"
            detail["ech_outcome"] = ech_outcome
            detail["control_outcome"] = control_outcome
            if errors:
                pair_category = "invalid_pair"
            elif ech_outcome == "ech_success" and control_outcome == "control_success":
                pair_category = "both_success"
            elif ech_outcome == "ech_success" and control_outcome == "http_error":
                pair_category = "ech_success_control_http_error"
            elif control_outcome == "control_success" and ech_outcome == "http_error":
                pair_category = "control_success_ech_http_error"
            elif ech_outcome == "http_error" and control_outcome == "http_error":
                pair_category = "neither_success_both_http_errors"
            else:
                pair_category = "at_least_one_outcome_unresolved"
            detail["paired_category"] = pair_category
        details.append(detail)
    return details, warning_counts, len(pairs)


def _campaign_analysis(name, records):
    required_fields = (
        "campaign_id", "timestamp_utc", "network", "destination_id",
        "endpoint", "resolver", "pair_id", "pair_position",
        "requested_mode", "outcome", "ech_status", "return_code",
        "http_status", "ech_rejection_observed", "ech_retry_config_received",
    )
    warning_counts = Counter()
    missing_field_counts = Counter()
    for record in records:
        for field in required_fields:
            if field not in record or record[field] is None or record[field] == "":
                missing_field_counts[field] += 1
    if missing_field_counts:
        warning_counts["missing_or_null_fields"] = sum(missing_field_counts.values())

    timestamps = []
    dates = Counter()
    invalid_timestamps = 0
    for record in records:
        raw_timestamp = record.get("timestamp_utc")
        try:
            parsed = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("timestamp has no timezone")
            parsed_utc = parsed.astimezone(timezone.utc)
            timestamps.append(parsed_utc)
            dates[parsed_utc.date().isoformat()] += 1
        except (TypeError, ValueError):
            invalid_timestamps += 1
    if invalid_timestamps:
        warning_counts["invalid_or_timezone_naive_timestamps"] = invalid_timestamps

    filename_date_match = re.search(r"(20\d{6})", name)
    filename_date = None
    if filename_date_match:
        try:
            filename_date = datetime.strptime(
                filename_date_match.group(1), "%Y%m%d"
            ).date().isoformat()
        except ValueError:
            pass
    timestamp_dates = sorted(dates)
    if filename_date and timestamp_dates and filename_date not in timestamp_dates:
        warning_counts["filename_date_differs_from_record_timestamps"] += 1

    network_counts = _counts(records, "network")
    if "current_connection" in network_counts:
        warning_counts["network_label_does_not_identify_access_type"] += network_counts[
            "current_connection"
        ]

    pair_details, pair_warnings, unique_pairs = _campaign_pair_details(records)
    warning_counts.update(pair_warnings)
    pair_ids_missing = sum(
        1 for record in records
        if record.get("pair_id") is None or str(record.get("pair_id")).strip() == ""
    )
    if pair_ids_missing:
        warning_counts["records_missing_pair_id"] += pair_ids_missing

    pair_mode_duplicates = Counter()
    for pair in pair_details:
        for mode, count in pair["modes"].items():
            if mode in {"true", "false"} and count > 1:
                pair_mode_duplicates[mode] += 1
    duplicate_trial_keys = Counter(
        (str(record.get("pair_id")), str(record.get("requested_mode")))
        for record in records
        if record.get("pair_id") is not None
    )
    exact_duplicate_trials = sum(
        count - 1 for count in duplicate_trial_keys.values() if count > 1
    )
    if exact_duplicate_trials:
        warning_counts["duplicate_pair_mode_records"] += exact_duplicate_trials
    unexpected_modes = sum(
        1 for record in records
        if record.get("requested_mode") not in ("true", "false")
    )
    if unexpected_modes:
        warning_counts["unexpected_requested_modes"] += unexpected_modes

    return {
        "campaign_file": name,
        "record_count": len(records),
        "campaign_ids": _counts(records, "campaign_id"),
        "field_counts": {
            field: _counts(records, field)
            for field in (
                "network", "endpoint", "resolver", "destination_id",
                "requested_mode", "outcome", "ech_status", "return_code",
                "pair_position", "http_status", "ech_rejection_observed",
                "ech_retry_config_received",
            )
        },
        "timestamp_utc": {
            "valid_count": len(timestamps),
            "invalid_count": invalid_timestamps,
            "minimum": min((value.isoformat() for value in timestamps), default=None),
            "maximum": max((value.isoformat() for value in timestamps), default=None),
            "date_counts": dict(sorted(dates.items())),
            "filename_date": filename_date,
        },
        "breakdowns": {
            "endpoint": _dimension_summary(records, "endpoint"),
            "resolver": _dimension_summary(records, "resolver"),
            "requested_mode": _dimension_summary(records, "requested_mode"),
        },
        "pair_count": unique_pairs,
        "pair_details": pair_details,
        "missing_field_counts": dict(sorted(missing_field_counts.items())),
        "duplicate_pair_mode_records": exact_duplicate_trials,
        "duplicate_mode_pairs": dict(sorted(pair_mode_duplicates.items())),
        "data_quality_warnings": dict(sorted(warning_counts.items())),
    }


def analyze_campaigns(campaigns):
    """Analyze named campaign record lists without changing source records."""
    campaign_records = {
        name: list(records) for name, records in campaigns.items()
    }
    reports = [
        _campaign_analysis(name, records)
        for name, records in sorted(campaign_records.items())
    ]
    all_records = [record for report_name in sorted(campaign_records)
                   for record in campaign_records[report_name]]
    return {
        "campaign_count": len(reports),
        "total_records": len(all_records),
        "campaigns": reports,
        "interpretation": (
            "Descriptive analysis only. Outcomes and curl log markers are kept "
            "distinct; HTTP success alone is not evidence of ECH acceptance. "
            "Connection errors, missing data, and unknown outcomes are not "
            "treated as confirmed protocol failures or evidence of censorship."
        ),
    }


def analyze_campaign_files(paths):
    """Read and analyze multiple campaign JSONL files, keyed by basename."""
    campaigns = {}
    for path in paths:
        path = Path(path)
        if path.name in campaigns:
            raise ValueError(f"Duplicate campaign filename: {path.name}")
        campaigns[path.name] = read_records(path)
    return analyze_campaigns(campaigns)


def summarize(records):
    records = list(records)
    modes, outcomes, by_mode = _record_counts(records)
    grouped = {}
    records_without_pair_id = 0
    for record in records:
        pair_id = record.get("pair_id")
        if pair_id is None or str(pair_id).strip() == "":
            records_without_pair_id += 1
            continue
        group_key = (str(record.get("campaign_id", "")), str(pair_id))
        grouped.setdefault(group_key, []).append(record)

    pair_details = []
    pair_rows = []
    destination_records = {}
    destination_pairs = {}

    for (campaign_id, pair_id), pair in sorted(grouped.items()):
        detail, paired_outcome, destination_keys = _pair_summary(pair)
        detail.update({"pair_id": pair_id, "campaign_id": campaign_id or None})
        pair_details.append(detail)
        row = {
            "detail": detail,
            "paired_outcome": paired_outcome,
            "destination_keys": destination_keys,
        }
        pair_rows.append(row)
        for destination_key in destination_keys:
            destination_pairs.setdefault(destination_key, []).append(row)

    for record in records:
        destination_records.setdefault(_destination_key(record), []).append(record)

    pair_counts = _pair_counts(pair_rows)
    destination_summaries = [
        _destination_summary(
            destination_id,
            endpoint,
            destination_records.get((destination_id, endpoint), []),
            destination_pairs.get((destination_id, endpoint), []),
        )
        for destination_id, endpoint in sorted(destination_records)
    ]
    paired_outcome_names = (
        "both_success",
        "ech_only_success",
        "control_only_success",
        "neither_success_both_outcomes_known",
        "at_least_one_outcome_unresolved",
    )

    return {
        "total_records": len(records),
        "attempted_records": len(records),
        "mode_counts": dict(sorted(modes.items())),
        "outcome_counts": dict(sorted(outcomes.items())),
        "ech_outcome_counts": by_mode["true"],
        "control_outcome_counts": by_mode["false"],
        "records_without_pair_id": records_without_pair_id,
        "unique_pairs": len(grouped),
        "complete_pairs": pair_counts["complete_pairs"],
        "incomplete_or_malformed_pairs": pair_counts["incomplete_or_malformed_pairs"],
        "pairs_missing_or_unexpected_trials": pair_counts[
            "pairs_missing_or_unexpected_trials"
        ],
        "pairs_with_duplicate_modes": pair_counts["pairs_with_duplicate_modes"],
        "pairs_missing_destination_or_endpoint": pair_counts[
            "pairs_missing_destination_or_endpoint"
        ],
        "pairs_with_mismatched_destinations_or_endpoints": pair_counts[
            "pairs_with_mismatched_destinations_or_endpoints"
        ],
        "paired_outcomes": {
            name: pair_counts[name] for name in paired_outcome_names
        },
        "pair_details": pair_details,
        "per_destination": destination_summaries,
        "interpretation": (
            "Descriptive results only. A failed request is not by itself "
            "evidence of censorship. ECH-specific attribution requires "
            "validated evidence about the failure stage and plausible "
            "alternative explanations."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Audit campaign JSONL records without changing source files."
    )
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument(
        "--output", type=Path,
        help="Optional new JSON report path; existing files are never overwritten.",
    )
    args = parser.parse_args()

    report = analyze_campaign_files(args.inputs)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        output = args.output
        if output.resolve() in {path.resolve() for path in args.inputs}:
            raise SystemExit("Output path must not overwrite an input campaign file")
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output.open("x", encoding="utf-8") as file:
                file.write(rendered)
        except FileExistsError as exc:
            raise SystemExit(f"Refusing to overwrite existing output: {output}") from exc
        print(f"Saved report to {output}")
    print(rendered, end="")


if __name__ == "__main__":
    main()
