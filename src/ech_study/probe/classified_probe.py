"""Classify ECH curl observations while preserving layer-specific evidence."""

from ech_study.schema import new_trial
from ech_study.classifier import classify_trial


def classify_curl_record(record: dict) -> dict:
    """Enrich one raw curl record without inferring censorship."""
    mode = record.get("requested_mode", "unknown")
    ech_status = record.get("ech_status", "unknown")
    raw_outcome = record.get("outcome", "inconclusive")
    return_code = record.get("return_code")
    http_status = record.get("http_status")
    trace_sni = record.get("trace_sni")

    requested_mode = (
        "real" if mode == "true"
        else "none" if mode == "false"
        else "unknown"
    )

    # A completed HTTP response demonstrates that the request progressed
    # through connection establishment and TLS, but does not by itself
    # establish that ECH was accepted.
    tcp_result = "connected" if return_code == 0 and http_status is not None else None
    tls_result = "success" if return_code == 0 and http_status is not None else None
    http_result = (
        "success" if isinstance(http_status, int) and 200 <= http_status < 400
        else "error" if isinstance(http_status, int)
        else "unknown"
    )

    ech_accepted = (
        True if mode == "true"
        and ech_status == "succeeded"
        and trace_sni == "encrypted"
        else None
    )

    evidence = [
        f"raw_outcome={raw_outcome}",
        f"curl_ech_status={ech_status}",
    ]
    if trace_sni:
        evidence.append(f"trace_sni={trace_sni}")

    rejection_observed = record.get("ech_rejection_observed") is True
    retry_config_received = record.get("ech_retry_config_received") is True

    if rejection_observed:
        evidence.append("ech_rejection_observed")
    if retry_config_received:
        evidence.append("ech_retry_config_received")

    if ech_accepted is True:
        evidence.append("ech_success_explicitly_reported_by_curl")
    if return_code != 0 or http_status is None:
        evidence.append("transport_or_tls_stage_not_fully_verified")

    trial = new_trial(
        network=record.get("network", "unknown"),
        resolver=record.get("resolver", "unknown"),
        domain=record.get("domain", "unknown"),
        requested_mode=requested_mode,
    )
    trial.tcp_result = tcp_result
    trial.tls_result = tls_result
    trial.ech_accepted = ech_accepted
    trial.evidence = evidence
    classify_trial(trial)

    # A nonzero curl exit code takes precedence over apparent success fields.
    # Preserve the raw fields, but do not count contradictory records as success.
    if return_code not in (None, 0):
        experiment_outcome = "connection_error"
    elif ech_accepted is True and http_result == "success":
        experiment_outcome = "ech_success"
    elif (
        mode == "false"
        and ech_status == "not_attempted"
        and tls_result == "success"
        and http_result == "success"
    ):
        experiment_outcome = "control_success"
    elif http_result == "error":
        experiment_outcome = "http_error"
    else:
        experiment_outcome = "inconclusive"

    enriched = dict(record)
    enriched.update({
        "classification": trial.classification,
        "classification_evidence": trial.evidence,
        "requested_mode_normalized": requested_mode,
        "tcp_result": tcp_result,
        "tls_result": tls_result,
        "ech_accepted": ech_accepted,
        "http_result": http_result,
        "experiment_outcome": experiment_outcome,
    })
    return enriched
