# Evaluation

MacroChef Agent evaluates recommendation quality with deterministic metrics over demo scenarios.

## Metrics

**Allergy violation rate**  
The fraction of recommended recipes that fail deterministic validation. Target: `0`.

**Pantry utilization rate**  
Average pantry match score across recommended recipes.

**Macro deviation**  
Average `1 - macro_fit_score`. Lower is better.

**Missing ingredient count**  
Average number of missing ingredients per recommended recipe.

**Recommendation validity rate**  
The fraction of recommended recipes that pass all hard constraints.

## Run

```bash
python scripts/evaluate_demo_set.py
```

The script runs multiple scenarios, prints per-scenario metrics, and then prints aggregate averages.
