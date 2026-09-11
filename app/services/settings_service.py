import os
from ..database import get_db

_cache = None

async def _load_settings():
    global _cache
    if _cache is not None:
        return _cache
    db = get_db()
    if db is None:
        _cache = {}
        return _cache
    doc = await db.settings.find_one({"key_type": "api_keys"})
    _cache = doc or {}
    return _cache

async def get_api_key(key_name: str, env_name: str) -> str:
    settings = await _load_settings()
    val = settings.get(key_name)
    if val:
        return val
    return os.getenv(env_name, "")

async def get_groq_api_key():
    return await get_api_key("groq_api_key", "GROQ_API_KEY")

async def get_nvidia_api_key():
    return await get_api_key("nvidia_api_key", "NVIDIA_API_KEY")

async def get_deepgram_api_key():
    return await get_api_key("deepgram_api_key", "DEEPGRAM_API_KEY")

async def get_jwt_secret():
    settings = await _load_settings()
    val = settings.get("jwt_secret")
    if val:
        return val
    return os.getenv("JWT_SECRET", "call-qa-secret-key-change-in-production")

def invalidate_cache():
    global _cache
    _cache = None
