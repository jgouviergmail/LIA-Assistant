# ADR-267 — Ollama is a native provider, and its server declares what its models can do

**Date**: 2026-09-05 · **Status**: Accepted · **Amends**: ADR-245 (reasoning seam), ADR-220 (usage accounting), ADR-244 (capability catalogue)

## Context

### What was measured

The `response` slot was moved to `ollama / qwen3.8:27b` in production on 2026-09-05.
Every turn died at instantiation:

```
ValidationError: 1 validation error for ChatOpenAI
reasoning_effort  Input should be a valid string
  [input_value=ReasoningIntent(level='none', ...)]
```

Ollama was served through `ChatOpenAI` pointed at its OpenAI-compatible bridge. Four
defects sat on that one path, each proven separately (production trace, a read of the
decrypted configuration, a probe from the API container, the Ollama and langchain-openai
sources, an offline simulation over twelve provider/model/level combinations):

1. The Ollama and Perplexity branches of `_prepare_provider_config` never routed
   `reasoning_effort` through the ADR-245 seam. The stored intent object reached the
   client and failed validation for ANY level, `provider_default` included. The `none`
   came from the slot's code default through `merge_config` — 29 of the 58 slot
   defaults carry a non-null intent — so no admin choice could avoid it.
2. The stored URL had no `/v1`; the bridge serves nothing else (`/models` → 404,
   `/v1/models` → 200). The discovery stripped the suffix, the adapter did not.
3. langchain-openai sends the output cap as `max_completion_tokens`; the bridge reads
   `max_tokens` only. The slot's cap never arrived.
4. A streamed call carried no usage unless asked; `LLMCallsWithoutUsage` (threshold
   zero) fired on every turn of a streamed slot for a spend that exists at 0 EUR.

A first fix routed both branches through the seam, normalised the URL, carried the cap
in `extra_body` and asked for usage. Its runtime proof exposed the design fault behind
all four: **the shim cannot say anything the bridge does not spell**. With twelve tokens
requested, `qwen3.8:27b` produced twelve tokens of *thinking* and an empty answer,
because Ollama thinks by default on a thinking model and LIA had no way to tell it not
to — a discovered tag resolved to no reasoning family, so `none` was silently dropped.
And the compaction threshold read `51 200`, which is `128 000 × 0.4`: the generic default
for a model nobody knows, against a server that allocates its context window by VRAM
tier (4k under 24 GiB) and truncates the beginning of a longer prompt in silence.

### What Ollama offers

Read in the Ollama repository (`docs/capabilities/thinking.mdx`, `openai/openai.go`,
`server/routes.go`, `api/types.go`) and in `langchain-ollama` 1.1.0:

- the native `/api/chat` takes `think` — a boolean or a level (`low`/`medium`/`high`/
  `max`); `false` is accepted by every model, a positive level is refused (400) by a
  model without the `thinking` capability; a thinking model thinks when nothing is said;
- `/api/show` names each tag's capabilities (`completion`, `tools`, `vision`,
  `thinking`, `embedding`) and its maximum context length;
- `options.num_ctx` sets the context window per request, `num_predict` the output cap;
- the response separates `message.thinking` from `message.content` and carries
  `prompt_eval_count` / `eval_count` on every response, streamed or not;
- `format` accepts a JSON schema, grammar-constrained on the server, for every model;
- `ChatOllama` (langchain-ollama) exposes all of it: `reasoning: bool | str | None`,
  `num_ctx`, `num_predict`, `format`, `client_kwargs` for the transport timeout, and
  puts the trace in `additional_kwargs["reasoning_content"]` — the field LIA's progress
  UI already streams for DeepSeek. ADR-026 drew `ChatOllama`; `inference_params`
  already mapped `chat-ollama`. The shim was never the intended interface.

## Decision

### 1. Ollama is served by the native client

`providers/ollama_chat.py` owns the client — the traced subclass and its
construction, one cohesive unit like `_deepseek_patched.py`, and an extraction rather
than growth in `adapter.py`, which sits at the 600-SLOC cap. The adapter keeps only
what it alone knows: the credential (the Ollama "key" IS the server URL), the
configured window, and what the server said about the tag. The four
dedicated-SDK providers now share one dispatch (`_create_with_dedicated_client`), so
`create_llm` reads as a pipeline rather than a chain of provider special cases — both
ratchets, size and complexity, said the same thing.

The OpenAI-compatible branch is gone, and with it the
`/v1` suffix (both readers now use the server root — `providers/ollama_urls.py`
tolerates and strips the suffix operators typed), the `extra_body` cap and the
`stream_usage` ask. The slot's `max_tokens` is `num_predict`; the per-slot transport
timeout (ADR-221) travels in `client_kwargs`; `top_p` and `temperature` are native;
the two OpenAI penalties have no native equivalent and are dropped, and the discovered
profile declares them unsupported so the admin UI does not offer them. A
`provider_config` key the client does not define is reported and dropped — `ChatOllama`
ignores unknown fields in silence, and a silently ignored `num_ctx` typo is the failure
that guard exists for.

### 2. The server is the authority on its own models — a discovered layer in the cache

`ModelCapabilitiesCache` gains a **discovered** layer beside the catalogue rows:
profiles built from `/api/show` (`build_discovered_profile`), provenance `discovered`,
in memory only, never a database row. It is a separate layer on purpose — `load_from_db`
swaps the catalogue wholesale on every reload and would otherwise wipe it — and it WINS
over a catalogue row of the same name, because the seed's Ollama rows are static
guesses. It refreshes on the ADDRESS, not on every reload: `LLMConfigOverrideCache.load_from_db`
is where the Ollama URL may have changed (boot, an admin key edit, a cross-worker
invalidation), but that path also runs when an admin saves ANY slot, and the discovery
is network I/O — refreshing there unconditionally would make each of those saves wait
for the timeout whenever the server is unreachable. So it discovers when the address
moved, or when nothing is known yet (a server down at boot is retried), and it drops
the layer when the address is removed. What a running server holds is refreshed by the
admin's own model listing, which discovers on every open (TTL-bounded) and reads the
same discovery once for the runtime and for the response. An unreachable server clears
the layer: a tag the server no longer lists keeps no profile.

Adding `discovered` to the database enum was considered and rejected: ADR-244 curates
DB capabilities from vendored registries and never from the network on an execution
path; a live server's word belongs in memory, refreshed, not in a row that outlives it.

### 3. The `ollama` reasoning family, ladder declared per model

The family's ladder is a **vocabulary** (`none`, `low`, `medium`, `high`, `max`) and
`ReasoningProfile.ladder_from_catalogue` says that whether a given model reasons is
known only to the catalogue — here, to the discovered layer. The discovery declares the
full ladder for a `thinking` model and `("none",)` for the others; a tag nobody
discovered resolves to the unknown family (no kwarg, no rejection, no offer — the
pre-ADR-267 behaviour, kept on purpose). Three consequences fall out of the existing
machinery without a special case:

- on a thinking model, `none` → `think=false`, a level → `think=<level>`, `minimal`
  and `xhigh` coerce upward onto the server vocabulary (ADR-245 ties break upward);
- on a model that cannot think, every depth coerces to the switch-off — `("none",)` is
  the one ladder shape the coercion keeps usable — so the server, which refuses a
  positive level on such a model, only ever receives `think=false`; the write path
  refuses the depth with a 422 and the UI offers only `none`;
- when nothing is asked and the model IS a thinking model, the adapter makes the
  server default explicit (`reasoning=True`): that is the only way `langchain-ollama`
  separates the trace into `reasoning_content` instead of dropping it. The server would
  think anyway; LIA now sees it.

### 4. What LIA accounts with is what LIA requests: one `num_ctx` chain

The discovered profile's `max_input_tokens` is the `num_ctx` LIA will request:
`OLLAMA_NUM_CTX` when the operator set it, else the model's own maximum capped by
`OLLAMA_NUM_CTX_DEFAULT_CAP` (32 768, Ollama's own tier for 24–48 GiB). The adapter
sends that same number on every call — `provider_config` may override it per slot — and
`get_effective_context_window` trusts a `discovered` profile, so the compaction
threshold, the ReAct budget and the meetings synthesis read the number the server
actually allocates. Measured: `num_ctx=8192` requested, `/api/ps` reports 8192 allocated,
`get_effective_context_window` returns 8192. A tag nobody discovered gets no request,
the server's VRAM tier, and a warning naming the gap.

### 5. Usage is native, structured output is native

`PROVIDER_USAGE_CAPABILITIES["ollama"]` is `native` (ADR-220 amended): the client
carries `prompt_eval_count` / `eval_count` on every response, so the ledger receives
exact counts at 0 EUR and `LLMCallsWithoutUsage` stays a signal. Perplexity remains the
one `excluded` provider, for the reason that was the right one (end-user key).

`provider_supports_structured_output["ollama"]` is `True` and the native path uses
`method="json_schema"` for Ollama (`native_structured_method`, one choice for the three
call sites): the server's `format` is grammar-constrained for every model, whereas the
forced-tool mechanism needs `tool_choice`, which Ollama does not implement. Measured
through `get_structured_output`: a Pydantic instance back, with thinking off and with
thinking `low`.

### 5bis. The register reads the call

`ChatOllama` publishes only `_type` and `stop` as invocation parameters
(measured on 1.1.0): the temperature, the cap, the window and `think` travel in
the request and never reach a callback, so an Ollama call would have entered the
Article-12 register (ADR-263 lot 7) as a provider name and nothing else. LIA
serves `ChatOllamaTraced`, a subclass that publishes exactly the fields it sends
under the names the register normalises — `num_predict` is the fourth spelling
of the output cap, `think` the fourth shape of reasoning (`False` → `none`, a
level → that level, `True` → no stated depth).

### 6. Guards

- `test_reasoning_seam_guard.py` drives every `ProviderType` member with every storable
  level: no constructor receives the intent object, every kwarg is JSON-serialisable.
  Mutation-checked: reinstating the original defect turns thirteen tests red.
- `_merge_extra_body` replaces three plain assignments to `extra_body` (Qwen dropped the
  `provider_config` value); `extra_body` is merged, never assigned.

## Consequences

- Any of the 58 slots can run on any Ollama tag; a thinking model obeys the configured
  level; the answer text is never eaten by an unrequested trace; the trace is shown
  live where the node streams reasoning.
- The admin UI is data-driven: a thinking tag shows the reasoning widget with the
  server's ladder, a plain tag shows `none` alone, the two penalties are hidden.
- `langchain-ollama` and `ollama` join the runtime manifest (ADR-112 lockfiles); the
  API image is rebuilt on deploy.
- Cloud-proxied tags (`*-cloud`) appear in the discovery like any other tag: they run
  on the operator's Ollama account.

### What this ADR does not do

- No Ollama embeddings: the embedding registry (ADR-242) does not know the provider.
- A model without a thinking parser that writes `<think>` inline is not cleaned up; the
  server separates the trace only for models it has a parser for.
- The context window is requested, not verified per call: `ollama ps` remains the
  operator's check when a machine is short of VRAM.

## Alternatives considered

- **Keep the shim and patch around it** (seam on both branches, URL normalisation,
  `extra_body.max_tokens`, `stream_options`): shipped as the first fix, proven working
  at the wire level, and rejected by its own runtime proof — an empty answer on a
  thinking model, a context window nobody controlled. The bridge offers
  `reasoning_effort`, but not `num_ctx`, and its thinking trace is not read by
  langchain-openai's Chat Completions converter.
- **A capability-aware family fed by the discovery at instantiation**: rejected, the
  adapter is synchronous and a network call on the LLM instantiation path is forbidden.
  The discovered layer moves the network to the moments the URL may change.
- **A ladder of `none` only for every Ollama tag**: honest but blind — it would have
  switched thinking OFF on a thinking model whose operator configured a depth.
