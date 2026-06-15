from datetime import datetime, timezone


def create_notification_doc(user_id: str, evaluation_id: str, title: str, message: str) -> dict:
    return {
        "user_id": user_id,
        "evaluation_id": evaluation_id,
        "title": title,
        "message": message,
        "read": False,
        "created_at": datetime.now(timezone.utc),
    }


def notification_to_dict(doc) -> dict:
    return {
        "id": str(doc.get("_id", "")),
        "user_id": doc.get("user_id", ""),
        "evaluation_id": doc.get("evaluation_id", ""),
        "title": doc.get("title", ""),
        "message": doc.get("message", ""),
        "read": doc.get("read", False),
        "created_at": doc.get("created_at", "").isoformat() if doc.get("created_at") else "",
    }
