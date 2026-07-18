from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.data.db import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    recipe_id: Mapped[str] = mapped_column(String(128), index=True)
    feedback_type: Mapped[str] = mapped_column(String(32), index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class SessionMemory(Base):
    __tablename__ = "session_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    summary: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class UserSavedRecipe(Base):
    __tablename__ = "user_saved_recipes"
    # recipe_id is unique per user, NOT globally unique -- a global unique
    # constraint here previously meant a second user saving a recipe_id
    # already claimed by another user silently reassigned (stole) that row
    # (see RecipeLibraryRepository.save_recipe). Two different users are now
    # free to each have their own row for the "same" recipe_id.
    __table_args__ = (
        UniqueConstraint("user_id", "recipe_id", name="uq_user_saved_recipes_user_recipe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    recipe_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    cuisine: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    meal_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    recipe_json: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
