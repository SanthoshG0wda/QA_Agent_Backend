from datetime import datetime
from bson import ObjectId

def create_setting_doc():
    return {
        "key_type": "api_keys",
        "groq_api_key": "",
        "nvidia_api_key": "",
        "deepgram_api_key": "",
        "jwt_secret": "",
        "updated_at": datetime.utcnow(),
        "updated_by": None,
    }

def setting_to_dict(doc):
    if not doc:
        return None
    return {
        "_id": str(doc.get("_id")),
        "key_type": doc.get("key_type"),
        "groq_api_key": doc.get("groq_api_key", ""),
        "nvidia_api_key": doc.get("nvidia_api_key", ""),
        "deepgram_api_key": doc.get("deepgram_api_key", ""),
        "jwt_secret": doc.get("jwt_secret", ""),
        "updated_at": doc.get("updated_at"),
        "updated_by": doc.get("updated_by"),
    }
