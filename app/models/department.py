from datetime import datetime, timezone


def create_department_doc(name: str) -> dict:
    return {
        "name": name,
        "created_at": datetime.now(timezone.utc),
    }


def department_to_dict(doc) -> dict:
    return {
        "id": str(doc.get("_id", "")),
        "name": doc.get("name", ""),
        "created_at": doc.get("created_at", "").isoformat() if doc.get("created_at") else "",
    }
