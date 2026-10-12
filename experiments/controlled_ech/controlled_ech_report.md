# Controlled ECH Configuration Experiments

## 1. Objective

Evaluate whether the experiment pipeline distinguishes successful ECH
negotiation, client-side configuration errors, server-observed ECH
rejection with retry configuration, and ordinary HTTPS without ECH.

These experiments use a live endpoint and controlled client inputs. They
are a preliminary diagnostic experiment, not a validated benchmark of
all possible ECH failure causes.

## 2. Experimental setup

- Client: custom curl 8.23.0-DEV build.
- TLS backend: OpenSSL 4.0.0.
- Destination for the defo.ie cases:
  https://defo.ie/ech-check.php
- Evidence: verbose curl logs, curl exit codes, HTTP status, ECH markers,
  retry-configuration markers, and server-reported ECH status where present.
- Processing: classify_logs.py generates classified_results.csv.
- Validation: regression assertions check all eight expected classifications
  and status codes.

## 3. Cases and observed results

| Case | Input or condition | Observed result | Interpretation |
|---|---|---|---|
| valid_ech_baseline | Known-good retry ECH configuration | ECH success; HTTP 200 | Successful ECH baseline |
| alternate_outer_name | ECH attempted with alternate outer name | ECH success; HTTP 200 | An alternate outer name alone did not cause failure |
| malformed_config | Syntactically invalid ECH configuration input | Client setup error; curl 35; HTTP 000 | Client-side configuration parsing/setup failure |
| ordinary_https_control | Ordinary HTTPS without ECH | HTTP 200; ECH not attempted | Non-ECH control succeeds |
| dns_published_config | Previously observed DNS-published configuration | ECH rejection; curl 101; HTTP 000; retry configuration received | Server-observed rejection with retry evidence |
| fresh_retry_config | Retry configuration supplied by defo.ie | ECH success; HTTP 200 | Retry configuration succeeds in this test |
| cross_server_config | Configuration obtained from cloudflare-ech.com used with defo.ie | ECH rejection; curl 101; HTTP 000; retry configuration received | Configuration from another endpoint was rejected by the destination |
| cross_server_retry | Retry configuration returned by defo.ie in the preceding test | ECH success; HTTP 200 | Destination-provided retry configuration succeeds |

The complete machine-generated results are in `classified_results.csv`.
The corresponding raw observations are retained in the individual `.log` files.

## 4. Main findings

1. The classifier distinguishes a client-side malformed-configuration error
   from an ECH rejection observed during communication with the server.
2. Both tested rejection cases recorded retry-configuration evidence and
   returned curl exit code 101 with HTTP status 000.
3. The retry configurations used in the corresponding follow-up tests
   succeeded with HTTP 200 and ECH success markers.
4. The cross-server test demonstrates that an ECH configuration obtained
   from one endpoint is not necessarily accepted by another endpoint.
5. The alternate-outer-name case succeeded, so that test must not be
   reported as an ECH failure.

## 5. Regression validation

All eight cases matched their expected classifications, curl exit codes,
and HTTP status codes. Both rejection cases were also verified to have
recorded retry-configuration evidence.

This validates the current test fixtures and classifier expectations.
It does not establish sensitivity, specificity, or general diagnostic
accuracy across a broad set of independently verified failure conditions.

## 6. Limitations

- These tests use live services, not a fully isolated local test server
  with independently controlled server keys and configurations.
- Server configuration and DNS records can change over time.
- A configuration rejected by a destination does not, by itself, identify
  the root cause of the rejection.
- A retry configuration succeeding afterward supports a configuration-
  dependent explanation, but does not prove why the original configuration
  was rejected.
- These experiments do not establish censorship, DNS tampering, geographic
  discrimination, or India-specific interference.
- The alternate-outer-name case tests only the particular configuration and
  endpoint used here.
- The classifier has been regression-tested against these eight fixtures;
  broader validation against independently generated, ground-truth cases
  remains necessary.

## 7. Next experiment

Construct a reproducible local test environment with a controlled ECH
server and known-good server configuration. Generate independently labelled
cases for valid configuration, stale or mismatched configuration,
malformed client input, ordinary HTTPS without ECH, and retry-config
recovery. Record the expected outcome before running the classifier.

This would allow the classifier to be evaluated against known ground truth,
rather than relying exclusively on observations from a live endpoint.
