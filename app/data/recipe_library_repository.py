import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.db import SessionLocal, init_db
from app.data.models import UserSavedRecipe
from app.schemas.recipe import Recipe


class RecipeLibraryRepository:
    def __init__(self, db: Session | None = None):
        init_db()
        self._external_db = db

    def _session(self) -> Session:
        return self._external_db or SessionLocal()

    def save_recipe(self, user_id: str, recipe: Recipe) -> str:
        db = self._session()
        close = self._external_db is None
        try:
            recipe = recipe.model_copy(
                update={"owner_user_id": user_id, "is_user_saved": True, "is_active": True}
            )
            payload = recipe.model_dump_json()
            existing = db.scalar(
                select(UserSavedRecipe).where(UserSavedRecipe.recipe_id == recipe.recipe_id)
            )
            if existing:
                existing.user_id = user_id
                existing.title = recipe.title
                existing.cuisine = recipe.cuisine
                existing.meal_type = recipe.meal_type
                existing.recipe_json = payload
                existing.source_type = recipe.source_type
                existing.image_url = recipe.image_url
                existing.image_path = recipe.image_path
                existing.is_active = True
            else:
                db.add(
                    UserSavedRecipe(
                        recipe_id=recipe.recipe_id,
                        user_id=user_id,
                        title=recipe.title,
                        cuisine=recipe.cuisine,
                        meal_type=recipe.meal_type,
                        recipe_json=payload,
                        source_type=recipe.source_type,
                        image_url=recipe.image_url,
                        image_path=recipe.image_path,
                        is_active=True,
                    )
                )
            db.commit()
            return recipe.recipe_id
        finally:
            if close:
                db.close()

    def list_user_recipes(self, user_id: str) -> list[Recipe]:
        db = self._session()
        close = self._external_db is None
        try:
            rows = db.scalars(
                select(UserSavedRecipe).where(
                    UserSavedRecipe.user_id == user_id,
                    UserSavedRecipe.is_active.is_(True),
                )
            ).all()
            return [self._row_to_recipe(row) for row in rows]
        finally:
            if close:
                db.close()

    def get_recipe(self, user_id: str, recipe_id: str) -> Recipe | None:
        db = self._session()
        close = self._external_db is None
        try:
            row = db.scalar(
                select(UserSavedRecipe).where(
                    UserSavedRecipe.user_id == user_id,
                    UserSavedRecipe.recipe_id == recipe_id,
                    UserSavedRecipe.is_active.is_(True),
                )
            )
            return self._row_to_recipe(row) if row else None
        finally:
            if close:
                db.close()

    def deactivate_recipe(self, user_id: str, recipe_id: str) -> bool:
        db = self._session()
        close = self._external_db is None
        try:
            row = db.scalar(
                select(UserSavedRecipe).where(
                    UserSavedRecipe.user_id == user_id,
                    UserSavedRecipe.recipe_id == recipe_id,
                    UserSavedRecipe.is_active.is_(True),
                )
            )
            if not row:
                return False
            row.is_active = False
            db.commit()
            return True
        finally:
            if close:
                db.close()

    def list_all_active_user_recipes(self) -> list[Recipe]:
        db = self._session()
        close = self._external_db is None
        try:
            rows = db.scalars(
                select(UserSavedRecipe).where(UserSavedRecipe.is_active.is_(True))
            ).all()
            return [self._row_to_recipe(row) for row in rows]
        finally:
            if close:
                db.close()

    def _row_to_recipe(self, row: UserSavedRecipe) -> Recipe:
        data = json.loads(row.recipe_json)
        recipe = Recipe.model_validate(data)
        return recipe.model_copy(
            update={
                "owner_user_id": row.user_id,
                "is_user_saved": True,
                "is_active": row.is_active,
            }
        )
