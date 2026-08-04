"""uv run python -m jobengine.llm.check. See specs/05-model-routing.md's
definition of done: per-stage resolved provider, reachability, and
round-trip latency on a schema-constrained call. Exits non-zero if any
Anthropic provider would be constructed under the default config.
"""

import asyncio
import sys
from typing import NamedTuple

from pydantic import BaseModel

from jobengine.llm.providers.anthropic import AnthropicProvider
from jobengine.llm.router import get_provider, load_config
from jobengine.llm.schemas import LLMConfig, Stage

STAGES: tuple[Stage, ...] = ("relevance", "extract", "rephrase")


class _PingSchema(BaseModel):
    ok: bool


class StageCheck(NamedTuple):
    stage: Stage
    tier: str
    anthropic_constructed: bool
    reachable: bool | None
    latency_ms: float | None
    detail: str | None


async def _check_stage(stage: Stage, config: LLMConfig) -> StageCheck:
    tier = getattr(config.routing, stage)
    try:
        provider = get_provider(stage, config)
    except RuntimeError as exc:
        # The billing guard refused construction. Correct outcome under a
        # default config (llm.api.enabled = false), not a check failure.
        return StageCheck(stage, tier, False, None, None, str(exc))

    if isinstance(provider, AnthropicProvider):
        return StageCheck(
            stage,
            tier,
            True,
            False,
            None,
            "AnthropicProvider was constructed under the default config",
        )

    try:
        result = await provider.call(
            stage=stage,
            messages=[{"role": "user", "content": 'Reply with {"ok": true}.'}],
            schema=_PingSchema,
        )
    except Exception as exc:  # noqa: BLE001 - a reachability probe must
        # report every provider failure mode (unreachable, timeout,
        # malformed decode) as a status line, not crash the CLI. Include
        # the exception's type name: httpx's own timeout/connect errors
        # often carry no message text, so str(exc) alone can be empty,
        # confirmed against a real unreachable host during C1's session.
        return StageCheck(
            stage, tier, False, False, None, f"{type(exc).__name__}: {exc}"
        )
    return StageCheck(stage, tier, False, True, float(result.duration_ms), None)


async def _run() -> int:
    config = load_config()
    exit_code = 0
    for stage in STAGES:
        check = await _check_stage(stage, config)
        if check.anthropic_constructed:
            exit_code = 1
        if check.reachable is None:
            status = f"refused by billing guard ({check.detail})"
        elif check.reachable:
            status = f"reachable, {check.latency_ms:.0f}ms"
        else:
            status = f"UNREACHABLE ({check.detail})"
        print(f"{check.stage:10s} provider={check.tier:6s} {status}")
    return exit_code


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
