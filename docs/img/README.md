# docs/img — demo GIFs (ROADMAP.md Step 6.3)

**No GIFs exist in this checkout yet — this is an honest placeholder, not a
broken link.** Screen recording needs a human at a real browser; matches the
same `TODO(human)` convention the main `README.md` already uses for its own
hero demo capture (`docs/media/demo.gif`, a single README-level clip — a
separate, pre-existing placeholder from the three below, which back
`docs/DEMO_SCRIPT.md`'s individual steps specifically).

Three recordings this step calls for, in the order `docs/DEMO_SCRIPT.md`
walks through them:

1. **`streaming-run.gif`** — the live agent-progress timeline (`/plan`,
   `RunProgressTimeline`) filling in row by row during a real
   `POST /recipes/recommend/stream` run. ~15-20s, captures the point of
   ROADMAP 3.1/4.2: no spinner, visible reasoning.
2. **`chat-tool-calls.gif`** — `/chat`, a full turn: the profile gate, a
   message being sent, tool-call chips appearing live (`🔍 search_recipes`
   then `🛡 check_recipe_safety`), one chip expanded to show its result, the
   final answer landing. ~20-30s, the flagship feature (ROADMAP 3.3/4.3).
3. **`evals-page.gif`** — `/evals`, a short pan across the safety-benchmark
   and retrieval numbers. ~10s, backs up `docs/CASE_STUDY.md`'s "receipts,
   not vibes" framing.

Once captured, embed each where `docs/DEMO_SCRIPT.md`/`README.md` currently
has a prose-only step, and delete the corresponding bullet above.
