# SKILLS_MATRIX.md — JD requirements → where MacroChef demonstrates them

Living document. The orchestrator updates the Status column as batches land.
Use this for the README's "skills demonstrated" section and for interview prep
("where in the code is X?").

Legend: ✅ already in the repo · 🔨 lands in the named batch · ⚪ optional /
opt-in · ❌ not viable in this project (and why).

| # (freq) | JD requirement | Status | Where in MacroChef |
|---|---|---|---|
| 1 (14/15) | Python | ✅ | Entire codebase — typed, Pydantic v2, tested with pytest |
| 2 (13/15) | LLMs / GenAI APIs (GPT/Claude/Gemini) | ✅ | Multi-provider router (`model_provider.py`): mock/Gemini/OpenAI/Claude/Ollama with ordered fallbacks; Batch 2 benchmark calls all three major APIs |
| 3 (~12/15) | ML fundamentals (supervised/unsupervised, evaluation) | 🔨 3 + 3.5 | Supervised: learned feedback ranker with train/test split, AUC/NDCG (Batch 3); allergen-suspect classifier with per-class precision/recall (3.5). Unsupervised: recipe clustering with quality metrics (3.5) |
| 4 (~9/15) | Scikit-learn / TensorFlow / **PyTorch** | 🔨 3 + 3.5 | scikit-learn: ranker + classifier. PyTorch: contrastive fine-tune of the sentence-transformers embedding model (3.5). TensorFlow: ❌ deliberately — one DL framework, used well |
| 6 (~8/15) | Cloud (AWS / **Azure** / GCP) | 🔨 2 | Containerized deploy to Azure Container Apps (default; Cloud Run/App Runner alternatives), staging + manual prod promotion |
| 7 (7/15) | SQL / relational DBs | ✅→🔨 2 | SQLAlchemy + SQLite today; managed Postgres migration with config-flagged backend in Batch 2 |
| 9 (~5/15) | API development (REST, **FastAPI**) | ✅ | FastAPI backend, documented endpoints (`/recipes/recommend`, `/library/*`); public constraint-engine API in Batch 5 |
| 10 (~5/15) | Deep learning | 🔨 3.5 | Embedding fine-tune (contrastive learning, held-out eval vs. baseline) |
| 11 (4/15) | Git / version control | ✅ | Branch-per-item workflow, PR discipline, commit messages tied to roadmap items |
| 12 (4/15) | Docker | ✅→🔨 2 | docker-compose local stack today; images built/pushed/deployed by CI/CD in Batch 2 |
| 13 (4/15) | Prompt engineering | ✅→🔨 2 | Structured-output prompts behind validation in the provider layer; the Batch 2 adversarial benchmark IS a prompt-robustness study (documented methodology) |
| 14 (4/15) | LLM/agent frameworks (**LangGraph**, LangChain…) | ✅ | Two LangGraph workflows (planner + library builder) with conditional edges and Pydantic node contracts |
| 15 (4/15) | AI agents / agentic workflows | ✅ | The product itself + the multi-agent Claude Code build process (orchestrator/executor/reviewer, documented in CLAUDE.md) |
| 16 (3/15) | RAG (chunking, vector DBs, retrieval) | ✅ | ChromaDB + embeddings + keyword fallback; RAG-vs-keyword eval on ~50 queries made valid in Batch 1.5 |
| 17 (3/15) | NLP | ✅→🔨 3.5 | Fuzzy ingredient normalization today; allergen-suspect text classifier in 3.5 |
| 18 (3/15) | Hugging Face | 🔨 2 + 3.5 | Benchmark published as an HF Dataset (2); fine-tuned embedding model on the HF Hub (3.5) |
| 19 (3/15) | Pandas / NumPy | ✅ | Corpus import/validation pipeline, grounding reports, eval scripts |
| 20 (3/15) | MLOps / MLflow | 🔨 3 + 3.5 | MLflow tracking for ranker, classifier, and fine-tune runs; versioned served models; benchmark-in-CI as a release gate |
| 21 (2/15) | CI/CD | ✅→🔨 2 | GitHub Actions CI today; full pipeline in Batch 2: build → tests → safety benchmark gate → image push → staged deploy → manual prod promotion |
| 21 (2/15) | Kubernetes | ⚪ 5 | Opt-in stretch: manifests/Helm verified on kind in CI |
| 22 (1/15) | Computer vision | ⚪ 5 | Real vision provider with validated structured output, only if analytics show demand |
| 22 (1/15) | Explainable AI | ✅ | Core thesis: safety/nutrition decisions are deterministic and fully inspectable (debug trace, rejected-recipes list); LLM confined to phrasing |
| 5, 8 | STEM degree, English B2+ | — | Not project artifacts (though the README/blog/benchmark writeups evidence written English) |
| 22 | Databricks, Spark, Airflow, Terraform, Kafka, Ray, vLLM, diffusion, HPC, Neo4j/ClickHouse | ❌ | Data volume (~5k recipes) and architecture don't justify them; bolting them on would read as padding. Terraform is the only one worth revisiting if the Azure deploy grows |

## The interview narrative this matrix supports

- **Safety-first system design:** "the LLM never enforces allergies" +
  published adversarial benchmark with 0 violations in CI.
- **Full lifecycle:** data ingestion (Kaggle/USDA) → validation → RAG →
  learned ranking → evaluation → MLflow → containerized cloud deploy →
  CI/CD gate → analytics-driven prioritization.
- **Honest ML practice:** held-out evals, baselines that must be beaten,
  negative results documented rather than hidden, models advisory-only in
  a safety-critical path.
