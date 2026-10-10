"""Initial DNS and TCP baseline probe. Does not perform an ECH handshake."""

import argparse
import ipaddress
import socket

import dns.exception
import dns.resolver
import json
from pathlib import Path

from ech_study.schema import append_jsonl, new_trial


ECH_PARAM_KEY = 5  # SVCB/HTTPS ECH parameter


def make_resolver(resolver_address: str) -> dns.resolver.Resolver:
    resolver = dns.resolver.Resolver(configure=(resolver_address == "system"))
    resolver.timeout = 3
    resolver.lifetime = 5

    if resolver_address != "system":
        # Accept an IP address, not an arbitrary hostname.
        ipaddress.ip_address(resolver_address)
        resolver.nameservers = [resolver_address]

    return resolver


def query_records(resolver, domain: str, record_type: str):
    try:
        answer = resolver.resolve(domain, record_type, raise_on_no_answer=False)
        if answer.rrset is None:
            return [], "no_answer"
        return list(answer), "answer"
    except dns.resolver.NXDOMAIN:
        return [], "nxdomain"
    except dns.resolver.NoNameservers:
        return [], "no_nameservers"
    except (dns.exception.Timeout, dns.resolver.NoAnswer):
        return [], "timeout_or_no_answer"
    except dns.exception.DNSException as exc:
        return [], f"dns_error:{type(exc).__name__}"


def run_probe(domain: str, network: str, resolver_address: str) -> dict:
    resolver = make_resolver(resolver_address)
    trial = new_trial(
        network=network,
        resolver=resolver_address,
        domain=domain,
        requested_mode="unknown",
    )

    evidence = []

    # 1. Query HTTPS records and inspect their ECH parameter.
    https_records, https_status = query_records(resolver, domain, "HTTPS")
    trial.https_record_present = (
        bool(https_records) if https_status in {"answer", "no_answer"} else None
    )
    evidence.append(f"https_dns_status={https_status}")

    ech_config_advertised = False

    for record in https_records:
        params = getattr(record, "params", {})
        if any(
            getattr(key, "value", key) == ECH_PARAM_KEY
            for key in params
        ):
            ech_config_advertised = True
            break

    evidence.append(f"ech_config_advertised={ech_config_advertised}")

    # 2. Resolve IPv4 and IPv6 addresses using the same resolver.
    addresses = []
    address_errors = []

    for record_type in ("A", "AAAA"):
        records, status = query_records(resolver, domain, record_type)
        addresses.extend(str(record) for record in records)
        if status not in {"answer", "no_answer"}:
            address_errors.append(f"{record_type}:{status}")

    # 3. Test TCP connectivity to port 443. No TLS or HTTP request is sent.
    if not addresses:
        trial.tcp_result = "not_attempted_no_address"
        evidence.append("tcp_reason=no_resolved_address")
        evidence.extend(address_errors)
    else:
        connected_address = None
        errors = []

        for address in dict.fromkeys(addresses):
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            sock = socket.socket(family, socket.SOCK_STREAM)
            sock.settimeout(3)

            try:
                sock.connect((address, 443))
                connected_address = address
                break
            except OSError as exc:
                errors.append(f"{address}:{type(exc).__name__}")
            finally:
                sock.close()

        if connected_address:
            trial.tcp_result = "connected"
            evidence.append(f"tcp_connected_address={connected_address}")
        else:
            trial.tcp_result = "failed"
            evidence.append("tcp_errors=" + ",".join(errors))

    # DNS/TCP observations alone cannot establish ECH success or censorship.
    trial.ech_accepted = None
    trial.tls_result = None
    trial.classification = "inconclusive"
    trial.evidence = evidence

    trial.validate()
    return trial.__dict__

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--network", default="unidentified")
    parser.add_argument("--resolver", default="system")
    parser.add_argument("--output", default="results/pilot_results.jsonl")
    args = parser.parse_args()

    result = run_probe(args.domain, args.network, args.resolver)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("a", encoding="utf-8") as file:
        file.write(json.dumps(result, sort_keys=True) + "\n")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()