# ruff: noqa: E501

from dataclasses import dataclass
from itertools import cycle
from uuid import NAMESPACE_URL, uuid5

from app.schemas.library import RecipeDiscoveryRequest
from app.schemas.recipe_candidate import RecipeCandidate
from app.services.recipe_generation_service import RecipeGenerationService
from app.services.recipe_image_service import placeholder_image_url
from app.services.recipe_import_service import RecipeImportService
from app.utils.ingredient_normalizer import ingredient_matches


@dataclass(frozen=True)
class MockRecipeTemplate:
    title: str
    ingredients: list[str]
    instructions: list[str]
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    cook_time_min: int
    allergens: list[str]
    diet_tags: list[str]
    equipment: list[str]
    description: str


MOCK_LIBRARY: dict[str, list[MockRecipeTemplate]] = {
    "Italian": [
        MockRecipeTemplate(
            "Chicken Tomato Basil Pasta",
            ["140 g chicken breast", "85 g whole wheat pasta", "120 g tomato", "8 g basil", "8 g olive oil"],
            ["Boil pasta until al dente.", "Sear chicken with olive oil.", "Simmer tomato and basil, then toss everything together."],
            610,
            48,
            70,
            16,
            10,
            30,
            ["gluten"],
            ["high-protein"],
            ["stovetop", "pot", "skillet"],
            "A weeknight pasta with lean chicken, tomato, and basil.",
        ),
        MockRecipeTemplate(
            "Turkey Spinach Meatballs",
            ["160 g ground turkey", "1 medium egg", "25 g parmesan", "80 g spinach", "150 g tomato sauce"],
            ["Mix turkey, egg, parmesan, and chopped spinach.", "Bake meatballs until cooked through.", "Warm tomato sauce and serve together."],
            520,
            50,
            28,
            22,
            6,
            35,
            ["egg", "dairy"],
            ["high-protein", "gluten-free"],
            ["oven", "mixing bowl"],
            "Simple baked turkey meatballs with spinach and tomato sauce.",
        ),
        MockRecipeTemplate(
            "Tuscan White Bean Skillet",
            ["180 g white beans", "100 g zucchini", "120 g tomato", "60 g spinach", "8 g olive oil"],
            ["Saute zucchini in olive oil.", "Add tomato and white beans.", "Fold in spinach and simmer briefly."],
            430,
            20,
            56,
            13,
            15,
            22,
            [],
            ["vegetarian", "vegan", "dairy-free", "gluten-free", "high-fiber"],
            ["skillet"],
            "A fast plant-forward skillet with beans and vegetables.",
        ),
        MockRecipeTemplate(
            "Lemon Garlic Shrimp Pasta",
            ["140 g shrimp", "80 g pasta", "1 lemon", "8 g garlic", "10 g olive oil"],
            ["Cook pasta.", "Saute shrimp with garlic.", "Toss with lemon juice and olive oil."],
            540,
            38,
            62,
            15,
            5,
            24,
            ["shellfish", "gluten"],
            ["high-protein", "dairy-free"],
            ["stovetop", "skillet", "pot"],
            "Bright shrimp pasta with lemon and garlic.",
        ),
        MockRecipeTemplate(
            "Caprese Chicken Rice Bowl",
            ["150 g chicken breast", "140 g cooked rice", "80 g tomato", "40 g mozzarella", "8 g basil"],
            ["Cook rice.", "Sear chicken.", "Layer rice, chicken, tomato, mozzarella, and basil."],
            590,
            51,
            54,
            18,
            4,
            28,
            ["dairy"],
            ["high-protein", "gluten-free"],
            ["stovetop"],
            "Caprese flavors turned into a home-cookable rice bowl.",
        ),
    ],
    "Indian": [
        MockRecipeTemplate(
            "Chicken Tikka Rice Bowl",
            ["150 g chicken breast", "140 g cooked basmati rice", "70 g Greek yogurt", "80 g cucumber", "1 lemon"],
            ["Marinate chicken in yogurt and spices.", "Sear chicken.", "Serve over rice with cucumber and lemon."],
            585,
            55,
            56,
            13,
            5,
            32,
            ["dairy"],
            ["high-protein", "gluten-free"],
            ["skillet"],
            "A lighter tikka-style bowl with rice and cucumber.",
        ),
        MockRecipeTemplate(
            "Chana Masala",
            ["190 g chickpea", "120 g tomato", "70 g onion", "8 g garlic", "5 g ginger"],
            ["Saute onion, garlic, and ginger.", "Add tomato and spices.", "Simmer chickpeas until saucy."],
            470,
            20,
            68,
            12,
            17,
            30,
            [],
            ["vegetarian", "vegan", "dairy-free", "gluten-free", "high-fiber"],
            ["stovetop", "pot"],
            "A pantry-friendly chickpea curry.",
        ),
        MockRecipeTemplate(
            "Paneer Pepper Stir Fry",
            ["140 g paneer", "120 g bell pepper", "80 g onion", "100 g tomato", "120 g cooked rice"],
            ["Sear paneer cubes.", "Stir fry peppers and onion.", "Add tomato and serve with rice."],
            640,
            32,
            62,
            28,
            8,
            27,
            ["dairy"],
            ["vegetarian", "gluten-free"],
            ["skillet"],
            "A quick vegetarian paneer and pepper skillet.",
        ),
        MockRecipeTemplate(
            "Lentil Dal with Spinach",
            ["170 g red lentils", "80 g spinach", "80 g onion", "8 g garlic", "120 g cooked rice"],
            ["Simmer lentils with onion and garlic.", "Stir in spinach.", "Serve with rice."],
            520,
            27,
            78,
            9,
            18,
            33,
            [],
            ["vegetarian", "vegan", "dairy-free", "gluten-free", "high-fiber"],
            ["pot"],
            "Comforting dal with spinach and rice.",
        ),
        MockRecipeTemplate(
            "Turkey Keema Bowl",
            ["160 g ground turkey", "100 g peas", "120 g tomato", "80 g onion", "130 g cooked basmati rice"],
            ["Brown turkey with onion.", "Add tomato, peas, and spices.", "Serve over rice."],
            570,
            45,
            58,
            16,
            8,
            28,
            [],
            ["high-protein", "dairy-free", "gluten-free"],
            ["skillet"],
            "A high-protein keema-inspired rice bowl.",
        ),
    ],
    "Japanese": [
        MockRecipeTemplate(
            "Teriyaki Chicken Rice Bowl",
            ["150 g chicken breast", "150 g cooked white rice", "90 g broccoli", "50 g carrot", "20 g soy sauce"],
            ["Cook rice.", "Sear chicken.", "Glaze with soy sauce, honey, garlic, and ginger.", "Serve with vegetables."],
            590,
            48,
            70,
            12,
            6,
            25,
            ["soy"],
            ["high-protein", "dairy-free"],
            ["skillet"],
            "A simple teriyaki-style chicken bowl.",
        ),
        MockRecipeTemplate(
            "Salmon Miso Soup Bowl",
            ["140 g salmon", "25 g miso paste", "120 g cooked brown rice", "80 g mushroom", "60 g spinach"],
            ["Simmer mushrooms.", "Whisk in miso off heat.", "Add cooked salmon and spinach.", "Serve with rice."],
            560,
            39,
            52,
            21,
            7,
            30,
            ["fish", "soy"],
            ["high-protein", "dairy-free"],
            ["pot"],
            "A cozy miso bowl with salmon, rice, and vegetables.",
        ),
        MockRecipeTemplate(
            "Tofu Soba Stir Fry",
            ["150 g tofu", "85 g soba noodles", "90 g broccoli", "60 g green onion", "18 g soy sauce"],
            ["Cook soba.", "Crisp tofu.", "Stir fry vegetables and toss with noodles."],
            520,
            29,
            64,
            16,
            9,
            24,
            ["soy", "gluten"],
            ["vegetarian", "dairy-free"],
            ["skillet", "pot"],
            "A tofu noodle stir fry for weeknights.",
        ),
        MockRecipeTemplate(
            "Chicken Yakitori Bowl",
            ["150 g chicken breast", "140 g cooked rice", "70 g green onion", "90 g cucumber", "18 g soy sauce"],
            ["Skewer or pan-sear chicken pieces.", "Brush with soy-honey glaze.", "Serve with rice and cucumber."],
            540,
            46,
            58,
            12,
            5,
            28,
            ["soy"],
            ["high-protein", "dairy-free"],
            ["skillet"],
            "Yakitori-inspired chicken without special equipment.",
        ),
        MockRecipeTemplate(
            "Egg Fried Rice Japanese Style",
            ["2 medium eggs", "180 g cooked rice", "70 g peas", "50 g carrot", "15 g soy sauce"],
            ["Scramble eggs.", "Stir fry rice and vegetables.", "Season with soy sauce."],
            500,
            23,
            65,
            16,
            6,
            18,
            ["egg", "soy"],
            ["vegetarian", "dairy-free"],
            ["skillet"],
            "A quick rice dish with eggs and vegetables.",
        ),
    ],
    "Chinese": [
        MockRecipeTemplate(
            "Chicken Broccoli Stir Fry",
            ["150 g chicken breast", "140 g broccoli", "20 g soy sauce", "8 g garlic", "120 g cooked rice"],
            ["Sear chicken.", "Stir fry broccoli and garlic.", "Add soy sauce and serve with rice."],
            540,
            47,
            55,
            12,
            7,
            22,
            ["soy"],
            ["high-protein", "dairy-free"],
            ["wok or skillet"],
            "A classic home stir fry with rice.",
        ),
        MockRecipeTemplate(
            "Mapo Tofu Inspired Bowl",
            ["180 g tofu", "120 g cooked rice", "80 g mushroom", "30 g green onion", "10 g chili bean paste"],
            ["Brown mushrooms.", "Add tofu and sauce.", "Simmer gently and serve over rice."],
            480,
            24,
            58,
            16,
            7,
            25,
            ["soy"],
            ["vegetarian", "dairy-free"],
            ["skillet"],
            "A mild home-friendly mapo-inspired tofu bowl.",
        ),
        MockRecipeTemplate(
            "Egg Tomato Rice",
            ["2 medium eggs", "180 g tomato", "140 g cooked rice", "30 g green onion", "6 g sesame oil"],
            ["Scramble eggs.", "Cook tomatoes until saucy.", "Fold eggs back in and serve over rice."],
            470,
            21,
            58,
            17,
            5,
            18,
            ["egg", "sesame"],
            ["vegetarian", "dairy-free"],
            ["skillet"],
            "A comforting egg and tomato rice plate.",
        ),
        MockRecipeTemplate(
            "Garlic Shrimp Noodles",
            ["140 g shrimp", "90 g rice noodles", "100 g bell pepper", "8 g garlic", "15 g soy sauce"],
            ["Cook noodles.", "Stir fry shrimp and garlic.", "Toss with vegetables and sauce."],
            510,
            35,
            62,
            12,
            5,
            20,
            ["shellfish", "soy"],
            ["high-protein", "dairy-free"],
            ["skillet", "pot"],
            "Fast shrimp noodles with garlic and peppers.",
        ),
        MockRecipeTemplate(
            "Turkey Lettuce Rice Bowl",
            ["160 g ground turkey", "130 g cooked rice", "80 g lettuce", "60 g carrot", "15 g soy sauce"],
            ["Brown turkey.", "Season with soy sauce and garlic.", "Serve over rice with lettuce and carrot."],
            520,
            43,
            52,
            15,
            6,
            23,
            ["soy"],
            ["high-protein", "dairy-free"],
            ["skillet"],
            "A lettuce-wrap-inspired turkey rice bowl.",
        ),
    ],
    "Mexican": [
        MockRecipeTemplate(
            "Chicken Fajita Bowl",
            ["150 g chicken breast", "120 g bell pepper", "80 g onion", "140 g cooked brown rice", "60 g avocado"],
            ["Sear chicken.", "Cook peppers and onions.", "Serve with rice, avocado, and lime."],
            620,
            52,
            64,
            17,
            13,
            30,
            [],
            ["high-protein", "dairy-free", "gluten-free"],
            ["skillet"],
            "A balanced fajita bowl with rice and avocado.",
        ),
        MockRecipeTemplate(
            "Turkey Taco Rice Bowl",
            ["160 g ground turkey", "140 g cooked rice", "90 g black beans", "80 g tomato", "40 g lettuce"],
            ["Brown turkey with taco spices.", "Warm beans.", "Layer rice, turkey, beans, tomato, and lettuce."],
            590,
            45,
            62,
            16,
            12,
            25,
            [],
            ["high-protein", "dairy-free", "gluten-free"],
            ["skillet"],
            "A simple taco-inspired rice bowl.",
        ),
        MockRecipeTemplate(
            "Black Bean Burrito Bowl",
            ["180 g black beans", "140 g cooked brown rice", "90 g corn", "80 g tomato", "60 g avocado"],
            ["Warm beans and corn.", "Layer with rice and tomato.", "Top with avocado and lime."],
            540,
            18,
            82,
            16,
            19,
            18,
            [],
            ["vegetarian", "vegan", "dairy-free", "gluten-free", "high-fiber"],
            ["stovetop"],
            "A plant-based burrito bowl with pantry staples.",
        ),
        MockRecipeTemplate(
            "Shrimp Avocado Rice Bowl",
            ["140 g shrimp", "140 g cooked rice", "70 g avocado", "80 g tomato", "1 lime"],
            ["Sear shrimp.", "Assemble rice, shrimp, avocado, and tomato.", "Finish with lime."],
            500,
            34,
            50,
            18,
            9,
            18,
            ["shellfish"],
            ["high-protein", "dairy-free", "gluten-free"],
            ["skillet"],
            "A quick shrimp bowl with fresh avocado.",
        ),
        MockRecipeTemplate(
            "Chicken Salsa Skillet",
            ["150 g chicken breast", "130 g salsa", "90 g black beans", "80 g corn", "100 g cooked rice"],
            ["Sear chicken.", "Simmer with salsa, beans, and corn.", "Serve over rice."],
            560,
            50,
            60,
            10,
            11,
            24,
            [],
            ["high-protein", "dairy-free", "gluten-free"],
            ["skillet"],
            "A one-pan salsa chicken meal.",
        ),
    ],
}


class RecipeDiscoveryService:
    def __init__(
        self,
        generation_service: RecipeGenerationService | None = None,
        import_service: RecipeImportService | None = None,
    ):
        self.generation_service = generation_service or RecipeGenerationService()
        self.import_service = import_service or RecipeImportService()
        self.warnings: list[str] = []

    def discover(self, request: RecipeDiscoveryRequest) -> list[RecipeCandidate]:
        if request.source_mode == "llm":
            return self._llm_or_mock(request)
        if request.source_mode == "external":
            return self._external_or_llm_or_mock(request)
        if request.source_mode == "hybrid":
            candidates: list[RecipeCandidate] = []
            try:
                candidates.extend(self.import_service.import_candidates(request))
            except Exception as exc:
                self.warnings.append(f"External import failed in hybrid mode. Details: {exc}")
            try:
                candidates.extend(self.generation_service.generate(request))
            except Exception as exc:
                self.warnings.append(f"LLM generation failed in hybrid mode. Details: {exc}")
            if len(candidates) < request.count:
                candidates.extend(self._mock_candidates(request))
            return self._ensure_candidates(request, candidates)[: request.count]
        return self._ensure_candidates(request, self._mock_candidates(request))

    def _external_or_llm_or_mock(self, request: RecipeDiscoveryRequest) -> list[RecipeCandidate]:
        try:
            candidates = self.import_service.import_candidates(request)
            if candidates:
                return candidates[: request.count]
            self.warnings.append("External import returned no candidates; trying LLM fallback.")
        except Exception as exc:
            self.warnings.append(f"External import failed; trying LLM fallback. Details: {exc}")
        return self._llm_or_mock(request)

    def _llm_or_mock(self, request: RecipeDiscoveryRequest) -> list[RecipeCandidate]:
        try:
            candidates = self.generation_service.generate(request)
            if candidates:
                return candidates[: request.count]
            self.warnings.append("LLM generation returned no candidates; mock fallback was used.")
        except Exception as exc:
            self.warnings.append(f"LLM generation failed; mock fallback was used. Details: {exc}")
        return self._ensure_candidates(request, self._mock_candidates(request))

    def _ensure_candidates(
        self,
        request: RecipeDiscoveryRequest,
        candidates: list[RecipeCandidate],
    ) -> list[RecipeCandidate]:
        if candidates:
            return candidates[: request.count]

        relaxed_request = request.model_copy(
            update={
                "diet_type": None,
                "max_cook_time_min": None,
                "excluded_ingredients": [],
            }
        )
        relaxed = self._mock_candidates(relaxed_request)
        if relaxed:
            self.warnings.append(
                "No recipes matched all discovery filters; returned relaxed mock candidates."
            )
        return relaxed[: request.count]

    def _mock_candidates(self, request: RecipeDiscoveryRequest) -> list[RecipeCandidate]:
        cuisines = request.cuisines or list(MOCK_LIBRARY)
        template_pairs = [
            (cuisine.title(), template)
            for cuisine in cuisines
            for template in [
                *MOCK_LIBRARY.get(cuisine.title(), []),
                *self._generic_templates(cuisine),
            ]
        ]
        candidates: list[RecipeCandidate] = []
        for index, (cuisine, template) in enumerate(
            cycle(template_pairs),
            start=1,
        ):
            candidate = self._candidate_from_template(cuisine.title(), template, request, index)
            if self._allowed(candidate, request):
                candidates.append(candidate)
            if len(candidates) >= request.count or index > request.count * 10:
                break
        return candidates[: request.count]

    def _candidate_from_template(
        self,
        cuisine: str,
        template: MockRecipeTemplate,
        request: RecipeDiscoveryRequest,
        index: int,
    ) -> RecipeCandidate:
        title = template.title
        if index > len(MOCK_LIBRARY.get(cuisine, [])):
            title = template.title
        cook_time = template.cook_time_min
        if request.max_cook_time_min:
            cook_time = min(cook_time, max(10, request.max_cook_time_min))
        difficulty = request.difficulty or ("easy" if cook_time <= 30 else "medium")
        meal_type = request.meal_type or "dinner"
        diet_tags = sorted({*template.diet_tags})
        candidate_id = uuid5(
            NAMESPACE_URL,
            f"macrochef-library:{request.user_id}:{cuisine}:{title}:{index}",
        ).hex[:16]
        return RecipeCandidate(
            candidate_id=f"mock_{candidate_id}",
            title=title,
            cuisine=cuisine,
            meal_type=meal_type,
            description=template.description,
            ingredients=template.ingredients,
            instructions=template.instructions,
            cook_time_min=cook_time,
            difficulty=difficulty,
            servings=1,
            calories=template.calories,
            protein_g=template.protein_g,
            carbs_g=template.carbs_g,
            fat_g=template.fat_g,
            fiber_g=template.fiber_g,
            allergens=template.allergens,
            diet_tags=diet_tags,
            equipment=template.equipment,
            image_url=placeholder_image_url(title, cuisine, meal_type),
            source_type="mock",
            source_name="MacroChef mock library",
            home_cookable_score=0.94,
        )

    def _allowed(self, candidate: RecipeCandidate, request: RecipeDiscoveryRequest) -> bool:
        if request.allergies and self._has_conflict([*candidate.ingredients, *candidate.allergens], request.allergies):
            return False
        if request.excluded_ingredients and self._has_conflict(candidate.ingredients, request.excluded_ingredients):
            return False
        if request.diet_type:
            requested = request.diet_type.lower()
            tags = {tag.lower() for tag in candidate.diet_tags}
            if requested not in tags and requested in {"vegetarian", "vegan", "dairy-free", "gluten-free"}:
                return False
        return not bool(
            request.max_cook_time_min
            and candidate.cook_time_min
            and candidate.cook_time_min > request.max_cook_time_min
        )

    def _has_conflict(self, recipe_terms: list[str], blocked_terms: list[str]) -> bool:
        return any(ingredient_matches(blocked, term) for blocked in blocked_terms for term in recipe_terms)

    def _generic_templates(self, cuisine: str) -> list[MockRecipeTemplate]:
        return [
            MockRecipeTemplate(
                f"{cuisine.title()} Chicken Rice Bowl",
                ["150 g chicken breast", "140 g cooked rice", "100 g mixed vegetables", "8 g olive oil"],
                ["Cook rice.", "Sear chicken.", "Warm vegetables and assemble the bowl."],
                560,
                46,
                58,
                14,
                6,
                28,
                [],
                ["high-protein", "dairy-free", "gluten-free"],
                ["skillet"],
                f"A practical {cuisine.title()}-style chicken rice bowl.",
            ),
            MockRecipeTemplate(
                f"{cuisine.title()} Turkey Vegetable Skillet",
                ["160 g ground turkey", "120 g zucchini", "90 g tomato", "80 g spinach"],
                ["Brown turkey.", "Add vegetables.", "Simmer until tender."],
                500,
                42,
                28,
                20,
                7,
                24,
                [],
                ["high-protein", "dairy-free", "gluten-free"],
                ["skillet"],
                f"A simple {cuisine.title()}-style turkey skillet.",
            ),
            MockRecipeTemplate(
                f"{cuisine.title()} Lentil Vegetable Bowl",
                ["180 g lentils", "140 g cooked rice", "100 g carrot", "60 g spinach"],
                ["Simmer lentils.", "Cook rice.", "Serve with vegetables."],
                520,
                25,
                78,
                8,
                18,
                30,
                [],
                ["vegetarian", "vegan", "dairy-free", "gluten-free", "high-fiber"],
                ["pot"],
                f"A plant-forward {cuisine.title()}-style lentil bowl.",
            ),
            MockRecipeTemplate(
                f"{cuisine.title()} Salmon Rice Plate",
                ["140 g salmon", "150 g cooked rice", "90 g cucumber", "80 g broccoli"],
                ["Cook rice.", "Sear salmon.", "Serve with vegetables."],
                590,
                39,
                58,
                21,
                6,
                26,
                ["fish"],
                ["high-protein", "dairy-free", "gluten-free"],
                ["skillet"],
                f"A balanced {cuisine.title()}-style salmon plate.",
            ),
            MockRecipeTemplate(
                f"{cuisine.title()} Tofu Rice Skillet",
                ["170 g tofu", "140 g cooked rice", "100 g bell pepper", "60 g green onion"],
                ["Crisp tofu.", "Warm rice and vegetables.", "Combine in the skillet."],
                510,
                28,
                62,
                16,
                8,
                22,
                ["soy"],
                ["vegetarian", "dairy-free", "gluten-free"],
                ["skillet"],
                f"A home-cookable {cuisine.title()}-style tofu skillet.",
            ),
        ]
