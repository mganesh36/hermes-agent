# Headroom Operations

## Modes and configuration

Configuration uses the existing Hermes YAML under the top-level `headroom` key. Defaults are `enabled: false`, `mode: off`, telemetry disabled, fail-open enabled, 4000 minimum input tokens, 10% minimum savings and 5000 ms timeout.

- `off`: bypass; original request.
- `observe`: candidate and metrics; original request.
- `active`: eligible candidate may be sent. Implemented only; do not enable in production in this mission.
- Per-request bypass: set request metadata `headroom_bypass: true`.

Any natural-language request to change policy must be confirmed before config persistence. No natural-language persistence path was added in Gate 2.

## Status and metrics

Inspect loaded config and structured `headroom_metrics` events. Metrics expose no request bodies. Savings are estimates, not billing claims. Explain bypass using `bypass_reason`, including `mode_off`, `request_bypass`, `below_minimum_tokens`, `no_eligible_content`, `telemetry_forbidden`, `timeout`, `compression_error`, or `insufficient_savings`.

Telemetry is forced off for every Headroom subprocess with `HEADROOM_TELEMETRY=off`. Raw-content logging is hard-disabled.

## Troubleshooting

Headroom errors are non-fatal. Verify the dedicated environment, `headroom-ai` version, telemetry-off check, subprocess timeout, classification metadata and savings threshold. Do not change provider routing or fallback to correct a Headroom failure.

Known limitation: version 0.25.0's local `LogCompressor` is used for eligible line-oriented tool/command/log content. Other content remains preserved unless deterministically classified and supported later.
