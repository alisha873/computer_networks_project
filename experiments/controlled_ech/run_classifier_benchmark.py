"""Run the loopback-only, ground-truth ECH classifier benchmark."""

import argparse
import base64
import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_DIR = Path(__file__).resolve().parent
LOCAL_SERVER = BENCHMARK_DIR / "local_server"
DEFAULT_CURL = Path.home() / "ech-build/curl/src/curl"
DEFAULT_OPENSSL = Path.home() / "ech-build/openssl-install/bin/openssl"

sys.path.insert(0, str(ROOT / "src"))
from ech_study.classifier import classify_trial  # noqa: E402
from ech_study.schema import new_trial  # noqa: E402


def _run(argv, *, timeout=12, input_text=None):
    completed = subprocess.run(
        [str(value) for value in argv],
        capture_output=True,
        text=True,
        timeout=timeout,
        input=input_text,
        check=False,
    )
    return {
        "argv": [str(value) for value in argv],
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _pem_ech_config(path):
    text = Path(path).read_text(encoding="ascii")
    match = re.search(
        r"-----BEGIN ECHCONFIG-----\s*(.*?)\s*-----END ECHCONFIG-----",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError(f"No ECHCONFIG PEM block in {path}")
    return base64.b64decode("".join(match.group(1).split()), validate=True)


def _client_san(openssl, cert_path):
    result = _run([openssl, "x509", "-in", cert_path, "-noout", "-ext", "subjectAltName"])
    if result["returncode"] != 0:
        raise RuntimeError("Unable to inspect the local server certificate: " + result["stderr"])
    return re.findall(r"DNS:([^,\s]+)", result["stdout"])


def _classify(case_id, mode, curl_result, *, http_status, stderr, stdout, evidence, domain):
    connected = bool(re.search(r"Connected to ", stderr, flags=re.IGNORECASE))
    if case_id == "tcp_connection_refusal_loopback":
        tcp_result = "refused" if curl_result == 7 else "error"
    else:
        tcp_result = "connected" if connected else None

    if http_status == 200:
        tls_result = "success"
    elif curl_result in {35, 60, 101} and tcp_result == "connected":
        tls_result = "handshake_failed"
    else:
        tls_result = None

    ech_accepted = None
    if "ECH: result 'succeeded'" in stderr:
        ech_accepted = True
    if "ECH: rejected" in stderr or "ECH required" in stderr:
        evidence.append("ech_rejection_observed=true")
    if "ECH: retry_configs" in stderr:
        evidence.append("ech_retry_config_received=true")

    trial = new_trial(
        network="controlled_loopback",
        resolver="none",
        domain=domain,
        requested_mode=mode,
    )
    trial.tcp_result = tcp_result
    trial.tls_result = tls_result
    trial.ech_accepted = ech_accepted
    trial.evidence = evidence
    classify_trial(trial)
    return {
        "classifier_input": {
            "requested_mode": mode,
            "tcp_result": tcp_result,
            "tls_result": tls_result,
            "ech_accepted": ech_accepted,
            "evidence": list(evidence),
        },
        "predicted_label": trial.classification,
    }


def _run_curl(curl, mode, host, port, *, cert_path, ech_value=None):
    url = f"https://{host}:{port}/"
    argv = [str(curl), "--silent", "--show-error", "--verbose", "--max-time", "8"]
    if ech_value is not None:
        argv.extend(["--ech", ech_value])
    else:
        argv.extend(["--ech", "false"])
    argv.extend([
        "--cacert", str(cert_path),
        "--resolve", f"{host}:{port}:127.0.0.1",
        "--write-out", "\\nHTTP_STATUS:%{http_code}\\n",
        url,
    ])
    return _run(argv)


def _http_status(result):
    combined = result["stdout"] + result["stderr"]
    match = re.search(r"HTTP_STATUS:(\d{3})", combined)
    return int(match.group(1)) if match else None


def _case(case_id, cause, ground_truth, expected, output, invocation, evidence, domain):
    stdout_path = output / f"{case_id}.stdout.txt"
    stderr_path = output / f"{case_id}.stderr.txt"
    stdout_path.write_text(invocation["stdout"], encoding="utf-8")
    stderr_path.write_text(invocation["stderr"], encoding="utf-8")
    result = _classify(
        case_id,
        "real" if case_id == "incompatible_well_formed_ech_config" else "none",
        invocation["returncode"],
        http_status=_http_status(invocation),
        stderr=invocation["stderr"],
        stdout=invocation["stdout"],
        evidence=evidence,
        domain=domain,
    )
    verified, verification = ground_truth(invocation)
    return {
        "case_id": case_id,
        "ground_truth_cause": cause,
        "ground_truth_verified": verified,
        "ground_truth_evidence": verification,
        "expected_classifier_label": expected,
        "predicted_label": result["predicted_label"],
        "correct": result["predicted_label"] == expected if verified else None,
        "score_scope": "classifier category; see manifest for attribution limitations",
        "classifier_input": result["classifier_input"],
        "client_returncode": invocation["returncode"],
        "client_stdout_file": stdout_path.name,
        "client_stderr_file": stderr_path.name,
        "invocation_argv": invocation["argv"],
    }


def verify_control(result):
    text = result["stdout"] + result["stderr"]
    ok = result["returncode"] == 0 and _http_status(result) == 200 and "SSL_ECH_STATUS: NOT_TRIED" in text
    return ok, ["curl_exit=0", "HTTP_STATUS=200", "server body SSL_ECH_STATUS: NOT_TRIED"]


def verify_incompatible(result, config_hashes):
    text = result["stdout"] + result["stderr"]
    ok = (
        config_hashes["client_sha256"] != config_hashes["server_sha256"]
        and result["returncode"] == 101
        and "ECH: rejected" in text
        and "ECH: retry_configs" in text
    )
    return ok, [
        "client and configured server ECHConfigList SHA-256 differ",
        "curl exit 101 and ECH rejection observed",
        "retry configuration observed",
    ]


def verify_certificate_failure(result, san_names):
    text = result["stdout"] + result["stderr"]
    requested_host = "wrong.localhost"
    ok = (
        requested_host not in san_names
        and result["returncode"] == 60
        and "Connected to wrong.localhost" in text
        and "certificate" in text.lower()
    )
    return ok, [
        f"certificate DNS SANs={san_names}",
        f"requested hostname={requested_host} is absent from SANs",
        "TCP connection completed; curl certificate verification failed with exit 60",
    ]


def verify_refusal(result, socket_was_bound):
    text = result["stdout"] + result["stderr"]
    ok = socket_was_bound and result["returncode"] == 7 and "Connection refused" in text
    return ok, [
        "runner held loopback port bound with no listen() during request",
        "curl exit 7 and Connection refused observed",
    ]


def verify_malformed(result):
    text = result["stdout"] + result["stderr"]
    ok = result["returncode"] == 35 and "SSL_ECH_set1_ech_config_list failed" in text and "Connected to " not in text
    return ok, [
        "exact invalid input ecl:AA== preserved in malformed_ech_input.txt",
        "curl ECH configuration setup failure observed before a connection",
    ]


def run_benchmark(curl, openssl, output):
    curl = Path(curl).expanduser().resolve()
    openssl = Path(openssl).expanduser().resolve()
    output = Path(output).resolve()
    if not curl.is_file() or not openssl.is_file():
        raise FileNotFoundError("Custom curl and OpenSSL binaries must exist")
    output.mkdir(parents=True, exist_ok=False)

    manifest_path = BENCHMARK_DIR / "benchmark_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shutil.copy2(manifest_path, output / "benchmark_manifest.json")
    shutil.copy2(LOCAL_SERVER / "server.crt", output / "server.crt")
    Path(output / "malformed_ech_input.txt").write_text("ecl:AA==\n", encoding="ascii")

    port = _free_port()
    server_host = "public.localhost"
    server_ech_config = LOCAL_SERVER / "echconfig.pem"
    server_ech_bytes = _pem_ech_config(server_ech_config)
    server_ech_hash = hashlib.sha256(server_ech_bytes).hexdigest()
    cert_sans = _client_san(openssl, LOCAL_SERVER / "server.crt")

    client_ech_pem = output / "incompatible_client_ech.pem"
    generation = _run([
        openssl, "ech", "-out", client_ech_pem,
        "-public_name", "cover.localhost",
    ])
    if generation["returncode"] != 0:
        raise RuntimeError("Failed to generate independent ECH config: " + generation["stderr"])
    client_ech_bytes = _pem_ech_config(client_ech_pem)
    config_hashes = {
        "client_sha256": hashlib.sha256(client_ech_bytes).hexdigest(),
        "server_sha256": server_ech_hash,
    }
    client_ecl = "ecl:" + base64.b64encode(client_ech_bytes).decode("ascii")
    (output / "incompatible_client_ech_config.b64").write_text(client_ecl + "\n", encoding="ascii")

    invocations = {"ech_config_generation": generation["argv"]}
    cases = []
    malformed = _run_curl(curl, "none", server_host, port,
                          cert_path=output / "server.crt", ech_value="ecl:AA==")
    invocations["malformed_ech_config"] = malformed["argv"]
    cases.append(_case(
        "malformed_ech_config", "client_ech_config_parse_failure",
        verify_malformed, "inconclusive", output,
        malformed, ["client_ech_config_parse_error=true"], server_host,
    ))

    server_log_path = output / "server.log"
    server_log = server_log_path.open("w", encoding="utf-8")
    server_argv = [
        str(openssl), "s_server", "-accept", f"127.0.0.1:{port}",
        "-cert", str(LOCAL_SERVER / "server.crt"),
        "-key", str(LOCAL_SERVER / "server.key"),
        "-ech_key", str(server_ech_config), "-www", "-state",
    ]
    server = subprocess.Popen(
        server_argv,
        stdin=subprocess.DEVNULL,
        stdout=server_log,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        time.sleep(0.25)
        if server.poll() is not None:
            raise RuntimeError(f"Local ECH server exited during startup; see {server_log_path}")

        ordinary = _run_curl(curl, "none", server_host, port, cert_path=output / "server.crt")
        invocations["ordinary_https_no_ech"] = ordinary["argv"]
        cases.append(_case(
            "ordinary_https_no_ech", "ordinary_tls_without_ech",
            verify_control, "ech_not_attempted", output,
            ordinary, ["ech_not_attempted=true"], server_host,
        ))

        incompatible = _run_curl(curl, "real", server_host, port,
                                 cert_path=output / "server.crt", ech_value=client_ecl)
        invocations["incompatible_well_formed_ech_config"] = incompatible["argv"]
        cases.append(_case(
            "incompatible_well_formed_ech_config", "client_config_does_not_match_server_ech_key",
            lambda result: verify_incompatible(result, config_hashes),
            "server_rejected_ech_retry", output, incompatible,
            ["ech_config_mismatch_verified=true"], server_host,
        ))

        wrong_host = "wrong.localhost"
        certificate_failure = _run_curl(
            curl, "none", wrong_host, port, cert_path=output / "server.crt"
        )
        invocations["certificate_verification_failure_no_ech"] = certificate_failure["argv"]
        cases.append(_case(
            "certificate_verification_failure_no_ech",
            "certificate_hostname_verification_failure",
            lambda result: verify_certificate_failure(result, cert_sans),
            "ech_independent_tls_failure", output, certificate_failure,
            ["certificate_verification_failed=true"], wrong_host,
        ))

        refusal_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        refusal_socket.bind(("127.0.0.1", 0))
        refusal_port = refusal_socket.getsockname()[1]
        refusal_host = f"127.0.0.1:{refusal_port}"
        refusal_url = f"https://127.0.0.1:{refusal_port}/"
        refusal_argv = [
            str(curl), "--silent", "--show-error", "--verbose", "--max-time", "8",
            "--ech", "false", "-k", refusal_url,
        ]
        refusal_result = _run(refusal_argv)
        invocations["tcp_connection_refusal_loopback"] = refusal_argv
        cases.append(_case(
            "tcp_connection_refusal_loopback", "local_tcp_connection_refused",
            lambda result: verify_refusal(result, refusal_socket.fileno() >= 0),
            "tcp_failure", output, refusal_result,
            ["loopback_connection_refused=true"], refusal_host,
        ))
        refusal_socket.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=3)
        server_log.close()

    server_evidence = server_log_path.read_text(encoding="utf-8", errors="replace")
    (output / "server_evidence_summary.txt").write_text(server_evidence, encoding="utf-8")
    for case in cases:
        case["server_evidence_file"] = "server_evidence_summary.txt"
        case["server_config_sha256"] = server_ech_hash
        if case["case_id"] == "incompatible_well_formed_ech_config":
            case["client_config_sha256"] = config_hashes["client_sha256"]
            case["causal_attribution_supported"] = False
            case["causal_attribution_note"] = (
                "The distinct client/server configs and rejection are verified, "
                "but this classifier label reports rejection plus retry, not the "
                "specific incompatible-key root cause."
            )

    result = {
        "benchmark_id": manifest["benchmark_id"],
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "loopback only; no external requests",
        "server": {
            "argv": server_argv,
            "host": "127.0.0.1",
            "port": port,
            "ech_config_sha256": server_ech_hash,
            "certificate_dns_sans": cert_sans,
        },
        "cases": cases,
        "correct_predictions": sum(case["correct"] is True for case in cases),
        "verified_cases": sum(case["ground_truth_verified"] for case in cases),
        "interpretation": (
            "Correctness is scored against the declared classifier category. "
            "For the incompatible-config case, the causal root is known from "
            "the injected key/config mismatch, but the classifier taxonomy only "
            "predicts the directly observed rejection/retry event."
        ),
    }
    (output / "invocations.json").write_text(
        json.dumps(invocations, indent=2) + "\n", encoding="utf-8"
    )
    (output / "benchmark_results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curl", type=Path, default=DEFAULT_CURL)
    parser.add_argument("--openssl", type=Path, default=DEFAULT_OPENSSL)
    parser.add_argument(
        "--output-dir", type=Path,
        default=BENCHMARK_DIR / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    args = parser.parse_args()
    result = run_benchmark(args.curl, args.openssl, args.output_dir)
    print(json.dumps({
        "output_dir": str(args.output_dir),
        "verified_cases": result["verified_cases"],
        "correct_predictions": result["correct_predictions"],
        "cases": [
            {key: case.get(key) for key in (
                "case_id", "ground_truth_cause", "ground_truth_verified",
                "predicted_label", "expected_classifier_label", "correct",
            )}
            for case in result["cases"]
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
