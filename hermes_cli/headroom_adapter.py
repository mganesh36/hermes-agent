"""Fail-open Headroom preprocessing for provider request payloads.

Headroom is deliberately isolated behind this module.  It never selects a
provider, changes fallback policy, or writes optimized content to memory.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping


LOGGER = logging.getLogger("hermes.headroom")
POLICY_VERSION = "headroom-v1"
HEADROOM_PYTHON = "/home/hermes/services/headroom/venv/bin/python"


class Mode(str, Enum):
    OFF = "off"
    OBSERVE = "observe"
    ACTIVE = "active"


class Classification(str, Enum):
    PROTECTED = "protected"
    ELIGIBLE = "eligible"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HeadroomPolicy:
    enabled: bool = False
    mode: Mode = Mode.OFF
    telemetry_enabled: bool = False
    fail_open: bool = True
    minimum_input_tokens: int = 4000
    minimum_expected_savings_percent: float = 10.0
    timeout_ms: int = 5000
    preserve_original_hash: bool = True
    record_metrics: bool = True
    raw_content_logging: bool = False
    policy_version: str = POLICY_VERSION


@dataclass
class OptimizationResult:
    original_context: Any
    optimized_context: Any
    original_token_estimate: int
    optimized_token_estimate: int
    estimated_tokens_saved: int
    estimated_savings_percent: float
    protected_segments_count: int
    eligible_segments_count: int
    optimized_segments_count: int
    unknown_segments_count: int
    bypassed: bool
    bypass_reason: str | None
    error: str | None
    compression_duration_ms: float
    original_content_hash: str
    optimized_content_hash: str
    policy_version: str
    original_context_used: bool = True
    metrics: dict[str, Any] = field(default_factory=dict)


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|secret|password|private[_-]?key)\b\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*"),
)
_ERROR_MARKERS = ("traceback", "exception", "error:", "failed", "failure", "stack trace")
_PROTECTED_KINDS = {
    "system_instructions", "developer_instructions", "routing_policy",
    "budget_policy", "governance_policy", "registry_canonical_content",
    "security_constraints", "user_explicit_constraints", "credentials",
    "secrets", "recent_error_context",
}
_ELIGIBLE_KINDS = {
    "tool_output", "command_output", "retrieved_documents",
    "repetitive_conversation_history", "large_logs",
}


def policy_from_mapping(value: Mapping[str, Any] | None) -> HeadroomPolicy:
    data = dict(value or {})
    mode_value = str(data.get("mode", "off")).lower()
    try:
        mode = Mode(mode_value)
    except ValueError:
        mode = Mode.OFF
    return HeadroomPolicy(
        enabled=bool(data.get("enabled", False)),
        mode=mode,
        telemetry_enabled=bool(data.get("telemetry_enabled", False)),
        fail_open=True,
        minimum_input_tokens=max(0, int(data.get("minimum_input_tokens", 4000))),
        minimum_expected_savings_percent=max(0.0, float(data.get("minimum_expected_savings_percent", 10))),
        timeout_ms=max(1, int(data.get("timeout_ms", 5000))),
        preserve_original_hash=bool(data.get("preserve_original_hash", True)),
        record_metrics=bool(data.get("record_metrics", True)),
        raw_content_logging=False,
        policy_version=str(data.get("policy_version", POLICY_VERSION)),
    )


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _content_text(segment: Mapping[str, Any]) -> str | None:
    content = segment.get("content")
    return content if isinstance(content, str) else None


def classify_segment(segment: Mapping[str, Any], *, latest_error: bool = False) -> Classification:
    text = _content_text(segment) or ""
    kind = str(segment.get("headroom_classification") or segment.get("content_type") or "").lower()
    role = str(segment.get("role") or "").lower()
    if role in {"system", "developer", "user"} or kind in _PROTECTED_KINDS:
        return Classification.PROTECTED
    if contains_secret(text):
        return Classification.PROTECTED
    if latest_error and any(marker in text.lower() for marker in _ERROR_MARKERS):
        return Classification.PROTECTED
    if kind in _ELIGIBLE_KINDS or role == "tool":
        return Classification.ELIGIBLE
    return Classification.UNKNOWN


def _estimate_tokens(value: Any) -> int:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return max(1, (len(encoded) + 3) // 4)


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _headroom_compress(text: str, timeout_ms: int) -> str:
    worker = (
        "import json,sys;"
        "from headroom.transforms.log_compressor import LogCompressor;"
        "x=json.load(sys.stdin);"
        "r=LogCompressor().compress(x['content']);"
        "json.dump({'content':r.compressed},sys.stdout)"
    )
    env = os.environ.copy()
    env["HEADROOM_TELEMETRY"] = "off"
    env["HEADROOM_TELEMETRY_WARN"] = "off"
    completed = subprocess.run(
        [HEADROOM_PYTHON, "-c", worker],
        input=json.dumps({"content": text}),
        text=True,
        capture_output=True,
        timeout=timeout_ms / 1000,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"headroom_exit_{completed.returncode}")
    parsed = json.loads(completed.stdout)
    return parsed["content"]


def _find_latest_error_index(messages: list[Mapping[str, Any]]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        text = _content_text(messages[index]) or ""
        if any(marker in text.lower() for marker in _ERROR_MARKERS):
            return index
    return None


def optimize_context(
    request_context: Mapping[str, Any],
    policy: HeadroomPolicy,
    *,
    bypass: bool = False,
    compressor: Callable[[str, int], str] | None = None,
) -> OptimizationResult:
    started = time.monotonic()
    original = copy.deepcopy(dict(request_context))
    original_hash = _hash(original)
    messages = original.get("messages")
    if not isinstance(messages, list):
        messages = original.get("input")
    if not isinstance(messages, list):
        return _result(original, original, policy, 0, 0, 0, True, "unsupported_structure", None, started)

    latest_error_index = _find_latest_error_index(messages)
    classifications: list[Classification] = []
    deadline = started + (policy.timeout_ms / 1000.0)
    for index, segment in enumerate(messages):
        if not isinstance(segment, Mapping):
            classifications.append(Classification.UNKNOWN)
        else:
            classifications.append(classify_segment(segment, latest_error=index == latest_error_index))
    protected = classifications.count(Classification.PROTECTED)
    eligible = classifications.count(Classification.ELIGIBLE)
    unknown = classifications.count(Classification.UNKNOWN)

    if bypass:
        return _result(original, original, policy, protected, eligible, unknown, True, "request_bypass", None, started)
    if not policy.enabled or policy.mode is Mode.OFF:
        return _result(original, original, policy, protected, eligible, unknown, True, "mode_off", None, started)
    if policy.telemetry_enabled:
        return _result(original, original, policy, protected, eligible, unknown, True, "telemetry_forbidden", None, started)
    if eligible == 0:
        return _result(original, original, policy, protected, eligible, unknown, True, "no_eligible_content", None, started)
    if _estimate_tokens(original) < policy.minimum_input_tokens:
        return _result(original, original, policy, protected, eligible, unknown, True, "below_minimum_tokens", None, started)

    candidate = copy.deepcopy(original)
    candidate_messages = candidate.get("messages") if isinstance(candidate.get("messages"), list) else candidate.get("input")
    compress = compressor or _headroom_compress
    optimized_count = 0
    try:
        for index, classification in enumerate(classifications):
            if classification is not Classification.ELIGIBLE:
                continue
            segment = candidate_messages[index]
            text = _content_text(segment)
            if not text:
                continue
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                return _result(original, original, policy, protected, eligible, unknown, True, "timeout", "TimeoutExpired", started)
            optimized = compress(text, remaining_ms)
            if not isinstance(optimized, str) or not optimized.strip():
                raise ValueError("empty_optimized_output")
            segment["content"] = optimized
            optimized_count += 1
    except subprocess.TimeoutExpired:
        return _result(original, original, policy, protected, eligible, unknown, True, "timeout", "TimeoutExpired", started)
    except Exception as exc:
        return _result(original, original, policy, protected, eligible, unknown, True, "compression_error", type(exc).__name__, started)

    if not isinstance(candidate_messages, list) or len(candidate_messages) != len(messages):
        return _result(original, original, policy, protected, eligible, unknown, True, "invalid_structure", "StructureMismatch", started)
    for index, classification in enumerate(classifications):
        if classification is not Classification.ELIGIBLE and candidate_messages[index] != messages[index]:
            return _result(original, original, policy, protected, eligible, unknown, True, "protected_mismatch", "ProtectedMismatch", started)
    original_tokens = _estimate_tokens(original)
    optimized_tokens = _estimate_tokens(candidate)
    savings = max(0, original_tokens - optimized_tokens)
    savings_percent = 100.0 * savings / original_tokens
    if optimized_count == 0:
        return _result(original, original, policy, protected, eligible, unknown, True, "nothing_optimized", None, started)
    if optimized_tokens >= original_tokens or savings_percent < policy.minimum_expected_savings_percent:
        return _result(original, original, policy, protected, eligible, unknown, True, "insufficient_savings", None, started)

    use_original = policy.mode is Mode.OBSERVE
    return _result(
        original, candidate, policy, protected, eligible, unknown, use_original,
        "observe_original_used" if use_original else None, None, started,
        optimized_count=optimized_count,
    )


def _result(
    original: Mapping[str, Any],
    optimized: Mapping[str, Any],
    policy: HeadroomPolicy,
    protected: int,
    eligible: int,
    unknown: int,
    original_used: bool,
    bypass_reason: str | None,
    error: str | None,
    started: float,
    *,
    optimized_count: int = 0,
) -> OptimizationResult:
    original_tokens = _estimate_tokens(original)
    optimized_tokens = _estimate_tokens(optimized)
    saved = max(0, original_tokens - optimized_tokens)
    percent = 100.0 * saved / original_tokens
    result = OptimizationResult(
        original_context=original,
        optimized_context=optimized,
        original_token_estimate=original_tokens,
        optimized_token_estimate=optimized_tokens,
        estimated_tokens_saved=saved,
        estimated_savings_percent=percent,
        protected_segments_count=protected,
        eligible_segments_count=eligible,
        optimized_segments_count=optimized_count,
        unknown_segments_count=unknown,
        bypassed=bypass_reason is not None,
        bypass_reason=bypass_reason,
        error=error,
        compression_duration_ms=(time.monotonic() - started) * 1000,
        original_content_hash=_hash(original),
        optimized_content_hash=_hash(optimized),
        policy_version=policy.policy_version,
        original_context_used=original_used,
    )
    result.metrics = metrics_event(result, policy)
    return result


def metrics_event(result: OptimizationResult, policy: HeadroomPolicy, **context: Any) -> dict[str, Any]:
    allowed_context = {key: context.get(key) for key in ("request_id", "task_id", "provider", "model")}
    return {
        "event": "headroom_context_optimization",
        "timestamp": time.time(),
        **allowed_context,
        "mode": policy.mode.value,
        "original_token_estimate": result.original_token_estimate,
        "optimized_token_estimate": result.optimized_token_estimate,
        "estimated_tokens_saved": result.estimated_tokens_saved,
        "estimated_savings_percent": result.estimated_savings_percent,
        "protected_segments_count": result.protected_segments_count,
        "eligible_segments_count": result.eligible_segments_count,
        "optimized_segments_count": result.optimized_segments_count,
        "unknown_segments_count": result.unknown_segments_count,
        "bypassed": result.bypassed,
        "bypass_reason": result.bypass_reason,
        "compression_duration_ms": result.compression_duration_ms,
        "headroom_error_type": result.error,
        "request_succeeded": None,
        "original_context_used": result.original_context_used,
        "retry_used_original_context": False,
        "policy_version": result.policy_version,
    }


def complete_metrics(
    result: OptimizationResult,
    *,
    request_succeeded: bool,
    retry_used_original_context: bool = False,
) -> dict[str, Any]:
    """Complete transport fields without retaining or logging request content."""
    completed = dict(result.metrics)
    completed["request_succeeded"] = bool(request_succeeded)
    completed["retry_used_original_context"] = bool(
        retry_used_original_context and result.original_context_used
    )
    result.metrics = completed
    LOGGER.info("headroom_metrics_completed %s", json.dumps(completed, sort_keys=True))
    return completed


def apply_to_request(request: Mapping[str, Any], config: Mapping[str, Any] | None, **context: Any) -> tuple[dict[str, Any], OptimizationResult]:
    headroom_config = dict((config or {}).get("headroom") or {})
    policy = policy_from_mapping(headroom_config)
    bypass = bool(request.get("headroom_bypass") or context.get("headroom_bypass"))
    clean_request = copy.deepcopy(dict(request))
    clean_request.pop("headroom_bypass", None)
    result = optimize_context(clean_request, policy, bypass=bypass)
    result.metrics = metrics_event(result, policy, **context)
    if policy.record_metrics:
        LOGGER.info("headroom_metrics %s", json.dumps(result.metrics, sort_keys=True))
    payload = result.original_context if result.original_context_used else result.optimized_context
    return copy.deepcopy(dict(payload)), result


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "mode": "off",
    "telemetry_enabled": False,
    "fail_open": True,
    "minimum_input_tokens": 4000,
    "minimum_expected_savings_percent": 10,
    "timeout_ms": 5000,
    "preserve_original_hash": True,
    "record_metrics": True,
    "raw_content_logging": False,
    "eligible_content": sorted(_ELIGIBLE_KINDS),
    "protected_content": sorted(_PROTECTED_KINDS | {"unknown_content"}),
}
