"""Response contracts for `app.api.routes_admin` (ROADMAP.md Phase 1, Step
1.2's LLM call ledger). Session-gated, NOT per-user scoped -- see
`app.api.routes_admin.get_llm_usage`'s docstring for the scoping rationale.
"""

from datetime import date, datetime

from pydantic import BaseModel


class LLMUsageAggregate(BaseModel):
    """One (day, provider, model, purpose) bucket of `llm_calls` rows."""

    day: date
    provider: str
    model: str
    purpose: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    success_count: int
    failure_count: int
    fallback_count: int
    # ROADMAP.md Phase 2, Step 2.1 -- count of calls where `parse_fallback`
    # was True (Ollama/mock's JSON-mode-prompt + regex/brace-scan path, NOT
    # Gemini/OpenAI/Anthropic's native structured-output calls). See
    # `app.data.models.LLMCall`'s docstring.
    parse_fallback_count: int
    # ROADMAP.md Phase 2, Step 2.3 -- count of calls served from
    # `app.services.llm_cache` instead of a real provider call. Each one is
    # already reflected in `cost_usd`/`prompt_tokens`/`completion_tokens`
    # being 0 for that row; this count is what makes the savings legible
    # (e.g. "12 of 40 detailed_instructions calls today were free").
    cache_hit_count: int


class LLMUsageTotals(BaseModel):
    """Grand totals across every row in `rows` below (same window)."""

    calls: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


class LLMUsageResponse(BaseModel):
    days: int
    since: datetime
    totals: LLMUsageTotals
    rows: list[LLMUsageAggregate]
