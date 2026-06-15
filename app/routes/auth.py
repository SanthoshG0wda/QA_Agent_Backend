from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from ..database import get_db
from ..models.user import create_user_doc, user_to_dict
from ..auth.hashing import hash_password, verify_password
from ..auth.token_utils import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthBody(BaseModel):
    name: str = ""
    email: str
    password: str
    role: str = "agent"


@router.post("/register")
async def register(body: AuthBody):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(400, "Email already registered")
    doc = create_user_doc(body.name, body.email, hash_password(body.password), body.role)
    result = await db.users.insert_one(doc)
    token = create_access_token(str(result.inserted_id), body.role)
    user = user_to_dict({**doc, "_id": result.inserted_id})
    return {"token": token, "user": user}


@router.post("/login")
async def login(body: AuthBody):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token(str(user["_id"]), user["role"])
    return {"token": token, "user": user_to_dict(user)}


@router.get("/me")
async def get_me(payload: dict = Depends(get_current_user)):
    from bson import ObjectId
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(404, "User not found")
    return user_to_dict(user)
