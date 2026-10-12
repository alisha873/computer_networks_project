from pathlib import Path
import re
import csv

LOG_DIR = Path(__file__).parent

CASES = {
    "baseline_ech.log": "valid_ech_baseline",
    "mismatched_ech.log": "alternate_outer_name",
    "invalid_ech.log": "malformed_config",
    "control.log": "ordinary_https_control",
    "dns_published_config.log": "dns_published_config",
    "fresh_retry_config.log": "fresh_retry_config",
    "cross_server_config.log": "cross_server_config",
    "cross_server_retry.log": "cross_server_retry",
}

def classify(path):
    text = path.read_text(errors="replace")

    ech_succeeded = bool(re.search(
        r"ECH: result [':]? ?(?:status is )?succeeded", text, re.I
    ))
    ech_rejected = bool(re.search(
        r"ECH: rejected|ECH required", text, re.I
    ))
    ech_not_attempted = bool(re.search(
        r"ECH: result: status is not attempted|SSL_ECH_STATUS: NOT_TRIED",
        text, re.I
    ))
    config_parse_error = "SSL_ECH_set1_ech_config_list failed" in text
    retry_received = "ECH: retry_configs" in text

    http_match = re.search(r"HTTP_STATUS:(\d{3})", text)
    http_status = int(http_match.group(1)) if http_match else None

    exit_match = re.search(r"curl: \((\d+)\)", text)
    if exit_match:
        curl_exit = int(exit_match.group(1))
    elif http_status == 200:
        curl_exit = 0
    else:
        curl_exit = None

    if config_parse_error:
        outcome = "client_config_parse_error"
    elif ech_rejected:
        outcome = "ech_rejected_server_retry"
    elif ech_succeeded and http_status == 200:
        outcome = "ech_success"
    elif ech_not_attempted and http_status == 200:
        outcome = "control_success_no_ech"
    else:
        outcome = "inconclusive"

    server_status = (
        "SUCCESS" if "SSL_ECH_STATUS: SUCCESS" in text
        else "NOT_TRIED" if "SSL_ECH_STATUS: NOT_TRIED" in text
        else "not_reported"
    )

    return {
        "file": path.name,
        "case": CASES[path.name],
        "classification": outcome,
        "curl_exit": curl_exit,
        "http_status": http_status,
        "ech_success_marker": ech_succeeded,
        "ech_rejection_marker": ech_rejected,
        "client_config_parse_error": config_parse_error,
        "retry_config_received": retry_received,
        "server_ech_status": server_status,
    }

rows = [classify(LOG_DIR / name) for name in CASES]

with (LOG_DIR / "classified_results.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

for row in rows:
    print(
        f"{row['case']:<25} {row['classification']:<28} "
        f"exit={str(row['curl_exit']):<4} HTTP={row['http_status']} "
        f"retry={row['retry_config_received']}"
    )

print(f"\nSaved: {LOG_DIR / 'classified_results.csv'}")
