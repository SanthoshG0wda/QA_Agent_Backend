import logging
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..models.notification import create_notification_doc, notification_to_dict
from ..auth.token_utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


def _validate_id(id_str: str, name: str = "id") -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise HTTPException(400, f"Invalid {name}: '{id_str}' is not a valid ID")


@router.get("")
async def list_notifications(payload: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    user_id = payload.get("sub", "")
    docs = await db.notifications.find({"user_id": user_id}).sort("created_at", -1).limit(50).to_list(50)
    return [notification_to_dict(d) for d in docs]


@router.get("/unread-count")
async def unread_count(payload: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    user_id = payload.get("sub", "")
    count = await db.notifications.count_documents({"user_id": user_id, "read": False})
    return {"count": count}


@router.put("/{notification_id}/read")
async def mark_read(notification_id: str, _=Depends(get_current_user)):
    obj_id = _validate_id(notification_id, "notification_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    await db.notifications.update_one({"_id": obj_id}, {"$set": {"read": True}})
    return {"ok": True}


@router.put("/read-all")
async def mark_all_read(payload: dict = Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    user_id = payload.get("sub", "")
    await db.notifications.update_many({"user_id": user_id, "read": False}, {"$set": {"read": True}})
    return {"ok": True}
