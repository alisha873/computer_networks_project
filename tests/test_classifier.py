import pytest

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
        evidence=["ech_accepted=true", "ech_acceptance_observed=confirmed"],
    )
    assert classify_trial(trial).classification == "success"


def test_ech_not_attempted():
    trial = make_trial(requested_mode="none")
    assert classify_trial(trial).classification == "ech_not_attempted"


def test_successful_control_handshake_is_ech_not_attempted():
    trial = make_trial(
        requested_mode="none",
        tcp_result="connected",
        tls_result="success",
        ech_accepted=False,
    )
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


def test_retry_configuration_alone_is_inconclusive():
    trial = make_trial(
        tcp_result="connected",
        tls_result="handshake_failed",
        evidence=["ech_retry_config_received"],
    )
    assert classify_trial(trial).classification == "inconclusive"


def test_ech_rejection_without_retry_configuration_is_inconclusive():
    trial = make_trial(evidence=["ech_rejection_observed"])
    assert classify_trial(trial).classification == "inconclusive"


def test_rejection_and_retry_configuration_classify_server_retry():
    trial = make_trial(
        evidence=[
            "ech_rejection_observed=confirmed",
            "ech_retry_config_received=true",
        ],
    )
    assert classify_trial(trial).classification == "server_rejected_ech_retry"


def test_consolidated_server_retry_marker_is_sufficient():
    trial = make_trial(evidence=["server_rejected_ech_retry"])
    assert classify_trial(trial).classification == "server_rejected_ech_retry"


@pytest.mark.parametrize("mode", ["none", "grease"])
def test_ech_specific_tls_failure_conflicts_with_none_or_grease(mode):
    trial = make_trial(
        requested_mode=mode,
        tcp_result="connected",
        tls_result="handshake_failed",
        evidence=["ech_specific_tls_failure=confirmed"],
    )
    assert classify_trial(trial).classification == "inconclusive"

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
    assert classify_trial(trial).classification == "inconclusive"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        pytest.param(
            {"requested_mode": "unknown", "tls_result": "handshake_failed"},
            "inconclusive",
            id="unknown-mode-and-tls-failure",
        ),
        pytest.param(
            {"requested_mode": "unknown", "tcp_result": "unknown", "tls_result": "unknown"},
            "inconclusive",
            id="unknown-observations",
        ),
        pytest.param(
            {
                "requested_mode": "real",
                "tcp_result": "connected",
                "tls_result": "handshake_failed",
                "ech_accepted": True,
                "evidence": ["ech_specific_tls_failure=confirmed"],
            },
            "inconclusive",
            id="acceptance-conflicts-with-tls-failure",
        ),
        pytest.param(
            {
                "requested_mode": "none",
                "tcp_result": "connected",
                "tls_result": "handshake_failed",
                "evidence": ["ech_specific_tls_failure=confirmed"],
            },
            "inconclusive",
            id="ech-specific-failure-while-disabled",
        ),
        pytest.param(
            {
                "tcp_result": "connected",
                "tls_result": "handshake_failed",
                "evidence": ["ech_specific_tls_failure=false"],
            },
            "inconclusive",
            id="negative-ech-specific-marker",
        ),
        pytest.param(
            {
                "tcp_result": "connected",
                "tls_result": "handshake_failed",
                "evidence": ["not_ech_specific_tls_failure=true"],
            },
            "inconclusive",
            id="similar-but-not-matching-marker",
        ),
        pytest.param(
            {
                "tcp_result": "connected",
                "tls_result": "success",
                "evidence": ["ech_rejection_observed"],
            },
            "inconclusive",
            id="rejection-without-retry-config",
        ),
        pytest.param(
            {
                "evidence": ["dns_anomaly=false"],
            },
            "inconclusive",
            id="negative-dns-anomaly-marker",
        ),
    ],
)
def test_ambiguous_and_contradictory_records_are_inconclusive(overrides, expected):
    trial = make_trial(**overrides)
    assert classify_trial(trial).classification == expected


def test_repeated_and_unrelated_evidence_do_not_change_specific_failure():
    trial = make_trial(
        tcp_result="connected",
        tls_result="handshake_failed",
        evidence=[
            "ech_specific_tls_failure=confirmed",
            "ech_specific_tls_failure=confirmed",
            "curl_error_excerpt=handshake failed",
        ],
    )

    assert classify_trial(trial).classification == "ech_specific_tls_failure"
    assert trial.evidence.count("ech_specific_tls_failure=confirmed") == 2