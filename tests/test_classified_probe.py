from ech_study.probe.classified_probe import classify_curl_record


def make_record(**overrides):
    record = {
        "requested_mode": "true",
        "ech_status": "succeeded",
        "outcome": "ech_success",
        "return_code": 0,
        "http_status": 200,
        "trace_sni": "encrypted",
        "network": "test_network",
        "resolver": "https://one.one.one.one/dns-query",
        "domain": "crypto.cloudflare.com",
    }
    record.update(overrides)
    return record


def test_valid_ech_success():
    result = classify_curl_record(make_record())
    assert result["experiment_outcome"] == "ech_success"
    assert result["ech_accepted"] is True


def test_plaintext_sni_does_not_count_as_ech_success():
    result = classify_curl_record(make_record(trace_sni="plaintext"))
    assert result["ech_accepted"] is None
    assert result["experiment_outcome"] == "inconclusive"


def test_string_http_status_is_not_treated_as_integer():
    result = classify_curl_record(make_record(http_status="200"))
    assert result["http_result"] == "unknown"
    assert result["experiment_outcome"] == "inconclusive"


def test_nonzero_curl_exit_code_is_connection_error():
    result = classify_curl_record(
        make_record(return_code=28, http_status=None, trace_sni=None)
    )
    assert result["experiment_outcome"] == "connection_error"
    assert result["tcp_result"] is None
    assert result["tls_result"] is None


def test_missing_fields_do_not_count_as_success():
    result = classify_curl_record({})
    assert result["ech_accepted"] is None
    assert result["experiment_outcome"] != "ech_success"


def test_http_status_does_not_override_nonzero_exit_code():
    result = classify_curl_record(make_record(return_code=28))
    assert result["experiment_outcome"] == "connection_error"
    assert result["tcp_result"] is None
    assert result["tls_result"] is None


def test_explicit_ech_rejection_and_retry_are_classified():
    result = classify_curl_record(
        make_record(
            return_code=101,
            http_status=0,
            ech_status="unknown",
            outcome="connection_error",
            trace_sni=None,
            ech_rejection_observed=True,
            ech_retry_config_received=True,
        )
    )

    assert result["classification"] == "server_rejected_ech_retry"
    assert "ech_rejection_observed" in result["classification_evidence"]
    assert "ech_retry_config_received" in result["classification_evidence"]
    # The protocol classification and request outcome answer different questions.
    assert result["experiment_outcome"] == "connection_error"


def test_ech_rejection_without_retry_remains_inconclusive():
    result = classify_curl_record(
        make_record(
            return_code=101,
            http_status=0,
            ech_status="unknown",
            outcome="connection_error",
            trace_sni=None,
            ech_rejection_observed=True,
            ech_retry_config_received=False,
        )
    )

    assert result["classification"] == "inconclusive"
    assert "ech_rejection_observed" in result["classification_evidence"]
    assert "ech_retry_config_received" not in result["classification_evidence"]


def test_enriched_record_preserves_ech_rejection_flags():
    record = make_record(
        return_code=101,
        http_status=0,
        ech_status="unknown",
        outcome="connection_error",
        trace_sni=None,
        ech_rejection_observed=True,
        ech_retry_config_received=True,
    )

    result = classify_curl_record(record)

    assert result["ech_rejection_observed"] is True
    assert result["ech_retry_config_received"] is True
    assert "ech_rejection_observed" in result["classification_evidence"]
    assert "ech_retry_config_received" in result["classification_evidence"]
    assert result["classification"] == "server_rejected_ech_retry"
    assert result["experiment_outcome"] == "connection_error"
