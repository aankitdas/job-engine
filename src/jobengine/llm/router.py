"""LLM router: the one place stage code asks for a provider. See
specs/05-model-routing.md. CLAUDE.md hard rule 8 says all LLM calls go
through this module; hard rule 9 says an Anthropic provider must never be
constructed by accident.

The Anthropic guard here is deliberately redundant with
providers/anthropic.py's own api_key requirement: get_provider() refuses to
construct AnthropicProvider unless config.llm.api.enabled is True AND the
caller passes api_key explicitly to this function. Neither this module nor
providers/anthropic.py ever reads ANTHROPIC_API_KEY, or any other env var,
to obtain a key; there is no code path in jobengine.llm that pulls a key
from the ambient environment (CLAUDE.md hard rule 10).
"""

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from jobengine.llm.providers.anthropic import AnthropicProvider
from jobengine.llm.providers.local import LocalProvider
from jobengine.llm.schemas import LLMCallResult, LLMConfig, Stage

DEFAULT_CONFIG_PATH = Path("config/llm.toml")

_ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _expand_env(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        resolved = os.environ.get(name)
        if resolved is None:
            raise RuntimeError(
                f"config/llm.toml references ${{{name}}} but it is not set "
                "in the environment. See specs/05-model-routing.md's WSL2 "
                f"networking section: export {name} before running."
            )
        return resolved

    return _ENV_VAR_RE.sub(replace, value)


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> LLMConfig:
    raw = tomllib.loads(path.read_text())
    llm = raw["llm"]
    llm["local"]["base_url"] = _expand_env(llm["local"]["base_url"])
    return LLMConfig.model_validate(llm)


def get_provider(
    stage: Stage,
    config: LLMConfig,
    *,
    api_key: str | None = None,
    local_client: Any | None = None,
) -> LocalProvider | AnthropicProvider:
    tier = getattr(config.routing, stage)
    if tier == "local":
        return LocalProvider(
            base_url=config.local.base_url,
            model=config.local.model,
            context=config.local.context,
            timeout_s=config.local.timeout_s,
            client=local_client,
        )
    if tier == "api":
        if not config.api.enabled:
            raise RuntimeError(
                "Refusing to construct AnthropicProvider: llm.api.enabled "
                "is false in config/llm.toml. See CLAUDE.md hard rule 9."
            )
        if not api_key:
            raise RuntimeError(
                "Refusing to construct AnthropicProvider: no api_key was "
                "passed to get_provider(). This function never reads "
                "ANTHROPIC_API_KEY from the environment (CLAUDE.md hard "
                "rule 9 and 10); a caller must source the key itself and "
                "pass it in explicitly."
            )
        return AnthropicProvider(api_key=api_key)
    raise ValueError(f"Unknown provider tier {tier!r} for stage {stage!r}")


async def call(
    stage: Stage,
    messages: list[dict[str, str]],
    schema: type[BaseModel],
    config: LLMConfig,
    *,
    api_key: str | None = None,
    local_client: Any | None = None,
) -> LLMCallResult | None:
    # get_provider()'s own guard errors (misconfiguration, refused billing)
    # are never caught below; only a constructed provider's call() failures
    # (unreachable, timeout, malformed decode) go through the configured
    # fallback. A refused Anthropic construction must always surface, not
    # get silently turned into a "skip".
    provider = get_provider(stage, config, api_key=api_key, local_client=local_client)
    fallback = getattr(config.fallback, stage)
    try:
        return await provider.call(stage=stage, messages=messages, schema=schema)
    except Exception:
        if fallback == "skip":
            return None
        raise
