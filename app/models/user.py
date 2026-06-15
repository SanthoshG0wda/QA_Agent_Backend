from datetime import datetime, timezone


def create_user_doc(name: str, email: str, password_hash: str, role: str = "agent") -> dict:
    return {
        "name": name,
        "email": email.lower(),
        "password_hash": password_hash,
        "role": role,
        "created_at": datetime.now(timezone.utc),
    }


def user_to_dict(doc) -> dict:
    return {
        "id": str(doc.get("_id", "")),
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
        "role": doc.get("role", "agent"),
        "created_at": doc.get("created_at", datetime.now(timezone.utc)).isoformat(),
    }
