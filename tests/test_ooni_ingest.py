from ech_study.ooni.ingest import summarize_raw_measurement


def test_extracts_ooni_network_observations():
    raw = {
        "probe_cc": "IN",
        "probe_asn": "AS24560",
        "test_name": "web_connectivity",
        "input": "https://example.com/",
        "anomaly": True,
        "confirmed": False,
        "test_keys": {
            "dns_consistency": "consistent",
            "accessible": False,
            "blocking": "dns",
            "queries": [
                {
                    "hostname": "example.com",
                    "query_type": "A",
                    "failure": None,
                    "answers": [{"answer_type": "A", "ipv4": "192.0.2.1"}],
                }
            ],
            "network_events": [
                {
                    "address": "192.0.2.1:443",
                    "failure": "generic_timeout_error",
                    "operation": "connect",
                    "proto": "tcp",
                }
            ],
            "control": {
                "tcp_connect": {"192.0.2.2:443": {"status": True}},
                "tls_handshake": {},
            },
        },
    }

    result = summarize_raw_measurement(raw)

    assert result["source"] == "ooni"
    assert result["is_ech_measurement"] is False
    assert result["probe_cc"] == "IN"
    assert result["dns_consistency"] == "consistent"
    assert result["blocking"] == "dns"
    assert result["dns_queries"][0]["hostname"] == "example.com"
    assert result["tcp_events"][0]["failure"] == "generic_timeout_error"
    assert result["tcp_control"]["192.0.2.2:443"]["status"] is True


def test_missing_fields_remain_unknown():
    result = summarize_raw_measurement({})

    assert result["source"] == "ooni"
    assert result["is_ech_measurement"] is False
    assert result["anomaly"] is None
    assert result["dns_queries"] == []
    assert result["tcp_events"] == []
