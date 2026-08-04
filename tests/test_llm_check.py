"""Tests for jobengine.llm.check. See specs/05-model-routing.md's
definition of done: exits non-zero if any Anthropic provider would be
constructed under the default config.

`_check_stage` is exercised directly with a monkeypatched `get_provider` so
these tests don't need a real Ollama server (per plan: mocked tests here,
you run `uv run python -m jobengine.llm.check` yourself against the live
WSL2 Ollama setup).
"""

import asyncio

from jobengine.llm import check
from jobengine.llm.providers.anthropic import AnthropicProvider
from jobengine.llm.schemas import (
    ApiConfig,
    FallbackConfig,
    LLMConfig,
    LocalConfig,
    RoutingConfig,
)


def _run(coro):
    return asyncio.run(coro)


def _default_config() -> LLMConfig:
    return LLMConfig(
        local=LocalConfig(
            enabled=True,
            base_url="http://fake:11434",
            model="qwen3.5:9b-q4_K_M",
            context=16384,
            timeout_s=120,
        ),
        routing=RoutingConfig(relevance="local", extract="local", rephrase="local"),
        fallback=FallbackConfig(relevance="skip", extract="fail", rephrase="skip"),
        api=ApiConfig(enabled=False),
    )


class _OkProvider:
    async def call(self, **kwargs):
        class _Result:
            duration_ms = 12

        return _Result()


class _UnreachableProvider:
    async def call(self, **kwargs):
        raise ConnectionError("no route to host")


def test_check_stage_reports_refused_when_billing_guard_raises(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("llm.api.enabled is false")

    monkeypatch.setattr(check, "get_provider", _raise)

    result = _run(check._check_stage("relevance", _default_config()))

    assert result.anthropic_constructed is False
    assert result.reachable is None


def test_check_stage_reports_reachable_on_success(monkeypatch):
    monkeypatch.setattr(check, "get_provider", lambda stage, config: _OkProvider())

    result = _run(check._check_stage("relevance", _default_config()))

    assert result.anthropic_constructed is False
    assert result.reachable is True
    assert result.latency_ms == 12


def test_check_stage_reports_unreachable_on_call_failure(monkeypatch):
    monkeypatch.setattr(
        check, "get_provider", lambda stage, config: _UnreachableProvider()
    )

    result = _run(check._check_stage("relevance", _default_config()))

    assert result.reachable is False
    assert result.anthropic_constructed is False


def test_check_stage_flags_anthropic_construction_as_failure(monkeypatch):
    # Defensive: even if get_provider() somehow returned an
    # AnthropicProvider despite the default config, check.py must catch it
    # rather than reporting a clean pass.
    monkeypatch.setattr(
        check,
        "get_provider",
        lambda stage, config: AnthropicProvider(api_key="sk-test"),
    )

    result = _run(check._check_stage("relevance", _default_config()))

    assert result.anthropic_constructed is True
    assert result.reachable is False


def test_run_exits_zero_when_no_anthropic_provider_constructed(monkeypatch):
    monkeypatch.setattr(check, "load_config", lambda: _default_config())
    monkeypatch.setattr(check, "get_provider", lambda stage, config: _OkProvider())

    exit_code = _run(check._run())

    assert exit_code == 0


def test_run_exits_nonzero_when_anthropic_provider_would_be_constructed(monkeypatch):
    monkeypatch.setattr(check, "load_config", lambda: _default_config())
    monkeypatch.setattr(
        check,
        "get_provider",
        lambda stage, config: AnthropicProvider(api_key="sk-test"),
    )

    exit_code = _run(check._run())

    assert exit_code == 1
