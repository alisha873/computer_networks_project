# ECH campaign pipeline and data audit

## Scope and reproducibility

This audit covers the probe and analysis code plus the four dated JSONL campaign files listed below. Source campaign records were read only and are not rewritten. The reproducible analyzer command for these files is:

```sh
PYTHONPATH=src python3 -m ech_study.probe.campaign_summary \
	results/ech_baseline_20261011.jsonl \
	results/ech_hotspot_20261012.jsonl \
	results/ech_wifi_20261013.jsonl \
	results/ech_wifi_google_doh_20261014.jsonl \
	--output /tmp/ech-campaign-audit.json
```

The command refuses to overwrite an existing output or any input file. It performs no network requests. Omit `--output` to print JSON to stdout only.

Implementation references: [ech_curl_probe.py](../src/ech_study/probe/ech_curl_probe.py), [ech_curl_campaign.py](../src/ech_study/probe/ech_curl_campaign.py), [campaign_summary.py](../src/ech_study/probe/campaign_summary.py), [classifier](../src/ech_study/classifier/__init__.py), and [schema.py](../src/ech_study/schema.py).

## How the pipeline assigns outcomes

`run_trial()` records a UTC timestamp immediately before invoking curl. It parses verbose curl output into `ech_status` (`succeeded`, `not_attempted`, `failed`, or `unknown`), separately parses HTTP status and curl return code, and separately stores boolean `ech_rejection_observed` and `ech_retry_config_received` markers. The raw record does not contain an `ech_accepted` field.

The raw `outcome` decision is ordered: nonzero curl exit becomes `connection_error`; otherwise a status other than HTTP 200 becomes `http_error`; otherwise ECH mode `true` plus curl-reported `ech_status=succeeded` becomes `ech_success`; ECH mode `false` plus `ech_status=not_attempted` becomes `control_success`; all other cases are `inconclusive`. Thus HTTP success alone does not yield `ech_success`, and an HTTP result, curl return code, curl ECH status, rejection marker, and retry-config marker remain distinct fields.

The `classify_curl_record()` adapter derives `ech_accepted=True` only when requested mode is `true`, curl status says `succeeded`, and trace SNI is `encrypted`; this is a derived adapter field, not an independent raw field in these four datasets. The classifier only treats explicit affirmative evidence as retry/rejection evidence and does not classify censorship. Its labels are not the same thing as the probe's raw `outcome` field.

## Dataset inventory

Each file contains 60 records and 30 pairs (one `true` and one `false` mode per pair). Pair IDs, destination IDs, endpoint, resolver, network and pair position agree within each pair. There are no missing pair modes, duplicate mode trials, duplicate pair positions, mismatched pair metadata, missing audited fields, invalid timestamps, or repeated timestamps in these files. Each file has 30 position-1 and 30 position-2 records.

| File | Records / pairs | Raw outcomes | Network label | Resolver | Record timestamp UTC range |
|---|---:|---|---|---|---|
| `ech_baseline_20261011.jsonl` | 60 / 30 | 30 control_success, 20 ech_success, 10 connection_error | current_connection (60) | https://one.one.one.one/dns-query (60) | 2026-10-10 22:11:07.561103–22:13:09.718112 |
| `ech_hotspot_20261012.jsonl` | 60 / 30 | 30 control_success, 20 ech_success, 10 connection_error | current_connection (60) | https://one.one.one.one/dns-query (60) | 2026-10-10 22:17:19.490554–22:19:13.391729 |
| `ech_wifi_20261013.jsonl` | 60 / 30 | 30 control_success, 20 ech_success, 10 connection_error | current_connection (60) | https://one.one.one.one/dns-query (60) | 2026-10-10 22:24:15.832060–22:25:45.899669 |
| `ech_wifi_google_doh_20261014.jsonl` | 60 / 30 | 30 control_success, 20 ech_success, 10 connection_error | wifi_google_doh (60) | https://dns.google/dns-query (60) | 2026-10-10 22:28:45.302509–22:30:27.313641 |

All four files have 30 `requested_mode=true` and 30 `requested_mode=false` records. In each file, the ECH-mode outcomes are 20 `ech_success` and 10 `connection_error`; all 30 control-mode outcomes are `control_success`. `ech_status` counts are 20 `succeeded`, 30 `not_attempted`, and 10 `unknown`. The 10 `connection_error` records per file have curl return code 101, HTTP status 0, and both rejection and retry-config flags set true.

Each campaign has 20 records for each of these endpoints:

| Endpoint | Control mode | ECH mode |
|---|---|---|
| https://crypto.cloudflare.com/cdn-cgi/trace | 10 control_success | 10 ech_success |
| https://defo.ie/ech-check.php | 10 control_success | 10 connection_error |
| https://tls-ech.dev/ | 10 control_success | 10 ech_success |

Therefore per campaign there are 20 pairs with both recorded successes and 10 pairs with a control success alongside an ECH-mode `connection_error`. These latter pairs remain unresolved for pair-level success/failure comparison: a curl connection error is not treated as a confirmed protocol failure. It is not evidence of censorship.

The 10 `defo.ie` failure excerpts per campaign include `ECH required`, `ECH: rejected`, and `retry_configs` log text; matching boolean markers are present in the JSON records. The stored `ech_status` is nevertheless `unknown` for these records, because the probe's status extraction does not map the rejection line to `failed`. This is a measurable parser/representation distinction; it should not be silently repaired in historical files. The log indicates rejection and retry configuration were observed, not that ECH was accepted.

## Time and network metadata limitations

Filename dates are October 11–14, but every record timestamp is October 10, 2026 UTC. Code inspection shows the record timestamp is generated with `datetime.now(timezone.utc).isoformat()` before each curl invocation; campaign ID is generated once at campaign start. Filenames are not used to set timestamps. The source establishes the stored UTC time and the mismatch, but not why the filename date differs; no historical timestamp or filename was corrected.

Three datasets store `network=current_connection`. That string does not identify Wi-Fi, hotspot, carrier, or another access type. The file names and researcher recollection are not sufficient to assign those labels to specific campaigns or trials. The fourth dataset stores `wifi_google_doh`, which is a recorded label rather than independent verification of the device's actual network. The data cannot establish which access network was active in the first three campaigns.

## Interpretation and limitations

The repeated endpoint-specific pattern is descriptive: successful records at two endpoints and the ECH-mode connection errors at `defo.ie/ech-check.php`, with rejection/retry markers in the logs. It does not show why the server rejected the exchange, establish a network intermediary, or demonstrate censorship. All four runs share the same timestamp date and broad metadata pattern, so they should not be treated as four independently verified access-network conditions. The audit code preserves the raw outcome categories and emits warnings rather than correcting records or filling unknown values.

Recommended next steps:

1. Preserve and independently document access-network state for each pair (user/device-observed label, connection type, carrier/SSID where ethically appropriate, and time of transition), instead of relying on `current_connection`.
2. Record an explicit campaign manifest with intended campaign date, operator-provided network label, resolver configuration, curl build/version, and command parameters; do not derive historical values from filenames.
3. Refine a future parser with fixtures from captured curl logs so `ech_status`, rejection observation, retry-config receipt, curl exit, and HTTP status remain separate and tested. Keep old JSONL unchanged; make any reprocessing a versioned derived artifact.
4. Repeat paired trials across documented networks and resolvers with adequate time separation and control endpoints, then investigate endpoint behavior and alternative explanations before making causal claims.

## Follow-up experiment: ECH configuration mismatch at defo.ie

**Date:** 11 October 2026  
**Client:** Custom curl 8.23.0-DEV, OpenSSL 4.0.0  
**Endpoint:** `https://defo.ie/ech-check.php`

### Observations

1. ECH using the HTTPS record discovered through curl failed with `ECH required` and curl exit code 101.
2. The ECHConfigList retrieved from the HTTPS record was supplied explicitly using `--ech ecl:<base64>`. This also failed with `ECH required`.
3. The server returned a different ECH retry configuration in its TLS response.
4. Supplying that retry configuration explicitly succeeded twice. Both requests returned HTTP 200, and the server reported `SSL_ECH_STATUS: SUCCESS`.
5. In a subsequent test, the previously successful retry configuration was rejected with `ECH required`. The server returned a different retry configuration, which was then supplied explicitly and succeeded, returning HTTP 200 with `SSL_ECH_STATUS: SUCCESS`.

### Additional interpretation

The successful use of a newly returned retry configuration, following rejection of an older one, is consistent with configuration freshness or rotation affecting the outcome. However, the observations do not establish why the configuration changed or whether the DNS-published configuration was stale, inconsistent, or otherwise incompatible.

5. Cloudflare DNS (`1.1.1.1`) and Google DNS (`8.8.8.8`) returned identical 165-byte HTTPS records.

### Preliminary interpretation

The results demonstrate a reproducible difference between the DNS-published ECH configuration and the configuration returned by the server during the tested connections. The server-returned configuration was accepted successfully.

The underlying cause remains undetermined. Possible explanations include inconsistent server configuration or DNS publication/cache behavior. These observations do not establish DNS tampering, censorship, or India-specific interference.

### Limitations

- One endpoint and one client environment were tested.
- The two DNS resolvers may share upstream authoritative data.
- The tests do not identify the root cause of the configuration mismatch.
- The diagnostic procedure has not yet been validated against controlled faults with known ground truth.

### Next research question

Can a diagnostic procedure distinguish configuration mismatch, DNS-path alteration, and other causes of paired ECH/control failures more accurately than a simple baseline rule?