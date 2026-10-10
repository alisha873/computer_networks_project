"""Shared schema for ECH measurements.

Unknown observations must be represented as None, serialized as JSON null.
A failed measurement does not, by itself, prove censorship.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from typing import Any


VALID_MODES = {"none", "grease", "real", "unknown"}

VALID_CLASSIFICATIONS = {
    "ech_not_attempted",
    "dns_anomaly",
    "tcp_failure",
    "ech_specific_tls_failure",
    "ech_independent_tls_failure",
    "server_rejected_ech_retry",
    "success",
    "inconclusive",
}


@dataclass
class Trial:
    timestamp_utc: str
    network: str
    resolver: str
    domain: str
    requested_mode: str = "unknown"

    https_record_present: bool | None = None
    tcp_result: str | None = None
    tls_result: str | None = None
    ech_accepted: bool | None = None

    classification: str = "inconclusive"
    evidence: list[str] | None = None

    def validate(self) -> None:
        """Raise ValueError if required fields or enumerated values are invalid."""
        for field_name in ("timestamp_utc", "network", "resolver", "domain"):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")

        if self.requested_mode not in VALID_MODES:
            raise ValueError(f"Invalid requested_mode: {self.requested_mode}")

        if self.classification not in VALID_CLASSIFICATIONS:
            raise ValueError(f"Invalid classification: {self.classification}")

        if self.https_record_present not in (True, False, None):
            raise ValueError("https_record_present must be true, false, or null")

        if self.ech_accepted not in (True, False, None):
            raise ValueError("ech_accepted must be true, false, or null")

        try:
            parsed = datetime.fromisoformat(
                self.timestamp_utc.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ValueError("timestamp_utc must be an ISO-8601 timestamp") from exc

        if parsed.tzinfo is None:
            raise ValueError("timestamp_utc must include a timezone")

    def to_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), sort_keys=True)


def new_trial(
    network: str,
    resolver: str,
    domain: str,
    requested_mode: str = "unknown",
) -> Trial:
    """Create a trial with a timezone-aware UTC timestamp."""
    return Trial(
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        network=network,
        resolver=resolver,
        domain=domain,
        requested_mode=requested_mode,
        evidence=[],
    )


def append_jsonl(path: str, trial: Trial) -> None:
    """Append one validated trial to a JSON Lines file."""
    with open(path, "a", encoding="utf-8") as file:
        file.write(trial.to_json() + "\n")


def read_jsonl(path: str) -> list[dict[str, Any]]:
    """Read JSONL records and reject malformed JSON."""
    records = []
    with open(path, encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {path}"
                ) from exc
    return records
