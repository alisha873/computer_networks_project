"""Normalize OONI raw measurements without losing source distinctions."""


def summarize_raw_measurement(
    raw: dict,
    metadata: dict | None = None,
) -> dict:
    keys = raw.get("test_keys") or {}
    annotations = raw.get("annotations") or {}
    metadata = metadata or {}

    tcp_events = [
        {
            "address": event.get("address"),
            "failure": event.get("failure"),
            "operation": event.get("operation"),
            "protocol": event.get("proto"),
        }
        for event in (keys.get("network_events") or [])
        if isinstance(event, dict) and event.get("proto") == "tcp"
    ]

    dns_queries = [
        {
            "hostname": query.get("hostname"),
            "query_type": query.get("query_type"),
            "failure": query.get("failure"),
            "answers": query.get("answers"),
        }
        for query in (keys.get("queries") or [])
        if isinstance(query, dict)
    ]

    control = keys.get("control") or {}

    return {
        "source": "ooni",
        "is_ech_measurement": False,
        "measurement_start_time": raw.get("measurement_start_time"),
        "probe_cc": raw.get("probe_cc"),
        "probe_asn": raw.get("probe_asn"),
        "probe_network_name": raw.get("probe_network_name"),
        "resolver_asn": raw.get("resolver_asn"),
        "resolver_ip": raw.get("resolver_ip"),
        "network_type": annotations.get("network_type"),
        "test_name": raw.get("test_name"),
        "input": raw.get("input"),

        # These fields are supplied by the API metadata.
        "anomaly": metadata.get("anomaly"),
        "confirmed": metadata.get("confirmed"),
        "failure": metadata.get("failure"),

        # These fields come from the raw test_keys.
        "accessible": keys.get("accessible"),
        "blocking": keys.get("blocking"),
        "dns_consistency": keys.get("dns_consistency"),
        "dns_experiment_failure": keys.get("dns_experiment_failure"),
        "http_experiment_failure": keys.get("http_experiment_failure"),
        "control_failure": keys.get("control_failure"),
        "dns_queries": dns_queries,
        "tcp_events": tcp_events,
        "tcp_control": control.get("tcp_connect"),
        "tls_control": control.get("tls_handshake"),
    }
