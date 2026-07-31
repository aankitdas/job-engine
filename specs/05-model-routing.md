# Spec 05: Model Routing and Local Inference

Revision 2. Much simpler than the previous draft, because there is no per-job
tailoring and no LLM critic.

## Module
`src/jobengine/llm/` with `router.py`, `providers/{local,anthropic}.py`,
`schemas.py`.

## What actually calls a model

| Stage | Provider | Tokens in | Frequency |
|---|---|---|---|
| 2.5 relevance scoring | local | ~6,000 | 300-500 per night |
| 3 keyword extraction | local | ~5,000 | 30-60 per night |
| P3 bullet rephrase | local | ~400 | 0-10 per night |
| Monthly base resume | interactive Claude Code | n/a | ~3 per month |

Nothing else. Everything else in the pipeline is deterministic Python.

The daily loop makes **zero paid API calls**.

## Laptop model

**Qwen3.5-9B, Q4_K_M**, context 16384.

9B is the ceiling on 8188 MiB. A 12B at Q4_K_M is roughly 7.3GB of weights
before any KV cache, and exceeding VRAM does not degrade gracefully: once
layers spill to system RAM over PCIe, throughput collapses by roughly 30x.

```
num_ctx        16384
num_gpu        999          # force full offload
flash_attn     true
kv_cache_type  q8_0         # roughly halves KV memory
```

Verify full offload in `nvidia-smi` during load. Expect 6.5 to 7 GB resident.
Under 5 GB with slow generation means layers are on CPU.

Do not use reasoning-model distills. They spend output tokens on visible
chain-of-thought, which is wrong for hundreds of short classification calls,
and the thinking block fights grammar constraints.

Note P3 is the easiest task in the set. Rephrasing one existing sentence to
carry a named keyword is well within 9B capability, unlike composing a resume
from scratch, which is why the earlier "local cannot write resume prose"
concern does not apply here.

## Constrained decoding

Every structured call passes a JSON schema. Ollama takes it in `format`;
llama.cpp takes a GBNF grammar. With the decoder constrained, malformed output
is impossible, so models are selected on judgment quality alone.

## Config

```toml
[llm.local]
enabled   = true
base_url  = "${OLLAMA_BASE_URL}"
model     = "qwen3.5:9b-q4_K_M"
context   = 16384
timeout_s = 120

[llm.routing]
relevance = "local"
extract   = "local"
rephrase  = "local"

[llm.fallback]
relevance = "skip"      # unscored jobs stay in the queue, unranked
extract   = "fail"      # cannot proceed without keywords
rephrase  = "skip"      # falls through to P4, logs to gap ledger
```

Every stage must be able to run without a GPU. `skip` and `fail` are the
zero-cost fallbacks; an API path exists in the code but is off by default and
must be enabled explicitly.

## Billing guard

`router.py` refuses to construct an Anthropic provider unless
`config.llm.api.enabled` is explicitly true **and** the API key is passed
in as a parameter rather than read from the ambient environment.

Rationale: Claude Code prioritizes `ANTHROPIC_API_KEY` from the environment
over subscription auth, which silently moves interactive sessions onto metered
billing. Never set that variable in a shell profile. The guard makes an
accidental paid call impossible rather than merely discouraged.

## WSL2 networking

Run Ollama natively on Windows. Set `OLLAMA_HOST=0.0.0.0` on the Windows side
and restart it. From WSL2:

```bash
export OLLAMA_BASE_URL="http://$(ip route show default | awk '{print $3}'):11434"
```

Never hardcode the IP; WSL2 reassigns it on restart.

## DGX Spark

Another tier behind the same interface: a different `base_url`, model name,
and tier label. It is bandwidth-bound rather than capacity-bound (128GB
LPDDR5x at up to 273 GB/s shared across CPU and GPU), so it is over-specified
for the high-volume laptop stages and earns its place on the monthly base
resume generation instead, where a 70B or 120B model at roughly 35 tok/s is
fine and quality matters most.

## Accounting

Every call records provider, model, input tokens, output tokens,
duration_ms, and cost_usd (explicitly 0.0 for local). The duration column is
what tells you when a local stage is slow enough to be worth rethinking.

## Definition of done
`uv run python -m jobengine.llm.check` prints per stage: resolved provider,
reachability, and round-trip latency on a schema-constrained call. It exits
non-zero if any Anthropic provider would be constructed under the default
config.
