import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "controlled_ech"
    / "run_classifier_benchmark.py"
)
spec = importlib.util.spec_from_file_location("controlled_ech_benchmark", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def predict(case_id, mode, returncode, stdout="", stderr="", evidence=None):
    return benchmark._classify(
        case_id,
        mode,
        returncode,
        http_status=benchmark._http_status({"stdout": stdout, "stderr": stderr}),
        stdout=stdout,
        stderr=stderr,
        evidence=list(evidence or []),
        domain="public.localhost",
    )["predicted_label"]


def test_local_ordinary_https_without_ech_is_not_attempted():
    assert predict(
        "ordinary_https_no_ech",
        "none",
        0,
        stdout="SSL_ECH_STATUS: NOT_TRIED\nHTTP_STATUS:200",
        stderr="Connected to public.localhost",
    ) == "ech_not_attempted"


def test_known_incompatible_ech_config_is_classified_as_server_retry_event():
    assert predict(
        "incompatible_well_formed_ech_config",
        "real",
        101,
        stderr=(
            "Connected to public.localhost\n"
            "ECH: rejected\nECH: retry_configs AQID"
        ),
    ) == "server_rejected_ech_retry"


def test_certificate_verification_error_with_ech_disabled_is_independent_tls_failure():
    assert predict(
        "certificate_verification_failure_no_ech",
        "none",
        60,
        stderr=(
            "Connected to wrong.localhost\\n"
            "curl: (60) SSL certificate problem: no alternative certificate subject name"
        ),
        evidence=["certificate_verification_failed=true"],
    ) == "ech_independent_tls_failure"


def test_loopback_tcp_refusal_is_tcp_failure():
    assert predict(
        "tcp_connection_refusal_loopback",
        "none",
        7,
        stderr="curl: (7) Failed to connect: Connection refused",
    ) == "tcp_failure"


def test_malformed_ech_input_remains_inconclusive_in_current_schema():
    assert predict(
        "malformed_ech_config",
        "real",
        35,
        stderr="ECH: SSL_ECH_set1_ech_config_list failed",
        evidence=["client_ech_config_parse_error=true"],
    ) == "inconclusive"


def test_incompatible_configs_require_different_preserved_config_hashes():
    result = {
        "returncode": 101,
        "stdout": "",
        "stderr": "ECH: rejected\nECH: retry_configs AQID",
    }
    assert benchmark.verify_incompatible(
        result,
        {"client_sha256": "client", "server_sha256": "server"},
    )[0]
    assert not benchmark.verify_incompatible(
        result,
        {"client_sha256": "same", "server_sha256": "same"},
    )[0]
