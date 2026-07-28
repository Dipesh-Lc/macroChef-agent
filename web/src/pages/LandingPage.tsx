import { Link } from "react-router-dom";

const GITHUB_REPO_URL = "https://github.com/Dipesh-Lc/macroChef-agent";

/**
 * ROADMAP 4.1: the cold-visit landing page. Route `/`; the dense planner
 * form moved to `/plan` (see `main.tsx`). Everything below is static
 * marketing copy + navigation -- no data fetching, no safety/nutrition
 * logic, matching the "honest kitchen ledger" tokens in `index.css`.
 */

/**
 * Proof-chip numbers must always be read from the same source the README
 * publishes (`data/evaluation/` via `scripts/verify_benchmark_evidence.py`),
 * per CLAUDE.md's release-gate semantics: the adjudicated number is
 * reported ALONGSIDE the raw judge-flagged count, never in place of it.
 * Current verified status (commit 0840e60, see README "Adversarial safety
 * benchmark"): adjudicated-true violations 0/269, raw judge flags 73/269.
 * Update both numbers together if a newer verified run changes them --
 * never round up the adjudicated count without re-running
 * `scripts/verify_benchmark_evidence.py`.
 */
const SAFETY_HEADLINE = "0 / 269 adjudicated violations";
const SAFETY_SUBLINE = "73 raw judge flags, every one traced to a known artifact — see the methodology";

/**
 * Human-readable labels for the recommend graph's node sequence
 * (`app/graph/builder.py`, in wiring order). `fallback_relaxation` is
 * conditional (only runs when the safety filter leaves too few
 * candidates), so it's rendered with a dashed border rather than a solid
 * one to signal "not every run takes this step."
 */
const PIPELINE_STEPS: { id: string; label: string; description: string; conditional?: boolean }[] = [
  { id: "intake", label: "Intake", description: "Reads your pantry text (or photo)" },
  {
    id: "inventory_confirmation",
    label: "Inventory confirmation",
    description: "Flags low-confidence items for you to confirm",
  },
  {
    id: "constraint_builder",
    label: "Constraint builder",
    description: "Compiles allergies, diet, and macro targets into rules",
  },
  {
    id: "recipe_retriever",
    label: "Recipe retrieval",
    description: "Searches the grounded recipe corpus for candidates",
  },
  {
    id: "safety_filter",
    label: "Safety filter",
    description: "Deterministically rejects anything that violates a rule",
  },
  {
    id: "fallback_relaxation",
    label: "Fallback relaxation",
    description: "Widens the search only if too few candidates survive",
    conditional: true,
  },
  {
    id: "substitution",
    label: "Substitution",
    description: "Proposes swaps for unsafe or missing ingredients",
  },
  {
    id: "nutrition_scoring",
    label: "Nutrition scoring",
    description: "Grounds macros against USDA FoodData Central",
  },
  {
    id: "meal_ranking",
    label: "Meal ranking",
    description: "Ranks by pantry fit, macro fit, time, and preference",
  },
  { id: "procurement", label: "Procurement", description: "Builds the shopping list for what's missing" },
  {
    id: "memory_update",
    label: "Memory update",
    description: "Updates your taste profile from this run",
  },
];

interface ProofChip {
  label: string;
  detail: string;
  href: string;
  external: boolean;
}

const PROOF_CHIPS: ProofChip[] = [
  {
    label: `Deterministic allergy safety — ${SAFETY_HEADLINE}`,
    detail: SAFETY_SUBLINE,
    href: "/evals",
    external: false,
  },
  {
    label: "USDA-grounded macros",
    detail: "Nutrition comes from ingredient grams matched to USDA FoodData Central, never recipe tags",
    href: `${GITHUB_REPO_URL}#3-usda-grounded-nutrition`,
    external: true,
  },
  {
    label: "Watch the agent think",
    detail: "Live step-by-step streaming is on the roadmap — today, expand “Debug” after a run",
    href: "/plan",
    external: false,
  },
];

function ProofChipCard({ chip }: { chip: ProofChip }) {
  const content = (
    <>
      <span className="font-mono text-sm font-semibold text-cast-iron">{chip.label}</span>
      <span className="text-xs text-cast-iron/60">{chip.detail}</span>
    </>
  );
  const className =
    "flex flex-col gap-1 rounded-lg border border-sage-line bg-white px-4 py-3 text-left transition-colors hover:border-basil hover:bg-basil/5";

  if (chip.external) {
    return (
      <a href={chip.href} target="_blank" rel="noreferrer" className={className}>
        {content}
      </a>
    );
  }
  return (
    <Link to={chip.href} className={className}>
      {content}
    </Link>
  );
}

function PipelineDiagram() {
  return (
    <div className="overflow-x-auto pb-2">
      <ol className="flex min-w-max items-stretch gap-2">
        {PIPELINE_STEPS.map((step, index) => (
          <li key={step.id} className="flex items-stretch gap-2">
            <div
              className={`flex w-44 flex-col gap-1 rounded-lg border bg-white px-3 py-3 ${
                step.conditional ? "border-dashed border-honey-dark" : "border-sage-line"
              }`}
            >
              <span className="font-mono text-xs text-cast-iron/40">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="font-display text-sm font-semibold text-cast-iron">{step.label}</span>
              <span className="text-xs text-cast-iron/60">{step.description}</span>
              {step.conditional && (
                <span className="text-[0.65rem] font-medium uppercase tracking-wide text-honey-dark">
                  Conditional
                </span>
              )}
            </div>
            {index < PIPELINE_STEPS.length - 1 && (
              <span aria-hidden="true" className="flex items-center text-cast-iron/30">
                &rarr;
              </span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="flex flex-col gap-16 py-6">
      <section className="flex flex-col items-start gap-6">
        <span className="font-mono text-xs font-semibold uppercase tracking-widest text-basil">
          MacroChef
        </span>
        <h1 className="max-w-3xl font-display text-4xl font-semibold leading-tight text-cast-iron sm:text-5xl">
          Meal planning that never hides its own uncertainty.
        </h1>
        <p className="max-w-2xl text-base text-cast-iron/70 sm:text-lg">
          Tell it what's in your kitchen. A deterministic constraint engine — never the
          language model — decides what's safe to eat, and every macro number is grounded
          against USDA FoodData Central before it reaches you.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/plan"
            className="rounded-md bg-cast-iron px-5 py-2.5 text-sm font-semibold text-porcelain transition-colors hover:bg-cast-iron/90"
          >
            Try the planner
          </Link>
          <Link
            to="/chat"
            className="rounded-md border border-sage-line px-5 py-2.5 text-sm font-semibold text-cast-iron transition-colors hover:bg-sage-line/40"
          >
            Chat with Chef
          </Link>
        </div>

        <div className="grid w-full gap-3 sm:grid-cols-3">
          {PROOF_CHIPS.map((chip) => (
            <ProofChipCard key={chip.label} chip={chip} />
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <div>
          <h2 className="font-display text-2xl font-semibold text-cast-iron">How it works</h2>
          <p className="max-w-2xl text-sm text-cast-iron/70">
            Every recommendation runs through this exact LangGraph pipeline — the same
            eleven nodes, in this order, every time. Scroll right to see the whole run.
          </p>
        </div>
        <PipelineDiagram />
      </section>

      <footer className="flex flex-col gap-3 border-t border-sage-line pt-6 text-sm text-cast-iron/70">
        <div className="flex flex-wrap items-center gap-4">
          <a
            href={GITHUB_REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-cast-iron underline underline-offset-2 hover:text-basil"
          >
            View on GitHub
          </a>
          <span className="font-mono text-xs text-cast-iron/50">
            Safety benchmark: {SAFETY_HEADLINE}
          </span>
          <Link
            to="/evals"
            className="font-medium text-cast-iron underline underline-offset-2 hover:text-basil"
          >
            Read the eval methodology
          </Link>
        </div>
        <p className="text-xs text-cast-iron/50">
          The LLM never enforces allergies or computes nutrition. Deterministic code does.
        </p>
      </footer>
    </div>
  );
}
