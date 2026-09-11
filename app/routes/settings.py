from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
from ..database import get_db
from ..auth.token_utils import get_current_user, require_exact_role
from ..models.setting import create_setting_doc, setting_to_dict
from ..services.settings_service import invalidate_cache
from bson import ObjectId

router = APIRouter()

class ApiKeysUpdate(BaseModel):
    groq_api_key: str | None = None
    nvidia_api_key: str | None = None
    deepgram_api_key: str | None = None
    jwt_secret: str | None = None

@router.get("/settings/api-keys")
async def get_api_keys(current_user = Depends(require_exact_role("service"))):
    db = get_db()
    doc = await db.settings.find_one({"key_type": "api_keys"})
    if not doc:
        doc = create_setting_doc()
        await db.settings.insert_one(doc)
        doc = await db.settings.find_one({"key_type": "api_keys"})
    return setting_to_dict(doc)

@router.put("/settings/api-keys")
async def update_api_keys(payload: ApiKeysUpdate, current_user = Depends(require_exact_role("service"))):
    db = get_db()
    update = {}
    if payload.groq_api_key is not None:
        update["groq_api_key"] = payload.groq_api_key
    if payload.nvidia_api_key is not None:
        update["nvidia_api_key"] = payload.nvidia_api_key
    if payload.deepgram_api_key is not None:
        update["deepgram_api_key"] = payload.deepgram_api_key
    if payload.jwt_secret is not None:
        update["jwt_secret"] = payload.jwt_secret

    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    update["updated_at"] = datetime.utcnow()
    update["updated_by"] = str(current_user.get("_id"))

    doc = await db.settings.find_one_and_update(
        {"key_type": "api_keys"},
        {"$set": update},
        upsert=True,
        return_document=True
    )
    invalidate_cache()
    return setting_to_dict(doc)
