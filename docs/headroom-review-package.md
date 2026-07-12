# Headroom Integration Review Package

## Review status and scope

This package presents the Hermes/Atlas Headroom integration for review after a Headroom-specific Gate 3 PASS. It does not authorize deployment or production enablement. Headroom remains a replaceable preprocessing adapter; Atlas remains the sole provider/model routing authority.

Branch: `feature/headroom-integration-v1`

Live configuration baseline SHA-256: `61f70f21f26bdd210981961f5c80b06c5bb317bbeac767c12cb5ed2d5908e806`

Effective live Headroom state: `enabled=false`, `mode=off`.

## Architecture

The integration adds one narrow adapter at the verified Hermes middleware boundary after routing and request assembly and before provider transport. `hermes_cli/headroom_adapter.py` owns deterministic classification, subprocess invocation, validation, fail-open selection, and redacted metrics. `agent/conversation_loop.py` calls the adapter once without changing routing or fallback policy. `hermes_cli/config.py` exposes the existing configuration block, and `agent/agent_init.py` loads it into the runtime.

Supported controls:

- `off`: passes the original provider request unchanged.
- `observe`: computes a candidate and metrics while sending the original request.
- `active`: code path exists but is not enabled in production.
- Per-request bypass overrides observe or active behavior.

The adapter launches the isolated Headroom environment as a bounded subprocess and invokes the installed `headroom-ai==0.25.0` `LogCompressor.compress()` API. It does not require a proxy, provider keys, a second router, global monkey-patching, or mutation of canonical request objects.

## Safety boundaries

- Classification is deterministic and defaults uncertain content to `unknown` and preservation.
- Protected and unknown segments remain unchanged. Protected categories include system/developer instructions, explicit user constraints, routing/budget/governance policy, Registry canonical content, security constraints, credentials/secrets, and recent diagnostic evidence.
- Only explicitly eligible tool/command output, retrieved documents, repetitive history, and large logs may be compressed.
- Secret-pattern detection prevents detected credentials from reaching Headroom or metrics.
- The latest relevant error, stack trace, failed-test output, or failed-command evidence is protected.
- Candidate output must be non-empty, structurally valid, retain required/protected markers, preserve segment coverage, finish before timeout, fit provider format, and meet the configured savings threshold.
- Exceptions, timeouts, invalid/empty output, marker mismatch, or insufficient savings select the original context and do not trigger provider fallback.
- Provider, model, and fallback fields remain outside Headroom decision authority and are preserved.
- `HEADROOM_TELEMETRY=off` and `HEADROOM_TELEMETRY_WARN=off` are enforced for subprocess execution; package telemetry was directly verified disabled.
- Headroom metrics contain structured counts, hashes, decisions, error types, and durations, not raw prompt/context bodies. Diagnostic raw-content logging defaults off.

Known limitation: existing Hermes conversation logging in `agent/turn_context.py:264-266` may emit raw synthetic prompt text through the pre-existing `conversation turn ... msg=%r` record. This is outside the Headroom metrics boundary and is not a Headroom metrics leak. No change to that behavior is included here.

## Validation evidence

- Gate 2: implementation and targeted automated validation passed; configuration defaults remained off, protected-content and fail-open behavior were verified, and routing/fallback behavior remained unchanged.
- Gate 2R: the installed real package was exercised through the isolated subprocess adapter with telemetry disabled; evidence is in `docs/headroom-gate2r-evidence.md`.
- Gate 3: Headroom-specific PASS. Observe mode retained the original provider payload and production remained off.
- Gate 3R: mocked-transport observe integration evidence was captured in `docs/headroom-gate3r-evidence.md`.
- Gate 3R2: recursive Codex Responses normalization mechanically proved adapter input, adapter output, and final mocked transport payload equality. Both normalized hashes were `b05345d5022c47f7951a92a7ce4849dfdbac09a8dddb579048dbbe846f1c03cd`; one test passed in 3.55 seconds; no provider API was contacted.
- Gate 3R3: classified the raw synthetic prompt record as existing Hermes logging outside Headroom and verified Headroom metrics contained no raw prompt/context.
- Gate 3R4: removed only the authorized temporary Gate 3R/Gate 3R2 test files and matching bytecode. No matching temp artifacts remain. Live config checksum still matched the baseline.
- Gate 5R3: PASS. A request-wide deadline now bounds all eligible segment compression, post-transport metrics record success/failure and retry use of original context, compilation passed, adapter tests reported 34 passed in 0.64 seconds, config/fallback/parity tests reported 137 passed in 14.93 seconds, and `git diff --check` passed. Live config remained OFF with SHA-256 `61f70f21f26bdd210981961f5c80b06c5bb317bbeac767c12cb5ed2d5908e806`.
- Gate 5R4: PASS. Three mocked conversation-loop lifecycle tests passed in 3.77 seconds, covering successful transport, exceptional transport, retry/original-context reporting, raw-content exclusion, and routing-field preservation. Compilation passed; the adapter suite reported 34 passed in 0.60 seconds; config/fallback/parity tests reported 137 passed in 14.81 seconds; and `git diff --check` passed. No provider API was contacted.

Evidence documents:

- `docs/headroom-integration-design.md`
- `docs/headroom-gate2r-evidence.md`
- `docs/headroom-gate3-evidence.md`
- `docs/headroom-gate3r-evidence.md`
- `docs/headroom-operations.md`
- `docs/headroom-rollback.md`

Gate 4 local review commands:

```text
venv/bin/python -m py_compile agent/agent_init.py agent/conversation_loop.py hermes_cli/config.py hermes_cli/headroom_adapter.py
venv/bin/python -m pytest -q tests/hermes_cli/test_headroom_adapter.py
venv/bin/python -m pytest -q tests/hermes_cli/test_config_validation.py tests/run_agent/test_provider_fallback.py tests/run_agent/test_provider_parity.py
git diff --check
```

Observed results:

- `py_compile`: PASS for all four changed Python files.
- Headroom adapter suite after Gate 5R3: 34 passed in 0.64 seconds.
- Config/routing/fallback selections after Gate 5R3: 137 passed in 14.93 seconds.
- `git diff --check`: PASS.

## Changed-file inventory and deployment candidate

Tracked modified runtime/config files:

- `agent/agent_init.py`
- `agent/conversation_loop.py`
- `hermes_cli/config.py`

Untracked adapter and test files:

- `hermes_cli/headroom_adapter.py`
- `tests/hermes_cli/test_headroom_adapter.py`

Untracked documentation:

- `docs/headroom-gate2r-evidence.md`
- `docs/headroom-gate3-evidence.md`
- `docs/headroom-gate3r-evidence.md`
- `docs/headroom-integration-design.md`
- `docs/headroom-operations.md`
- `docs/headroom-rollback.md`
- `docs/headroom-review-package.md`

These files form the deployment candidate only after separate approval. Evidence-only gate documents may be retained for audit but do not require runtime deployment. No live configuration file is part of this candidate, and no deployment is performed by this package.

## Rollback checklist

Follow `docs/headroom-rollback.md` exactly:

- Set effective Headroom state to `enabled=false`, `mode=off`.
- Verify telemetry controls remain off.
- Restore the timestamped pre-change configuration if configuration was changed, then verify its checksum.
- Revert the isolated integration change or remove the adapter hook/files through Git.
- Restart only the required Hermes service when separately authorized.
- Verify the original provider request path and unchanged provider/model/fallback behavior.
- Verify Atlas operates normally without Headroom.

Current rollback posture is immediate configuration bypass through the default OFF state. Active production compression has never been enabled.

## Review disposition

The integration is ready for code and governance review. Any deployment, persistent configuration change, observe-mode continuation, or active-mode canary requires a separate explicit authorization.
