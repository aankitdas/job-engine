"""Anthropic provider. See specs/05-model-routing.md and CLAUDE.md hard
rule 9 ("never construct an Anthropic provider... if you believe a stage
needs a paid call, stop and ask").

No stage in specs/05-model-routing.md's routing table routes here today;
the daily pipeline is zero-cost by design. This module never reads
os.environ: `api_key` must be handed to the constructor explicitly by a
caller that already decided, out of band, to make a paid call.
`jobengine.llm.router.get_provider()` adds a second, independent gate on
top of this one, see its docstring.
"""

from pydantic import BaseModel

from jobengine.llm.schemas import LLMCallResult, Stage


class AnthropicProvider:
    def __init__(self, *, api_key: str) -> None:
        if not api_key:
            raise ValueError("AnthropicProvider requires a non-empty api_key")
        self.api_key = api_key

    async def call(
        self,
        *,
        stage: Stage,
        messages: list[dict[str, str]],
        schema: type[BaseModel],
    ) -> LLMCallResult:
        raise NotImplementedError(
            "No stage in specs/05-model-routing.md routes here today. If "
            "you believe a stage needs a paid call, stop and ask "
            "(CLAUDE.md hard rule 9) before implementing this."
        )
