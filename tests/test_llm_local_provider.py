"""Tests for jobengine.llm.providers.local. See specs/05-model-routing.md."""

import asyncio
from typing import Any

from pydantic import BaseModel

from jobengine.llm.providers.local import LocalProvider


def _run(coro):
    return asyncio.run(coro)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(
        self, content: str, prompt_eval_count: int = 10, eval_count: int = 5
    ) -> None:
        self.message = _FakeMessage(content)
        self.prompt_eval_count = prompt_eval_count
        self.eval_count = eval_count


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def chat(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return self._response


class _PingSchema(BaseModel):
    ok: bool


def _provider(client: _FakeClient) -> LocalProvider:
    return LocalProvider(
        base_url="http://example:11434",
        model="qwen3.5:9b-q4_K_M",
        context=16384,
        timeout_s=120,
        client=client,
    )


def test_call_sets_think_false_explicitly():
    client = _FakeClient(_FakeResponse('{"ok": true}'))
    provider = _provider(client)

    _run(
        provider.call(
            stage="relevance",
            messages=[{"role": "user", "content": "hi"}],
            schema=_PingSchema,
        )
    )

    assert len(client.calls) == 1
    assert client.calls[0]["think"] is False


def test_call_passes_json_schema_for_constrained_decoding():
    client = _FakeClient(_FakeResponse('{"ok": true}'))
    provider = _provider(client)

    _run(
        provider.call(
            stage="relevance",
            messages=[{"role": "user", "content": "hi"}],
            schema=_PingSchema,
        )
    )

    assert client.calls[0]["format"] == _PingSchema.model_json_schema()


def test_call_uses_configured_context_window():
    client = _FakeClient(_FakeResponse('{"ok": true}'))
    provider = _provider(client)

    _run(
        provider.call(
            stage="rephrase",
            messages=[{"role": "user", "content": "hi"}],
            schema=_PingSchema,
        )
    )

    assert client.calls[0]["options"] == {"num_ctx": 16384}


def test_call_returns_accounting_envelope_with_zero_cost():
    client = _FakeClient(
        _FakeResponse('{"ok": true}', prompt_eval_count=42, eval_count=7)
    )
    provider = _provider(client)

    result = _run(
        provider.call(
            stage="extract",
            messages=[{"role": "user", "content": "hi"}],
            schema=_PingSchema,
        )
    )

    assert result.provider == "local"
    assert result.stage == "extract"
    assert result.model == "qwen3.5:9b-q4_K_M"
    assert result.input_tokens == 42
    assert result.output_tokens == 7
    assert result.cost_usd == 0.0
    assert result.output == {"ok": True}
    assert result.duration_ms >= 0
