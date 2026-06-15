import logging
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from ..database import get_db
from ..models.department import create_department_doc, department_to_dict
from ..auth.token_utils import get_current_user, require_role

import datetime
from datetime import timedelta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/departments", tags=["departments"])

class DepartmentBody(BaseModel):
    name: str


def _validate_id(id_str: str, name: str = "id") -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise HTTPException(400, f"Invalid {name}: '{id_str}' is not a valid ID")


@router.post("")
async def create_department(body: DepartmentBody, _=Depends(require_role("admin"))):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    existing = await db.departments.find_one({"name": body.name})
    if existing:
        raise HTTPException(400, "Department already exists")
    doc = create_department_doc(body.name)
    result = await db.departments.insert_one(doc)
    return department_to_dict({**doc, "_id": result.inserted_id})


@router.get("")
async def list_departments(_=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    docs = await db.departments.find().sort("name", 1).to_list(100)
    return [department_to_dict(d) for d in docs]


@router.get("/{department_id}")
async def get_department(department_id: str, _=Depends(get_current_user)):
    obj_id = _validate_id(department_id, "department_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    doc = await db.departments.find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(404, "Department not found")
    return department_to_dict(doc)


@router.get("/{department_id}/stats")
async def department_stats(department_id: str, _=Depends(get_current_user)):
    obj_id = _validate_id(department_id, "department_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    dept = await db.departments.find_one({"_id": obj_id})
    if not dept:
        raise HTTPException(404, "Department not found")
    dept_name = dept.get("name", "")

    calls = await db.calls.find({"department_id": department_id}).sort("created_at", -1).to_list(200)
    evaluations = await db.evaluations.find({"department_id": department_id}).sort("created_at", -1).to_list(200)
    agents = await db.agents.find({"department_id": department_id}).sort("name", 1).to_list(100)

    total_calls = len(calls)
    completed_calls = sum(1 for c in calls if c.get("processing_status") == "completed")
    total_evals = len(evaluations)
    scores = [e.get("overall_score", 0) for e in evaluations if e.get("overall_score")]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    agent_scores = {}
    for e in evaluations:
        aid = e.get("agent_id", "")
        if aid:
            if aid not in agent_scores:
                agent_scores[aid] = []
            agent_scores[aid].append(e.get("overall_score", 0))

    agent_stats = []
    for a in agents:
        aid = str(a["_id"])
        a_scores = agent_scores.get(aid, [])
        agent_calls = sum(1 for c in calls if c.get("agent_id") == aid)
        agent_stats.append({
            "id": aid,
            "name": a.get("name", ""),
            "email": a.get("email", ""),
            "total_calls": agent_calls,
            "evaluations": len(a_scores),
            "avg_score": round(sum(a_scores) / len(a_scores), 1) if a_scores else 0,
        })
    agent_stats.sort(key=lambda x: x["avg_score"], reverse=True)

    recent_evals = []
    for e in evaluations[:10]:
        recent_evals.append({
            "id": str(e["_id"]),
            "agent_name": e.get("agent_name", ""),
            "overall_score": e.get("overall_score", 0),
            "critical_error": e.get("critical_error", False),
            "created_at": e.get("created_at").isoformat() if e.get("created_at") else "",
        })

    week_ago = datetime.datetime.now(datetime.timezone.utc) - timedelta(days=7)
    calls_this_week = sum(1 for c in calls if c.get("created_at") and c["created_at"] >= week_ago)

    return {
        "id": department_id,
        "name": dept_name,
        "total_calls": total_calls,
        "completed_calls": completed_calls,
        "total_evaluations": total_evals,
        "avg_score": avg_score,
        "calls_this_week": calls_this_week,
        "total_agents": len(agents),
        "top_agents": agent_stats[:5],
        "agents": agent_stats,
        "recent_evaluations": recent_evals,
    }


@router.delete("/{department_id}")
async def delete_department(department_id: str, _=Depends(require_role("admin"))):
    obj_id = _validate_id(department_id, "department_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    result = await db.departments.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Department not found")
    return {"ok": True}
