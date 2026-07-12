# Headroom Integration Design

## Gate 2 pre-checks

- Runtime: CT106 `Atlas`, Hermes commit `7426c09beee73bdff94d916015bac71384f6bc92`, Python 3.11.15.
- Hook: a synthetic full-conversation test reached mocked provider transport (`1 passed`). Source ordering proves `api_kwargs`, provider, model and API mode are fixed before `apply_llm_request_middleware()` at `agent/conversation_loop.py:1170`; transport begins later through `run_llm_execution_middleware()` and `_perform_api_call()`.
- Serialization: the hook receives provider-shaped dictionaries with separable `messages` or `input`; no irreversible byte serialization has occurred.
- Package: `headroom-ai==0.25.0`, Python 3.11.15, both virtual environments pass `pip check`.
- API: synchronous `headroom.transforms.log_compressor.LogCompressor.compress(content)` returning `LogCompressionResult`; adapter invokes it in the isolated Headroom environment with a 5-second subprocess timeout.
- Exceptions: timeout, nonzero exit, invalid JSON, empty output, invalid structure and insufficient savings all return the original request.
- Telemetry: package default is enabled. The adapter always sets `HEADROOM_TELEMETRY=off` and `HEADROOM_TELEMETRY_WARN=off`; direct verification returned `False` from `is_telemetry_enabled()`.
- Feasibility: no proxy, provider keys, router, global patching or request-object mutation is required.

## Design

`hermes_cli/headroom_adapter.py` is the sole integration boundary. It deep-copies requests, classifies each segment as protected, eligible or unknown, sends only eligible string content to the isolated compressor, validates the candidate, and returns either the candidate or the original.

System, developer and user roles are protected. Explicit policy, governance, security, Registry, secret and recent-error classifications are protected. Unknown segments are preserved. Tool segments or explicitly eligible content types may be optimized. The most recent error-like segment is protected.

Modes are `off`, `observe`, and `active`. Off and observe send the original. Active exists in code but remains disabled by default. `headroom_bypass` overrides all modes and is removed before provider transport.

Metrics contain identifiers, mode, token estimates, counts, savings, bypass/error state, latency and policy version. They contain no raw content.

The adapter does not inspect or modify routing or fallback selection. Failures are caught before provider transport and cannot trigger fallback by themselves.
