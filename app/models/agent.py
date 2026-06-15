from datetime import datetime, timezone


def create_agent_doc(name: str, email: str, department_id: str = "", department_name: str = "") -> dict:
    return {
        "name": name,
        "email": email.lower(),
        "department_id": department_id,
        "department_name": department_name,
        "created_at": datetime.now(timezone.utc),
    }


def agent_to_dict(doc) -> dict:
    return {
        "id": str(doc.get("_id", "")),
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
        "department_id": doc.get("department_id", ""),
        "department_name": doc.get("department_name", ""),
        "total_calls": doc.get("total_calls", 0),
        "average_score": doc.get("average_score", 0),
        "created_at": doc.get("created_at", datetime.now(timezone.utc)).isoformat(),
    }
