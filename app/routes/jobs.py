import logging
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth.token_utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(_=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    docs = await db.calls.find({"job_id": {"$exists": True}}, {
        "job_id": 1, "processing_status": 1, "progress": 1, "filename": 1, "created_at": 1,
        "agent_name": 1, "department_name": 1,
    }).sort("created_at", -1).to_list(100)
    return [
        {
            "job_id": d.get("job_id", ""),
            "call_id": str(d["_id"]),
            "status": d.get("processing_status", "pending"),
            "progress": d.get("progress", 0),
            "filename": d.get("filename", ""),
            "agent_name": d.get("agent_name", ""),
            "department_name": d.get("department_name", ""),
            "duration_seconds": d.get("duration_seconds", 0),
            "created_at": d.get("created_at", "").isoformat() if d.get("created_at") else "",
        }
        for d in docs
    ]


@router.get("/{job_id}")
async def get_job(job_id: str, _=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    doc = await db.calls.find_one({"job_id": job_id})
    if not doc:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": doc.get("job_id", ""),
        "call_id": str(doc["_id"]),
        "status": doc.get("processing_status", "pending"),
        "progress": doc.get("progress", 0),
        "filename": doc.get("filename", ""),
        "agent_name": doc.get("agent_name", ""),
        "department_name": doc.get("department_name", ""),
        "duration_seconds": doc.get("duration_seconds", 0),
        "created_at": doc.get("created_at", "").isoformat() if doc.get("created_at") else "",
    }
