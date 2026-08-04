"""Config models and the per-call accounting envelope for jobengine.llm.
See specs/05-model-routing.md.
"""

from typing import Literal

from pydantic import BaseModel

Stage = Literal["relevance", "extract", "rephrase"]
ProviderTier = Literal["local", "api"]
FallbackMode = Literal["skip", "fail"]


class LocalConfig(BaseModel):
    enabled: bool
    base_url: str
    model: str
    context: int
    timeout_s: int


class RoutingConfig(BaseModel):
    relevance: ProviderTier
    extract: ProviderTier
    rephrase: ProviderTier


class FallbackConfig(BaseModel):
    relevance: FallbackMode
    extract: FallbackMode
    rephrase: FallbackMode


class ApiConfig(BaseModel):
    enabled: bool = False


class LLMConfig(BaseModel):
    local: LocalConfig
    routing: RoutingConfig
    fallback: FallbackConfig
    api: ApiConfig = ApiConfig()


class LLMCallResult(BaseModel):
    """Accounting envelope for one LLM call.

    Callers persist whichever of these fields their own table has columns
    for (job_analysis, relevance_scores per specs/00-data-model.md); this
    module never writes to the db itself.
    """

    stage: Stage
    provider: ProviderTier
    model: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int
    cost_usd: float
    output: dict
