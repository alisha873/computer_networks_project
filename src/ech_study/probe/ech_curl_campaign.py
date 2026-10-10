"""Run randomized paired ECH/control trials across configured endpoints."""

import argparse
import json
import random
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from ech_study.probe.ech_curl_probe import (
    DOH_URL,
    ENDPOINT,
    run_trial,
)

DEFAULT_OUTPUT = Path("results/ech_curl_campaign.jsonl")


def validate_destinations(destinations):
    if not destinations:
        raise ValueError("At least one destination is required")

    for endpoint in destinations:
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(
                f"Destination must be an HTTPS URL: {endpoint!r}"
            )


def run_campaign(
    pairs=10,
    output=DEFAULT_OUTPUT,
    network="current_connection",
    pause_seconds=0.5,
    seed=None,
    destinations=None,
    doh_url=DOH_URL,
):
    """Run randomized ECH/control pairs for every destination.

    `pairs` is the number of pairs per destination. Existing output files
    are never overwritten. Each record retains its destination and pair ID.
    """
    if pairs < 1:
        raise ValueError("pairs must be at least 1")
    if pause_seconds < 0:
        raise ValueError("pause_seconds cannot be negative")

    if destinations is None:
        destinations = [ENDPOINT]
    else:
        destinations = list(destinations)

    validate_destinations(destinations)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    campaign_id = datetime.now(timezone.utc).isoformat()
    total_pairs = pairs * len(destinations)

    with output.open("x", encoding="utf-8") as file:
        for destination_number, endpoint in enumerate(destinations, start=1):
            for pair_number in range(1, pairs + 1):
                modes = ["true", "false"]
                rng.shuffle(modes)

                if len(destinations) == 1:
                    pair_id = f"pair-{pair_number:04d}"
                else:
                    pair_id = (
                        f"dest-{destination_number:02d}-"
                        f"pair-{pair_number:04d}"
                    )

                for position, mode in enumerate(modes, start=1):
                    try:
                        record = run_trial(
                            mode,
                            endpoint=endpoint,
                            doh_url=doh_url,
                        )
                    except (subprocess.TimeoutExpired, OSError) as exc:
                        record = {
                            "timestamp_utc": datetime.now(
                                timezone.utc
                            ).isoformat(),
                            "requested_mode": mode,
                            "outcome": "probe_error",
                            "ech_status": "unknown",
                            "return_code": None,
                            "http_status": None,
                            "error_excerpt": str(exc),
                        }

                    record.update({
                        "campaign_id": campaign_id,
                        "pair_id": pair_id,
                        "pair_position": position,
                        "network": network,
                        "endpoint": endpoint,
                        "resolver": doh_url,
                        "destination_id": f"dest-{destination_number:02d}",
                    })

                    file.write(
                        json.dumps(record, ensure_ascii=False) + "\n"
                    )
                    file.flush()

                    print(
                        f"{pair_id} position={position} "
                        f"mode={mode} outcome="
                        f"{record.get('outcome', 'unknown')}"
                    )

                    is_last_trial = (
                        destination_number == len(destinations)
                        and pair_number == pairs
                        and position == len(modes)
                    )
                    if not is_last_trial:
                        time.sleep(pause_seconds)

    total_trials = total_pairs * 2
    print(f"\nDestinations: {len(destinations)}")
    print(f"Pairs per destination: {pairs}")
    print(f"Total pairs: {total_pairs}")
    print(f"Trials recorded: {total_trials}")
    print(f"Saved to: {output}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=10)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--network", default="current_connection")
    parser.add_argument("--pause", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--destinations",
        nargs="+",
        default=[ENDPOINT],
        help="HTTPS endpoint URLs; pairs are run for each endpoint",
    )
    parser.add_argument("--doh-url", default=DOH_URL)
    args = parser.parse_args()

    run_campaign(
        pairs=args.pairs,
        output=args.output,
        network=args.network,
        pause_seconds=args.pause,
        seed=args.seed,
        destinations=args.destinations,
        doh_url=args.doh_url,
    )


if __name__ == "__main__":
    main()
