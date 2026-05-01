from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation.eval_recommendations import summarize_response  # noqa: E402
from app.graph.builder import run_recommendation_graph  # noqa: E402
from app.schemas.recommendation import RecommendationRequest  # noqa: E402
from app.schemas.user import MacroTargets, UserProfile  # noqa: E402


def _profile(
    allergies: list[str] | None = None,
    diet_type: str | None = None,
    cuisine: str | None = None,
    max_time: int = 35,
) -> UserProfile:
    return UserProfile(
        user_id="demo_user",
        allergies=allergies or [],
        disliked_ingredients=[],
        diet_type=diet_type,
        preferred_cuisines=[cuisine] if cuisine else [],
        macro_targets=MacroTargets(calories=600, protein_g=45, carbs_g=60, fat_g=20, fiber_g=9),
        max_cook_time_min=max_time,
    )


def scenarios() -> list[RecommendationRequest]:
    return [
        RecommendationRequest(
            user_id="demo_user",
            input_type="text",
            typed_ingredients="chicken breast, spinach, rice, bell pepper, Greek yogurt",
            user_profile=_profile(cuisine="Mediterranean"),
            cuisine_preference="Mediterranean",
            meal_type="dinner",
        ),
        RecommendationRequest(
            user_id="demo_user",
            input_type="text",
            typed_ingredients="tofu, rice noodles, broccoli, bell pepper",
            user_profile=_profile(allergies=["peanut"], cuisine="Thai"),
            cuisine_preference="Thai",
            meal_type="dinner",
        ),
        RecommendationRequest(
            user_id="demo_user",
            input_type="text",
            typed_ingredients="brown rice, black beans, corn, avocado, tomato",
            user_profile=_profile(diet_type="vegan", cuisine="Mexican", max_time=30),
            cuisine_preference="Mexican",
            meal_type="lunch",
        ),
        RecommendationRequest(
            user_id="demo_user",
            input_type="text",
            typed_ingredients="lentils, spinach, tomato, onion, rice",
            user_profile=_profile(allergies=["dairy"], cuisine="Indian"),
            cuisine_preference="Indian",
            meal_type="dinner",
        ),
    ]


def main() -> None:
    metric_rows: list[dict[str, float]] = []
    for index, request in enumerate(scenarios(), start=1):
        response = run_recommendation_graph(request)
        row = summarize_response(response, request.user_profile)
        metric_rows.append(row)
        print(f"\nScenario {index}: {request.cuisine_preference or 'Any'}")
        print(f"Recommendations: {[item.recipe.title for item in response.recommendations]}")
        for metric, value in row.items():
            print(f"  {metric}: {value:.3f}")

    print("\nAggregate report")
    for metric in metric_rows[0]:
        print(f"{metric}: {statistics.mean(row[metric] for row in metric_rows):.3f}")


if __name__ == "__main__":
    main()
