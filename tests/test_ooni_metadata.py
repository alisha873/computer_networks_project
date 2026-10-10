from ech_study.ooni.ingest import summarize_raw_measurement


def test_summary_uses_api_metadata_for_anomaly_fields():
    raw = {
        "probe_cc": "IN",
        "test_name": "web_connectivity",
        "test_keys": {
            "accessible": False,
            "blocking": "dns",
            "dns_consistency": "inconsistent",
            "http_experiment_failure": "generic_timeout_error",
        },
    }
    metadata = {
        "anomaly": True,
        "confirmed": False,
        "failure": False,
    }

    result = summarize_raw_measurement(raw, metadata=metadata)

    assert result["anomaly"] is True
    assert result["confirmed"] is False
    assert result["failure"] is False
    assert result["blocking"] == "dns"
    assert result["accessible"] is False
    assert result["dns_consistency"] == "inconsistent"
    assert result["is_ech_measurement"] is False


def test_missing_metadata_remains_unknown():
    result = summarize_raw_measurement({"test_keys": {}})

    assert result["anomaly"] is None
    assert result["confirmed"] is None
    assert result["failure"] is None
