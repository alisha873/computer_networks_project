"""Conservative classification of ECH measurement trials.

A connection failure alone is never proof of censorship.
Explicit evidence is required to attribute a failure specifically to ECH.
"""

from ech_study.schema import Trial


def classify_trial(trial: Trial) -> Trial:
    """Classify a trial using its recorded observations and evidence.

    The function updates trial.classification and returns the same Trial.
    Evidence strings should record observed facts, not assumptions.
    """
    evidence = list(trial.evidence or [])
    facts = {item.strip().lower() for item in evidence}

    def has_fact(*terms: str) -> bool:
        return any(
            term in fact
            for fact in facts
            for term in terms
        )

    def add_fact(message: str) -> None:
        if message not in evidence:
            evidence.append(message)

    mode = trial.requested_mode
    tcp = (trial.tcp_result or "").strip().lower()
    tls = (trial.tls_result or "").strip().lower()

    # An explicit server retry signal takes precedence over generic failures.
    if has_fact("server_rejected_ech_retry", "ech_retry_config_received"):
        trial.classification = "server_rejected_ech_retry"
        add_fact("classification_basis=explicit_ech_retry_evidence")
        trial.evidence = evidence
        return trial

    # DNS anomalies must be explicitly identified by the measurement logic.
    if has_fact("dns_anomaly", "dns_tampering_confirmed"):
        trial.classification = "dns_anomaly"
        add_fact("classification_basis=explicit_dns_anomaly_evidence")
        trial.evidence = evidence
        return trial

    # Only an explicit ECH acceptance observation supports ECH success.
    if mode in {"none", "grease"} and trial.ech_accepted is True:
        trial.classification = "inconclusive"
        add_fact("classification_basis=ech_acceptance_conflicts_with_requested_mode")
        trial.evidence = evidence
        return trial

    if (
        mode == "real"
        and trial.ech_accepted is True
        and tls in {"success", "succeeded", "ok"}
        and tcp in {"connected", "success", "succeeded", "ok"}
    ):
        trial.classification = "success"
        add_fact("classification_basis=ech_accepted_and_tls_succeeded")
        trial.evidence = evidence
        return trial

    # Transport failure does not identify the cause or imply censorship.
    if tcp in {
        "failed", "failure", "timeout", "timed_out",
        "refused", "reset", "unreachable", "error",
    }:
        trial.classification = "tcp_failure"
        add_fact("classification_basis=tcp_connection_failure")
        trial.evidence = evidence
        return trial

    # Attribute TLS failure to ECH only when evidence explicitly supports it.
    if tls in {"failed", "failure", "error", "handshake_failed"}:
        if has_fact(
            "ech_specific_tls_failure",
            "ech_failure_confirmed",
        ):
            trial.classification = "ech_specific_tls_failure"
            add_fact("classification_basis=explicit_ech_specific_tls_failure")
        elif mode in {"none", "grease"} or has_fact(
            "ech_independent_tls_failure",
            "failure_with_ech_disabled",
        ):
            trial.classification = "ech_independent_tls_failure"
            add_fact("classification_basis=ech_independent_tls_failure")
        else:
            trial.classification = "inconclusive"
            add_fact("classification_basis=tls_failure_cause_unproven")

        trial.evidence = evidence
        return trial

    # A missing ECH attempt is not a failure of ECH.
    if (
        mode == "none"
        or has_fact("ech_not_attempted", "ech_attempted=false")
        or has_fact("ech_config_absent", "ech_config_not_advertised")
    ):
        trial.classification = "ech_not_attempted"
        add_fact("classification_basis=ech_not_attempted")
        trial.evidence = evidence
        return trial

    # An ECH rejection without retry evidence is not enough to classify it.
    trial.classification = "inconclusive"
    add_fact("classification_basis=insufficient_or_ambiguous_evidence")
    trial.evidence = evidence
    return trial
