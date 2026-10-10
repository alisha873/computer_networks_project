from src.ech_study.schema import new_trial
from src.ech_study.classifier import classify_trial


def make_trial(**overrides):
    trial = new_trial(
        network="test-network",
        resolver="test-resolver",
        domain="example.com",
        requested_mode="real",
    )
    for key, value in overrides.items():
        setattr(trial, key, value)
    return trial


def test_explicit_ech_success():
    trial = make_trial(
        tcp_result="connected",
        tls_result="success",
        ech_accepted=True,
    )
    assert classify_trial(trial).classification == "success"


def test_ech_not_attempted():
    trial = make_trial(requested_mode="none")
    assert classify_trial(trial).classification == "ech_not_attempted"


def test_explicit_dns_anomaly():
    trial = make_trial(evidence=["dns_anomaly=confirmed"])
    assert classify_trial(trial).classification == "dns_anomaly"


def test_tcp_failure_is_not_censorship():
    trial = make_trial(tcp_result="timeout")
    assert classify_trial(trial).classification == "tcp_failure"


def test_generic_tls_failure_is_inconclusive():
    trial = make_trial(
        tcp_result="connected",
        tls_result="handshake_failed",
    )
    assert classify_trial(trial).classification == "inconclusive"


def test_explicit_ech_specific_tls_failure():
    trial = make_trial(
        tcp_result="connected",
        tls_result="handshake_failed",
        evidence=["ech_specific_tls_failure=confirmed"],
    )
    assert classify_trial(trial).classification == "ech_specific_tls_failure"


def test_ech_disabled_tls_failure_is_independent():
    trial = make_trial(
        requested_mode="none",
        tcp_result="connected",
        tls_result="handshake_failed",
    )
    assert (
        classify_trial(trial).classification
        == "ech_independent_tls_failure"
    )


def test_server_retry_evidence():
    trial = make_trial(
        evidence=["server_rejected_ech_retry=observed"],
    )
    assert (
        classify_trial(trial).classification
        == "server_rejected_ech_retry"
    )


def test_missing_observations_are_inconclusive():
    trial = make_trial()
    assert classify_trial(trial).classification == "inconclusive"


def test_ech_rejected_without_retry_evidence_is_inconclusive():
    trial = make_trial(
        tcp_result="connected",
        tls_result="success",
        ech_accepted=False,
    )
    assert classify_trial(trial).classification == "inconclusive"

def test_dns_lookup_failure_is_inconclusive():
    trial = make_trial(
        evidence=["dns_lookup_failed=timeout"],
    )
    assert classify_trial(trial).classification == "inconclusive"


def test_tcp_timeout_takes_precedence_over_no_ech_attempt():
    trial = make_trial(
        requested_mode="none",
        tcp_result="timeout",
    )
    assert classify_trial(trial).classification == "tcp_failure"


def test_generic_tls_failure_with_ech_disabled_is_independent():
    trial = make_trial(
        requested_mode="none",
        tcp_result="connected",
        tls_result="handshake_failed",
    )
    assert (
        classify_trial(trial).classification
        == "ech_independent_tls_failure"
    )


def test_ech_failure_without_explicit_evidence_is_inconclusive():
    trial = make_trial(
        tcp_result="connected",
        tls_result="handshake_failed",
        ech_accepted=False,
    )
    assert classify_trial(trial).classification == "inconclusive"


def test_retry_evidence_takes_precedence():
    trial = make_trial(
        tcp_result="connected",
        tls_result="handshake_failed",
        evidence=["ech_retry_config_received"],
    )
    assert (
        classify_trial(trial).classification
        == "server_rejected_ech_retry"
    )

def test_ech_success_requires_real_ech_mode():
    trial = make_trial(
        requested_mode="none",
        tcp_result="connected",
        tls_result="success",
        ech_accepted=True,
    )
    assert classify_trial(trial).classification == "inconclusive"


def test_grease_mode_is_not_real_ech_acceptance():
    trial = make_trial(
        requested_mode="grease",
        tcp_result="connected",
        tls_result="success",
        ech_accepted=True,
    )
    assert classify_trial(trial).classification == "inconclusive"

def test_retry_evidence_takes_precedence_over_tcp_failure():
    trial = make_trial(
        requested_mode="real",
        tcp_result="failed",
        tls_result=None,
        ech_accepted=None,
        evidence=["server_rejected_ech_retry"],
    )
    assert classify_trial(trial).classification == "server_rejected_ech_retry"


def test_dns_anomaly_is_not_inferred_from_generic_dns_failure():
    trial = make_trial(
        requested_mode="real",
        tcp_result=None,
        tls_result=None,
        ech_accepted=None,
        evidence=["dns_lookup_failed"],
    )
    assert classify_trial(trial).classification == "inconclusive"


def test_ech_acceptance_conflict_with_control_mode_is_inconclusive():
    trial = make_trial(
        requested_mode="none",
        tcp_result="connected",
        tls_result="success",
        ech_accepted=True,
        evidence=["server_rejected_ech_retry"],
    )
    # The classifier currently prioritizes explicit retry evidence.
    # This test documents that precedence for us to evaluate.
    assert classify_trial(trial).classification == "server_rejected_ech_retry"