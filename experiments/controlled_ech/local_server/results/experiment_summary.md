# Local ECH Controlled Experiment

## Environment
- Client: custom curl 8.23.0-DEV
- TLS implementation: custom OpenSSL build
- Server: OpenSSL s_server on 127.0.0.1:8443
- Transport: local loopback

## Test 1: Valid ECH configuration
- Input: valid ECHConfigList
- Result: ECH succeeded
- Outer SNI: cover.localhost
- Inner SNI: public.localhost
- Certificate verification: passed
- HTTP response: 200 OK
- Log: results/inner_outer_sni_success.log

## Test 2: Truncated ECH configuration
- Input: deliberately truncated ECHConfigList
- Result: client-side ECH configuration setup failed
- Evidence: SSL_ECH_set1_ech_config_list failed; curl exit 35
- Interpretation: invalid client input; not evidence of server rejection or network interference
- Log: results/invalid_ech_config.log

## Scope and limitations
These are controlled local tests establishing a positive ECH handshake and a client-side configuration failure. They do not establish the cause of failures observed on public endpoints, nor do they demonstrate censorship or geographic discrimination.
