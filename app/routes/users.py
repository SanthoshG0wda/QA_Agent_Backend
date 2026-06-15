from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from ..database import get_db
from ..models.user import create_user_doc, user_to_dict
from ..auth.hashing import hash_password
from ..auth.token_utils import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


class UserBody(BaseModel):
    name: str = ""
    email: str
    password: str
    role: str = "agent"


async def require_admin(payload: dict = Depends(get_current_user)):
    if payload.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return payload


@router.get("/")
async def list_users(_=Depends(require_admin)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    docs = await db.users.find().sort("created_at", -1).to_list(100)
    return [user_to_dict(d) for d in docs]


@router.post("/")
async def create_user(body: UserBody, _=Depends(require_admin)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(400, "Email already exists")
    doc = create_user_doc(body.name, body.email, hash_password(body.password), body.role)
    result = await db.users.insert_one(doc)
    return user_to_dict({**doc, "_id": result.inserted_id})


@router.delete("/{user_id}")
async def delete_user(user_id: str, _=Depends(require_admin)):
    from bson import ObjectId
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    result = await db.users.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(404, "User not found")
    return {"ok": True}
