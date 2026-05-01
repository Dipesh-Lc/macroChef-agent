import re
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile

from app.schemas.inventory import InventoryObservation
from app.services.text_inventory_parser import merge_inventory_observations, parse_typed_inventory
from app.services.vision_service import extract_inventory_from_image

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.post("/extract", response_model=list[InventoryObservation])
async def extract_inventory(
    typed_ingredients: Annotated[str | None, Form()] = None,
    image: Annotated[UploadFile | None, File()] = None,
) -> list[InventoryObservation]:
    text_observations = parse_typed_inventory(typed_ingredients)
    if image is not None:
        upload_dir = Path("data/raw/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        original_name = Path(image.filename or "image.jpg")
        suffix = original_name.suffix or ".jpg"
        safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", original_name.stem).strip("_")
        image_path = upload_dir / f"{uuid4().hex}_{safe_stem or 'upload'}{suffix}"
        image_path.write_bytes(await image.read())
        vision_observations = extract_inventory_from_image(image_path)
        return merge_inventory_observations(text_observations, vision_observations)
    return text_observations
