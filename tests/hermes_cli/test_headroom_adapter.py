import logging
from hermes_cli.headroom_adapter import complete_metrics
import json
import logging
import subprocess

import pytest

from hermes_cli.headroom_adapter import (
    Classification, HeadroomPolicy, Mode, apply_to_request, classify_segment,
    metrics_event, optimize_context, policy_from_mapping,
)


SYNTHETIC = {"synthetic": True}


def msg(role, content, kind=None):
    value = {"role": role, "content": content, **SYNTHETIC}
    if kind:
        value["content_type"] = kind
    return value


def request(*messages):
    return {"model": "synthetic-model", "messages": list(messages), **SYNTHETIC}


def policy(mode=Mode.ACTIVE, **kwargs):
    kwargs.setdefault("minimum_expected_savings_percent", 1)
    return HeadroomPolicy(enabled=True, mode=mode, minimum_input_tokens=0, **kwargs)


def compress(text, timeout):
    return "compressed synthetic output"


@pytest.mark.parametrize("kind", [
    "system_instructions", "developer_instructions", "routing_policy",
    "budget_policy", "governance_policy", "security_constraints",
    "registry_canonical_content", "user_explicit_constraints",
])
def test_protected_kinds_are_byte_identical(kind):
    protected = msg("assistant", f"{kind} exact synthetic text", kind)
    eligible = msg("tool", "repeat " * 200, "large_logs")
    original = request(protected, eligible)
    result = optimize_context(original, policy(), compressor=compress)
    assert result.optimized_context["messages"][0] == original["messages"][0]


def test_off_mode_sends_original_unchanged():
    original = request(msg("tool", "repeat " * 200, "large_logs"))
    result = optimize_context(original, HeadroomPolicy())
    assert result.original_context_used and result.optimized_context == original


def test_observe_records_candidate_but_sends_original():
    original = request(msg("tool", "repeat " * 200, "large_logs"))
    result = optimize_context(original, policy(Mode.OBSERVE), compressor=compress)
    assert result.original_context_used
    assert result.optimized_context != original


def test_active_optimizes_only_eligible_tool_output():
    system = msg("system", "exact synthetic system")
    tool = msg("tool", "repeat " * 200, "tool_output")
    result = optimize_context(request(system, tool), policy(), compressor=compress)
    assert not result.original_context_used
    assert result.optimized_context["messages"][0] == system
    assert result.optimized_context["messages"][1]["content"] == "compressed synthetic output"


def test_request_bypass_overrides_active():
    original = request(msg("tool", "repeat " * 200, "tool_output"))
    result = optimize_context(original, policy(), bypass=True, compressor=compress)
    assert result.original_context_used and result.bypass_reason == "request_bypass"


def test_system_developer_and_user_roles_are_protected():
    for role in ("system", "developer", "user"):
        assert classify_segment(msg(role, "exact synthetic")) is Classification.PROTECTED


def test_unknown_is_preserved():
    unknown = msg("assistant", "unknown synthetic content")
    eligible = msg("tool", "repeat " * 200, "tool_output")
    result = optimize_context(request(unknown, eligible), policy(), compressor=compress)
    assert result.optimized_context["messages"][0] == unknown
    assert result.unknown_segments_count == 1


@pytest.mark.parametrize("secret", [
    "api_key=synthetic-secret-value", "Bearer syntheticTokenValue12345",
    "-----BEGIN PRIVATE KEY----- synthetic",
])
def test_secrets_are_excluded_and_absent_from_metrics(caplog, secret):
    original = request(msg("tool", secret, "tool_output"))
    with caplog.at_level(logging.INFO):
        payload, result = apply_to_request(original, {"headroom": {
            "enabled": True, "mode": "active", "minimum_input_tokens": 0,
        }})
    assert payload == original
    assert result.protected_segments_count == 1
    assert secret not in json.dumps(result.metrics)
    assert secret not in caplog.text


def test_latest_debugging_context_is_preserved():
    old = msg("tool", "Error: old synthetic failure\n" + "x\n" * 100, "large_logs")
    latest = msg("tool", "Traceback: latest synthetic failure", "large_logs")
    result = optimize_context(request(old, latest), policy(), compressor=compress)
    assert result.optimized_context["messages"][1] == latest


def test_exception_fails_open():
    def broken(text, timeout): raise RuntimeError("synthetic")
    original = request(msg("tool", "repeat " * 200, "large_logs"))
    result = optimize_context(original, policy(), compressor=broken)
    assert result.original_context_used and result.error == "RuntimeError"


def test_timeout_fails_open():
    def timed_out(text, timeout): raise subprocess.TimeoutExpired("synthetic", 1)
    original = request(msg("tool", "repeat " * 200, "large_logs"))
    result = optimize_context(original, policy(), compressor=timed_out)
    assert result.original_context_used and result.error == "TimeoutExpired"


def test_empty_output_fails_open():
    original = request(msg("tool", "repeat " * 200, "large_logs"))
    result = optimize_context(original, policy(), compressor=lambda *_: "")
    assert result.original_context_used and result.error == "ValueError"


def test_insufficient_savings_fails_open():
    original = request(msg("tool", "synthetic compact", "large_logs"))
    result = optimize_context(original, policy(minimum_expected_savings_percent=99), compressor=lambda text, _: text)
    assert result.original_context_used and result.bypass_reason == "insufficient_savings"


def test_unsupported_structure_fails_open():
    original = {"model": "synthetic", **SYNTHETIC}
    result = optimize_context(original, policy(), compressor=compress)
    assert result.original_context_used and result.bypass_reason == "unsupported_structure"


def test_metrics_have_no_prompt_body():
    body = "private synthetic prompt body"
    result = optimize_context(request(msg("tool", body * 100, "large_logs")), policy(), compressor=compress)
    serialized = json.dumps(result.metrics)
    assert body not in serialized and "messages" not in serialized


def test_telemetry_cannot_be_enabled():
    original = request(msg("tool", "repeat " * 200, "large_logs"))
    unsafe = HeadroomPolicy(enabled=True, mode=Mode.ACTIVE, telemetry_enabled=True, minimum_input_tokens=0)
    result = optimize_context(original, unsafe, compressor=compress)
    assert result.original_context_used and result.bypass_reason == "telemetry_forbidden"


def test_default_configuration_is_off():
    configured = policy_from_mapping({})
    assert configured.mode is Mode.OFF and configured.enabled is False


def test_unconfirmed_natural_language_cannot_enable_active():
    configured = policy_from_mapping({"command": "enable active headroom"})
    assert configured.mode is Mode.OFF and configured.enabled is False


def test_apply_does_not_mutate_original_or_route():
    original = request(msg("tool", "repeat " * 200, "large_logs"))
    original["provider"] = "synthetic-provider"
    snapshot = json.loads(json.dumps(original))
    payload, _ = apply_to_request(original, {"headroom": {"enabled": False, "mode": "off"}})
    assert original == snapshot
    assert payload["provider"] == "synthetic-provider"


def test_failure_does_not_change_provider_or_fallback_fields(monkeypatch):
    original = request(msg("tool", "repeat " * 200, "large_logs"))
    original.update(provider="synthetic-provider", fallback_providers=["synthetic-fallback"])
    monkeypatch.setattr("hermes_cli.headroom_adapter._headroom_compress", lambda *_: (_ for _ in ()).throw(RuntimeError()))
    payload, result = apply_to_request(original, {"headroom": {
        "enabled": True, "mode": "active", "minimum_input_tokens": 0,
    }})
    assert result.original_context_used
    assert payload["provider"] == original["provider"]
    assert payload["fallback_providers"] == original["fallback_providers"]


def test_per_request_bypass_marker_is_not_forwarded():
    original = request(msg("tool", "repeat " * 200, "large_logs"))
    original["headroom_bypass"] = True
    payload, result = apply_to_request(original, {"headroom": {"enabled": True, "mode": "active"}})
    assert result.bypass_reason == "request_bypass"
    assert "headroom_bypass" not in payload


def test_multi_segment_timeout_is_one_request_budget(monkeypatch):
    original = request(
        msg("tool", "first " * 200, "large_logs"),
        msg("tool", "second " * 200, "large_logs"),
    )
    moments = iter([10.0, 10.002, 10.006, 10.006])
    monkeypatch.setattr("hermes_cli.headroom_adapter.time.monotonic", lambda: next(moments))
    seen_timeouts = []

    def slow_compress(_text, timeout_ms):
        seen_timeouts.append(timeout_ms)
        return "compressed synthetic output"

    result = optimize_context(original, policy(timeout_ms=5), compressor=slow_compress)
    assert result.original_context_used is True
    assert result.bypass_reason == "timeout"
    assert seen_timeouts == [3]


@pytest.mark.parametrize("succeeded", [True, False])
def test_provider_outcome_completes_metrics_without_raw_content(succeeded, caplog):
    original = request(msg("tool", "synthetic private body " * 200, "large_logs"))
    result = optimize_context(original, policy(mode=Mode.OBSERVE), compressor=compress)
    with caplog.at_level(logging.INFO, logger="hermes.headroom"):
        completed = complete_metrics(result, request_succeeded=succeeded)
    assert completed["request_succeeded"] is succeeded
    assert completed["retry_used_original_context"] is False
    assert "synthetic private body" not in caplog.text


def test_retry_fail_open_records_original_context_without_raw_content(caplog):
    original = request(msg("tool", "synthetic retry body " * 200, "large_logs"))

    def fail(_text, _timeout):
        raise RuntimeError("synthetic compressor failure")

    result = optimize_context(original, policy(), compressor=fail)
    with caplog.at_level(logging.INFO, logger="hermes.headroom"):
        completed = complete_metrics(
            result,
            request_succeeded=True,
            retry_used_original_context=True,
        )
    assert result.original_context_used is True
    assert completed["retry_used_original_context"] is True
    assert "synthetic retry body" not in caplog.text
