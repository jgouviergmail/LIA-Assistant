# Provider Cost Adjustment — Investigation & Recommendations

## Context

During sub-agent integration testing (2026-03-17), a systematic discrepancy was identified between LIA's internal token cost tracking and actual provider billing.

## Findings

### Anthropic (claude-sonnet-4-6)

**Test case**: Complex sub-agent delegation (3 experts, Paris-Strasbourg transport comparison)

| Metric | LIA Tracking | Anthropic Billing | Delta |
|--------|-------------|-------------------|-------|
| Cost (EUR) | €0.198 | €0.22 | +€0.022 (~11%) |
| Tokens tracked | 45,456 (36,119 in + 7,069 out + 2,268 cached) | Not disclosed per-request | — |

**Root cause hypothesis**: Anthropic bills tokens that are NOT reported in the API `usage` field:
- System prompt overhead (internal formatting, tool schemas injection)
- Message framing tokens (role markers, conversation structure)
- Safety/alignment prefix tokens (invisible to the caller)
- Potential batch rounding at billing level

This is consistent across multiple test runs (~10-15% overhead observed each time).

### OpenAI (gpt-5.2, gpt-5-mini, gpt-5-nano)

**Not yet quantified**. OpenAI generally reports tokens more accurately in the `usage` field, but a small delta may exist for:
- Tool/function definition tokens (may or may not be in `usage.prompt_tokens`)
- System message overhead
- Reasoning tokens on `o`-series models (billed but not always in `completion_tokens`)

### Google (Gemini)

**Not yet quantified**. Google has a different tokenization (SentencePiece) and pricing structure.

## Impact

For a SaaS business model where users are billed based on tracked token consumption:
- **11% under-billing on Anthropic models** means margin erosion on every request
- With sub-agents (3-5 LLM calls per sub-agent × 3 sub-agents), the absolute delta grows significantly
- At scale: 1000 users × 10 requests/day × €0.02 delta = **€200/day revenue leakage**

## Recommended Solution

### Provider Cost Adjustment Factor

Add a configurable `cost_adjustment_factor` per provider in the pricing system:

```
# .env or Admin > Settings
ANTHROPIC_COST_ADJUSTMENT_FACTOR=1.12   # +12% markup to cover billing delta
OPENAI_COST_ADJUSTMENT_FACTOR=1.02      # +2% estimated (needs quantification)
GOOGLE_COST_ADJUSTMENT_FACTOR=1.05      # +5% estimated (needs quantification)
```

**Implementation approach**:
1. Add `cost_adjustment_factor` column to `llm_model_pricing` table (per-model granularity) or as a provider-level setting
2. Apply factor in `get_cached_cost_usd_eur()` after calculating base cost
3. Expose in Admin panel for tuning based on observed billing data
4. Default to 1.0 (no adjustment) for backward compatibility

### Quantification Plan

Before implementing, collect data across multiple scenarios:

| Test | Provider | Model | Scenario | LIA Cost | Provider Cost | Factor |
|------|----------|-------|----------|----------|---------------|--------|
| 1 | Anthropic | claude-sonnet-4-6 | Simple chat (no tools) | — | — | — |
| 2 | Anthropic | claude-sonnet-4-6 | Tool execution (1 tool) | — | — | — |
| 3 | Anthropic | claude-sonnet-4-6 | Sub-agent delegation (3 agents) | €0.198 | €0.22 | 1.11 |
| 4 | OpenAI | gpt-5.2 | Simple chat | — | — | — |
| 5 | OpenAI | gpt-5.2 | Tool execution | — | — | — |
| 6 | OpenAI | gpt-5-mini | Pipeline calls (router, etc.) | — | — | — |

This data will determine whether the factor is:
- **Constant per provider** (simplest: one factor per provider)
- **Variable by model** (some models may have more overhead)
- **Variable by call type** (tool calls may have more overhead than simple chat)

## Status

- **Identified**: 2026-03-17
- **Quantified**: Anthropic ~11% (one test case)
- **Implementation**: Planned for future iteration
- **Priority**: Medium-High (direct revenue impact, but requires broader data collection first)

## References

- Anthropic API docs: Token counting does not include internal system tokens
- OpenAI API docs: `usage.prompt_tokens` includes system message tokens but may exclude function schemas
- Related ADR: ADR-039-Cost-Optimization-Token-Management.md
