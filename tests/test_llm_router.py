"""Tests for jobengine.llm.router. See specs/05-model-routing.md, and
CLAUDE.md hard rules 8-10 (all LLM calls route through here, an Anthropic
provider must be nearly impossible to construct by accident, and this
module must never read ANTHROPIC_API_KEY from the environment).
"""

import asyncio
from pathlib import Path

import pytest
from pydantic import BaseModel

from jobengine.llm import router
from jobengine.llm.providers.anthropic import AnthropicProvider
from jobengine.llm.providers.local import LocalProvider
from jobengine.llm.schemas import (
    ApiConfig,
    FallbackConfig,
    LLMConfig,
    LocalConfig,
    RoutingConfig,
)


def _run(coro):
    return asyncio.run(coro)


def _make_config(
    *, relevance_tier: str = "local", api_enabled: bool = False
) -> LLMConfig:
    return LLMConfig(
        local=LocalConfig(
            enabled=True,
            base_url="http://fake:11434",
            model="qwen3.5:9b-q4_K_M",
            context=16384,
            timeout_s=120,
        ),
        routing=RoutingConfig(
            relevance=relevance_tier, extract="local", rephrase="local"
        ),
        fallback=FallbackConfig(relevance="skip", extract="fail", rephrase="skip"),
        api=ApiConfig(enabled=api_enabled),
    )


class _PingSchema(BaseModel):
    ok: bool


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)
        self.prompt_eval_count = 1
        self.eval_count = 1


class _OkClient:
    async def chat(self, **kwargs):
        return _FakeResponse('{"ok": true}')


class _FailingClient:
    async def chat(self, **kwargs):
        raise ConnectionError("no route to host")


# ---------------------------------------------------------------------------
# load_config: env var expansion
# ---------------------------------------------------------------------------

_TOML = """
[llm.local]
enabled   = true
base_url  = "${TEST_OLLAMA_BASE_URL}"
model     = "qwen3.5:9b-q4_K_M"
context   = 16384
timeout_s = 120

[llm.routing]
relevance = "local"
extract   = "local"
rephrase  = "local"

[llm.fallback]
relevance = "skip"
extract   = "fail"
rephrase  = "skip"

[llm.api]
enabled = false
"""


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "llm.toml"
    path.write_text(_TOML)
    return path


def test_load_config_expands_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_OLLAMA_BASE_URL", "http://10.0.0.5:11434")
    path = _write_config(tmp_path)

    config = router.load_config(path)

    assert config.local.base_url == "http://10.0.0.5:11434"
    assert config.api.enabled is False


def test_load_config_raises_clear_error_when_env_var_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_OLLAMA_BASE_URL", raising=False)
    path = _write_config(tmp_path)

    with pytest.raises(RuntimeError, match="TEST_OLLAMA_BASE_URL"):
        router.load_config(path)


# ---------------------------------------------------------------------------
# get_provider: the billing guard
# ---------------------------------------------------------------------------


def test_get_provider_returns_local_provider_for_local_tier():
    config = _make_config()
    provider = router.get_provider("relevance", config)
    assert isinstance(provider, LocalProvider)


def test_get_provider_refuses_api_tier_when_disabled():
    config = _make_config(relevance_tier="api", api_enabled=False)
    with pytest.raises(RuntimeError, match="llm.api.enabled"):
        router.get_provider("relevance", config)


def test_get_provider_refuses_api_tier_without_explicit_key_even_when_enabled():
    config = _make_config(relevance_tier="api", api_enabled=True)
    with pytest.raises(RuntimeError, match="api_key"):
        router.get_provider("relevance", config)


def test_get_provider_constructs_anthropic_only_with_both_enabled_and_key():
    config = _make_config(relevance_tier="api", api_enabled=True)
    provider = router.get_provider("relevance", config, api_key="sk-test")
    assert isinstance(provider, AnthropicProvider)


def test_get_provider_never_reads_anthropic_api_key_from_environment(monkeypatch):
    # Simulates the exact accident CLAUDE.md hard rule 10 warns about: the
    # key sitting in the environment. It must still be refused.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-be-used")
    config = _make_config(relevance_tier="api", api_enabled=True)

    with pytest.raises(RuntimeError, match="api_key"):
        router.get_provider("relevance", config)


# ---------------------------------------------------------------------------
# call(): fallback handling
# ---------------------------------------------------------------------------


def test_call_returns_result_on_success():
    config = _make_config()
    result = _run(
        router.call(
            "relevance",
            [{"role": "user", "content": "hi"}],
            _PingSchema,
            config,
            local_client=_OkClient(),
        )
    )
    assert result.output == {"ok": True}


def test_call_skip_fallback_returns_none_on_provider_failure():
    config = _make_config()  # relevance fallback = "skip"
    result = _run(
        router.call(
            "relevance",
            [{"role": "user", "content": "hi"}],
            _PingSchema,
            config,
            local_client=_FailingClient(),
        )
    )
    assert result is None


def test_call_fail_fallback_raises_on_provider_failure():
    config = _make_config()  # extract fallback = "fail"
    with pytest.raises(ConnectionError):
        _run(
            router.call(
                "extract",
                [{"role": "user", "content": "hi"}],
                _PingSchema,
                config,
                local_client=_FailingClient(),
            )
        )


def test_call_never_swallows_billing_guard_errors_via_fallback():
    # relevance's fallback is "skip", but a refused Anthropic construction
    # is a misconfiguration, not a transient provider failure, and must
    # still raise rather than silently returning None.
    config = _make_config(relevance_tier="api", api_enabled=False)
    with pytest.raises(RuntimeError, match="llm.api.enabled"):
        _run(
            router.call(
                "relevance",
                [{"role": "user", "content": "hi"}],
                _PingSchema,
                config,
            )
        )
