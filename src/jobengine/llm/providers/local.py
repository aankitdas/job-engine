"""Local Ollama provider. See specs/05-model-routing.md.

Every call sets think=False explicitly, in the request itself, never left
to a Modelfile default: Ollama auto-enables thinking for thinking-capable
models unless a request says otherwise, and for hundreds of short
classification calls a visible thinking block both wastes output tokens
and fights the JSON grammar constraint (`format=`) below.
"""

import time
from typing import Any, Protocol

import ollama
from pydantic import BaseModel

from jobengine.llm.schemas import LLMCallResult, Stage


class _ChatClient(Protocol):
    async def chat(self, **kwargs: Any) -> Any: ...


class LocalProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        context: int,
        timeout_s: int,
        client: _ChatClient | None = None,
    ) -> None:
        self.model = model
        self.context = context
        self.timeout_s = timeout_s
        self._client: _ChatClient = client or ollama.AsyncClient(
            host=base_url, timeout=timeout_s
        )

    async def call(
        self,
        *,
        stage: Stage,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
    ) -> LLMCallResult:
        started = time.monotonic()
        response = await self._client.chat(
            model=self.model,
            messages=messages,
            format=schema.model_json_schema(),
            think=False,
            options={"num_ctx": self.context},
        )
        duration_ms = round((time.monotonic() - started) * 1000)
        parsed = schema.model_validate_json(response.message.content or "")
        return LLMCallResult(
            stage=stage,
            provider="local",
            model=self.model,
            input_tokens=response.prompt_eval_count,
            output_tokens=response.eval_count,
            duration_ms=duration_ms,
            cost_usd=0.0,
            output=parsed.model_dump(),
        )
