from pydantic import BaseModel, Field


class DetailedInstructionsRequest(BaseModel):
    """Request to rewrite an already-shown recipe's terse instructions as
    detailed, beginner-friendly steps (phrasing/elaboration only -- see
    app.services.model_provider.generate_detailed_instructions_with_provider_chain).

    `ingredients` are already-formatted display strings (e.g.
    "2 cups flour", the frontend's `ingredientDisplay(ingredient)` output),
    not structured `{name, amount, unit}` objects -- this is presentation-
    layer elaboration of a recipe already validated safe elsewhere, never a
    safety-relevant computation, so the wire contract doesn't need the
    structured Ingredient model here.
    """

    title: str
    ingredients: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    servings: int | None = None
    cuisine: str | None = None


class DetailedInstructionsResponse(BaseModel):
    """`generated=False` means `steps` is just the original `instructions`
    echoed back unmodified (no provider configured, or every provider
    failed/returned unparseable output) -- never fabricated detailed
    content. `provider_note` is set to a short human-readable explanation
    whenever `generated=False`, so the frontend can tell the user why the
    steps look unchanged rather than silently presenting them as if they
    were freshly elaborated.
    """

    steps: list[str] = Field(default_factory=list)
    generated: bool
    provider_note: str | None = None
