# Claude Code Session Prompts — Phase 1.5 → Phase 5 (autonomous multi-agent)

How to use this file:
- Start the orchestrator: `claude --model claude-opus-4-8`
- One session per BATCH below (a batch = a phase, or Phase 1.5). Paste the
  batch prompt and let the orchestration loop in CLAUDE.md run to completion.
- Maximum automation, interactive: press Shift+Tab to enable auto-accept edits.
  Fully headless alternative:
  `claude --model claude-opus-4-8 -p "<batch prompt>" --permission-mode acceptEdits`
  (Use `--dangerously-skip-permissions` only inside a container/sandbox.)
- Each batch ends with a NEEDS HUMAN summary + phase-exit evidence. Do the
  human items in `docs/HUMAN_INPUTS.md` for the NEXT batch before starting it.
- Fresh session per batch keeps the orchestrator's context clean; subagents
  keep implementation noise out of the main window.

Execution order: 1.5 → 2 → 3 → 3.5 → 4 → 5. (2 must precede the rest: the
roadmap deliberately deploys and starts collecting user signal at the end of
Phase 2. Batch 3.5 is the ML/MLOps skills layer and depends on the corpus
and eval infrastructure from 1.5–3.)

---

## Batch 1.5 — Phase 1 closeout (blocking debt before the benchmark)

> Read CLAUDE.md and docs/ROADMAP.md fully. We are closing out the unfixed
> Phase 1 follow-ups documented in ROADMAP Phase 1, items 3–4, because the
> Phase 2 benchmark and RAG eval are invalid until they're fixed. Run the full
> orchestration protocol autonomously for these items, in this order:
>
> 1. **Wire the retriever to the full corpus.** `RecipeRetriever._base_recipes`
>    only loads the 25 seeds via `load_recipes()`; the ~4,238 imported recipes
>    are embedded in Chroma but filtered out of `retrieve()` results. Switch to
>    the seed+imported union (`load_corpus()`), keeping per-user library
>    filtering intact. Add a regression test proving an imported recipe can
>    surface in a recommendation and that allergy filtering still rejects at
>    full corpus scale.
> 2. **Re-point indexing to computed macros.** `recipe_indexing_service.py`
>    still embeds tag-based macros into the Chroma embedding text. Re-point it
>    to computed-or-unknown via `nutrition_view`, same as the scorer/frontend/
>    explanation paths, then run a full reindex.
> 3. **Generalize USDA grounding beyond the 25 seeds.** Consult the advisor
>    (MODE: ADVISE) with the `_KNOWN_RESIDUALS` list in `grounding_job.py` and
>    ROADMAP's two documented gaps: (a) undeclared-preparation wrong-state
>    matches, (b) Branded same-name-different-value noise and 0-kcal defects,
>    plus the sibling-food/synonym problem (zucchini→"Squash"). Get a concrete
>    design (e.g. synonym table strategy, median-of-duplicates or dataType
>    deprioritization for Branded noise, generic 0-kcal detection), implement
>    it, and re-run corpus grounding. Produce a grounding report; implausible
>    values go to the report for human review, never silently written.
> 4. **Seed-recipe quantities check.** Verify all 25 seed recipes have real
>    researched quantities (ROADMAP Phase 1 item 2 follow-up). If any are
>    still `amount: null`, author quantities (mass units preferred) and
>    re-ground their macros.
> 5. **Re-run the Phase 1 gates now that retrieval is real:** pytest, demo
>    eval (allergy-violation rate must be 0), and the ~50-query RAG vs.
>    keyword retrieval eval — RAG must measurably win. Report the numbers.
>
> Every item goes through advisor review. Finish with: per-item verdicts,
> final gate numbers, NEEDS HUMAN list, and the noticed-not-fixed backlog.

---

## Batch 2 — Phase 2: safety benchmark + first public deploy

> Read CLAUDE.md and docs/ROADMAP.md (Phase 2) and docs/HUMAN_INPUTS.md.
> Execute Phase 2 autonomously with the orchestration protocol:
>
> 1. **Safety benchmark.** FIRST send the advisor (MODE: ADVISE) a proposed
>    methodology: case taxonomy (allergy stated-then-contradicted, hidden
>    allergens like satay→peanut, diet-type traps like vegan→gelatin/fish
>    sauce, macro-limit traps), target of 300–500 pinned adversarial cases,
>    scoring rules, and how raw GPT / Claude / Gemini prompting will be run
>    vs. MacroChef on identical cases. Benchmark methodology is a designated
>    Fable 5 item — do not skip this consult. Then have the executor build:
>    the case set (pinned JSONL), a one-script reproducible harness
>    (`scripts/run_safety_benchmark.py`) with cached/mock modes so it runs
>    from a fresh clone without keys, and the violation-rate comparison
>    table. HUMAN GATE before running paid comparison calls at full scale:
>    report estimated API cost and wait for keys/approval (run MacroChef-side
>    and mock-side cases meanwhile). Add the benchmark to CI so every release
>    re-verifies 0 violations. Draft (do not publish) the README section and
>    a short blog post with the results table. Also package the pinned case
>    set + harness as a publishable Hugging Face Dataset (dataset card,
>    license, loading script) — actual publication to the HF Hub is a HUMAN
>    GATE (account + token + trigger).
> 2. **Deploy prep — target a major cloud (skills matrix: cloud, Docker,
>    SQL, CI/CD).** Migrate storage SQLite → Postgres behind a config flag
>    (SQLAlchemy already in the stack; keep SQLite as the local default),
>    add magic-link/email auth so memory and plans persist per user, add
>    per-user rate limits + call caps with the mock-LLM fallback as the cost
>    floor. Deploy the existing Docker images to the chosen cloud — default
>    proposal: Azure Container Apps + managed Postgres (Neon acceptable);
>    alternative: GCP Cloud Run (cheapest) or AWS App Runner — and extend
>    GitHub Actions into a full CI/CD pipeline: build → pytest → safety
>    benchmark (must be 0 violations to pass) → push image → deploy to a
>    staging revision, with production promotion as a manual approval step.
>    HUMAN GATE: cloud choice + account credentials, Postgres provider, and
>    auth/email provider come from docs/HUMAN_INPUTS.md — build against the
>    defaults with all values read from .env / repo-secret placeholders.
> 3. **Analytics.** Instrument events: request completed, plan generated,
>    thumbs up/down, return visit. Provider key is a human input; ship with
>    a no-op fallback when the key is absent. Verify Streamlit is usable on
>    mobile viewport sizes and fix low-hanging issues only.
> 4. **Soft-launch kit.** Draft the Show HN post, the r/MealPrepSunday and
>    macro-community posts, led by the benchmark story. Posting is a HUMAN
>    GATE — deliver drafts only.
>
> Advisor review on every item; additionally request a single pre-deploy
> review (MODE: REVIEW) of the whole deploy surface (auth, rate limiting,
> secrets handling, data isolation between users) before declaring the phase
> ready. Finish with phase-exit evidence: benchmark table, load-test result
> at modest concurrency, analytics events verified, NEEDS HUMAN list
> (deploy trigger, keys, screenshots/demo GIF for the README).

---

## Batch 3 — Phase 3: differentiation features

> Read CLAUDE.md and docs/ROADMAP.md (Phase 3). Execute autonomously:
>
> 1. **"Remaining macros" mode.** Reverse-macro solving: remaining kcal/
>    protein/carbs/fat + pantry → closest-fit meal. Consult the advisor on
>    the fit metric and solver approach first. Gate: fit-error metric over a
>    test set within the tolerance target (≤10% kcal/protein deviation).
>    Design the input so MyFitnessPal/Cronometer/MacroFactor export import
>    can be added later without schema changes.
> 2. **Deterministic substitution engine.** This is a designated advisor
>    consult: substitution-graph safety semantics (allergen-safe swaps,
>    e.g. sunflower-seed butter for peanut butter; Greek yogurt ↔ sour
>    cream) with macro deltas computed from the USDA module. The LLM must
>    have no role in choosing substitutions. Extend the adversarial
>    benchmark with substitution-attack cases; violation rate must stay 0.
> 3. **Visible personalization loop — as a real learned ranker (skills
>    matrix: scikit-learn, ML fundamentals, MLflow).** Consult the advisor
>    on the formulation, then replace/augment the heuristic preference
>    adjustment with a scikit-learn model (start simple: logistic
>    regression or gradient-boosted trees over recipe/user features built
>    from thumbs feedback) that re-ranks the ALREADY SAFETY-FILTERED
>    shortlist. Requirements: feature pipeline with Pydantic contracts;
>    proper offline evaluation (train/test split, stated metric — e.g.
>    AUC and NDCG@k vs. the heuristic baseline); cold-start fallback to
>    the heuristic when a user has too little feedback; training runs and
>    metrics tracked in MLflow (local file backend is fine) with the
>    served model versioned. The ranker is advisory only — it never
>    touches the safety filter. UI: learned taste profile, auto-avoided
>    ingredients, drifting cuisine preferences, visibly changing output.
>    Gate: before/after eval showing feedback measurably shifts
>    recommendations AND the ranker beating the heuristic offline.
> 4. **Cost estimation v1.** Rough ingredient-price table → per-meal and
>    per-week estimates with pantry-already-covered amounts. Price data
>    source and its license go through the license HUMAN GATE if external.
>
> Advisor review per item; benchmark re-run at the end of the batch.
> Finish with gate numbers, NEEDS HUMAN list, backlog.

---

## Batch 3.5 — ML depth layer (deep learning, Hugging Face, NLP, MLOps)

> Read CLAUDE.md (note the "ML components are advisory only" rule),
> docs/ROADMAP.md, and docs/SKILLS_MATRIX.md. This batch exists to add
> genuinely useful ML components that also demonstrate PyTorch, Hugging
> Face, NLP, unsupervised learning, and MLOps. Every model is advisory
> only and ships with an offline eval. Execute autonomously:
>
> 1. **Fine-tune the retrieval embeddings (PyTorch + Hugging Face + DL).**
>    Consult the advisor on the training design first. Build a training set
>    of (query → relevant recipe) pairs from the corpus + the ~50-query
>    retrieval eval's methodology (keep eval queries held out), then
>    contrastively fine-tune the sentence-transformers embedding model
>    (PyTorch; CPU-viable on a small model — a GPU is an optional human
>    input). Gate: the fine-tuned model must beat the off-the-shelf
>    embeddings on the held-out retrieval eval; otherwise keep the baseline
>    and document the negative result honestly in the skills matrix.
>    Track runs/params/metrics in MLflow; pushing the model to the HF Hub
>    is a HUMAN GATE. Wire model choice through config with the current
>    model as fallback.
> 2. **Allergen-suspect classifier (NLP + scikit-learn or small PyTorch
>    model).** A corpus-QA layer that flags recipes whose text suggests an
>    allergen their metadata doesn't declare (e.g. "satay" without a peanut
>    tag) — surfacing metadata errors, which is the real residual risk in
>    the safety chain. Train on the corpus's declared allergen tags with a
>    proper split; report precision/recall per allergen class; track in
>    MLflow. STRICTLY advisory: flagged recipes go into a review report and
>    can be conservatively quarantined by a DETERMINISTIC rule the human
>    approves — the classifier itself never admits or rejects anything.
> 3. **Recipe clustering (unsupervised ML).** Cluster recipe embeddings
>    (e.g. k-means/HDBSCAN with a stated selection method and silhouette
>    or similar quality metric) and use the clusters for two real features:
>    dedup assistance in the import pipeline and an "explore similar"
>    facet in the UI. Notebook or script with clear methodology, tracked
>    in MLflow.
> 4. **Update docs/SKILLS_MATRIX.md and the README** with what landed,
>    the metrics, and one-line "where to look in the code" pointers.
>
> Advisor review per item; benchmark + demo eval re-run at batch end.
> Finish with gate numbers, NEEDS HUMAN list, backlog.

---

## Batch 4 — Phase 4: retention & planning systems

> Read CLAUDE.md and docs/ROADMAP.md (Phase 4). Execute autonomously,
> strictly in this order (each builds on the last):
>
> 1. **Meal-prep batch solver.** 2–3 recipes sharing ingredients, scaled to
>    N containers hitting per-container kcal/protein targets, one
>    consolidated quantity-aware shopping list. Advisor consult on the
>    optimization formulation first (this exercises per-serving scaling).
> 2. **Full weekly meal-plan solver.** Pantry + budget + macro goals +
>    N meals → plan maximizing pantry utilization, sharing ingredients,
>    sequencing perishables first, one costed shopping list. This is a
>    designated Fable 5 design item — the advisor consult on the
>    optimization design is mandatory and should happen before any code.
>    Gate: shopping-list quantities reconcile EXACTLY against plan
>    requirements minus pantry; add property-style tests for this.
> 3. **Expiry / waste tracking.** Purchase dates for perishables + "use your
>    spinach today — 3 ways" nudges. Gate: waste metric (% perishables
>    consumed within plan window) computed in the eval.
> 4. **Shareable plan URLs.** Public share links for plans/recipes. Advisor
>    must review the privacy surface: share links expose ONLY the shared
>    plan, never profile, allergy, or library data; unguessable IDs.
>
> Advisor review per item; full benchmark + demo eval re-run at batch end.
> Finish with gate numbers, NEEDS HUMAN list, backlog.

---

## Batch 5 — Phase 5: final product & platform play

> Read CLAUDE.md and docs/ROADMAP.md (Phase 5). Execute autonomously:
>
> 1. **Mobile-quality frontend.** HUMAN GATE up front: framework choice
>    (docs/HUMAN_INPUTS.md — default proposal: Next.js + Tailwind consuming
>    the existing FastAPI). Build against the approved choice; keep
>    Streamlit alive until parity. Prioritize the flows Phase 2–4 analytics
>    show are most used.
> 2. **Constraint engine as API + MCP server.** Expose food-safety filtering
>    and macro scoring as documented public API endpoints and as an MCP
>    server ("safety infrastructure for food AI"). Advisor consult on the
>    tool surface design; rate-limit and key-gate the public endpoints.
> 3. **Vision, done properly (only if analytics show demand — otherwise
>    skip and say so).** Prerequisite first: replace the silent mock
>    fallback in `app/services/model_provider.py`
>    (`extract_inventory_with_provider_chain`) with explicit user-visible
>    degradation. Then wire one real vision provider with validated
>    structured output. Vision output still never touches allergy or
>    nutrition decisions.
> 4. **v2 launch kit.** Draft the Show HN follow-up, solver-design blog
>    post, and benchmark/dataset release notes. Publishing is a HUMAN GATE.
> 5. **(Optional stretch, skills matrix: Kubernetes.)** If the human opts
>    in via docs/HUMAN_INPUTS.md, add k8s manifests (or a minimal Helm
>    chart) for the API + frontend with health/readiness probes and
>    resource limits, verified on a local kind/minikube cluster in CI.
>    Skip cleanly if not opted in — do not add k8s complexity by default.
>
> Before declaring the phase done, request the advisor's designated
> pre-launch safety review (MODE: REVIEW) covering: benchmark-in-CI status,
> the full deterministic/LLM boundary, public API abuse surface, and
> secrets/PII handling. Finish with north-star metric instrumentation
> confirmed, NEEDS HUMAN list, backlog.
