import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

CURL = Path.home() / "ech-build/curl/src/curl"
ENDPOINT = "https://crypto.cloudflare.com/cdn-cgi/trace"
DOH_URL = "https://one.one.one.one/dns-query"
OUTPUT = Path("results/ech_curl_trials.jsonl")


def run_trial(mode, endpoint=ENDPOINT, doh_url=DOH_URL):
    timestamp = datetime.now(timezone.utc).isoformat()

    command = [
        str(CURL),
        "-4",
        "-sS",
        "-v",
        "--max-time", "20",
        "--ech", mode,
        "--doh-url", doh_url,
        "-w", "\nHTTP_STATUS:%{http_code}\n",
        endpoint,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=25,
    )

    log = result.stderr
    body = result.stdout

    if "ECH: result 'succeeded'" in log:
        ech_status = "succeeded"
    elif "status is not attempted" in log:
        ech_status = "not_attempted"
    elif re.search(r"ECH:.*fail", log, re.IGNORECASE):
        ech_status = "failed"
    else:
        ech_status = "unknown"

    trace = {}
    for line in body.splitlines():
        if "=" in line and not line.startswith("HTTP_STATUS:"):
            key, value = line.split("=", 1)
            trace[key] = value

    http_match = re.search(r"HTTP_STATUS:(\d{3})", body)
    http_status = int(http_match.group(1)) if http_match else None

    if result.returncode != 0:
        outcome = "connection_error"
    elif http_status != 200:
        outcome = "http_error"
    elif mode == "true" and ech_status == "succeeded":
        outcome = "ech_success"
    elif mode == "false" and ech_status == "not_attempted":
        outcome = "control_success"
    else:
        outcome = "inconclusive"

    return {
        "timestamp_utc": timestamp,
        "network": "current_connection",
        "domain": endpoint.split("://", 1)[-1].split("/", 1)[0],
        "endpoint": endpoint,
        "resolver": doh_url,
        "requested_mode": mode,
        "return_code": result.returncode,
        "http_status": http_status,
        "ech_status": ech_status,
        "ech_rejection_observed": bool(
            re.search(r"ECH: rejected", log, re.IGNORECASE)
        ),
        "ech_retry_config_received": "retry_configs" in log,
        "outcome": outcome,
        "trace_sni": trace.get("sni"),
        "trace_location": trace.get("loc"),
        "trace_colo": trace.get("colo"),
        "error_excerpt": log[-1200:] if result.returncode != 0 else None,
    }


def main():
    if not CURL.is_file():
        raise SystemExit(f"Custom curl not found: {CURL}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Keep the pair together: ECH enabled, then disabled.
    for mode in ("true", "false"):
        try:
            record = run_trial(mode)
        except (subprocess.TimeoutExpired, OSError) as exc:
            record = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "domain": "crypto.cloudflare.com",
                "requested_mode": mode,
                "outcome": "probe_error",
                "error_excerpt": str(exc),
            }

        with OUTPUT.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record) + "\n")

        print(
            f"mode={mode:5} "
            f"outcome={record['outcome']:18} "
            f"ECH={record.get('ech_status', 'unknown')} "
            f"SNI={record.get('trace_sni', 'unknown')}"
        )

    print(f"\nResults appended to {OUTPUT}")


if __name__ == "__main__":
    main()
