import logging
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..auth.token_utils import get_current_user
from .upload import cancel_task_for_call

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _find_job_doc(db, job_id: str):
    query = {"$or": [{"job_id": job_id}]}
    try:
        query["$or"].append({"_id": ObjectId(job_id)})
    except (InvalidId, TypeError):
        pass
    return await db.calls.find_one(query)


@router.get("")
async def list_jobs(_=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    docs = await db.calls.find({"job_id": {"$exists": True}}, {
        "job_id": 1, "processing_status": 1, "progress": 1, "filename": 1, "created_at": 1,
        "agent_name": 1, "department_name": 1, "duration_seconds": 1, "evaluation_id": 1,
    }).sort("created_at", -1).to_list(100)
    now = datetime.now(timezone.utc)
    from .upload import _active_call_tasks
    results = []
    for d in docs:
        status = d.get("processing_status", "pending")
        if status in ["processing", "pending", "queued"]:
            created_at = d.get("created_at")
            if created_at:
                if getattr(created_at, "tzinfo", None) is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if (now - created_at).total_seconds() > 300 and str(d["_id"]) not in _active_call_tasks:
                    status = "failed"
                    await db.calls.update_one(
                        {"_id": d["_id"]},
                        {"$set": {"processing_status": "failed", "error": "Processing timed out or task interrupted", "progress": 0}},
                    )
        results.append({
            "job_id": d.get("job_id", ""),
            "call_id": str(d["_id"]),
            "evaluation_id": d.get("evaluation_id", ""),
            "status": status,
            "progress": d.get("progress", 0) if status != "failed" else 0,
            "filename": d.get("filename", ""),
            "agent_name": d.get("agent_name", ""),
            "department_name": d.get("department_name", ""),
            "duration_seconds": d.get("duration_seconds", 0),
            "created_at": d.get("created_at", "").isoformat() if d.get("created_at") else "",
        })
    return results


@router.get("/{job_id}")
async def get_job(job_id: str, _=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    doc = await _find_job_doc(db, job_id)
    if not doc:
        raise HTTPException(404, "Job not found")

    status = doc.get("processing_status", "pending")
    if status in ["processing", "pending", "queued"]:
        created_at = doc.get("created_at")
        if created_at:
            if getattr(created_at, "tzinfo", None) is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            from .upload import _active_call_tasks
            if (now - created_at).total_seconds() > 300 and str(doc["_id"]) not in _active_call_tasks:
                status = "failed"
                await db.calls.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"processing_status": "failed", "error": "Processing timed out or task interrupted", "progress": 0}},
                )

    return {
        "job_id": doc.get("job_id", ""),
        "call_id": str(doc["_id"]),
        "evaluation_id": doc.get("evaluation_id", ""),
        "status": status,
        "progress": doc.get("progress", 0) if status != "failed" else 0,
        "filename": doc.get("filename", ""),
        "agent_name": doc.get("agent_name", ""),
        "department_name": doc.get("department_name", ""),
        "duration_seconds": doc.get("duration_seconds", 0),
        "created_at": doc.get("created_at", "").isoformat() if doc.get("created_at") else "",
    }


@router.post("/{job_id}/end")
@router.post("/{job_id}/cancel")
async def end_job(job_id: str, _=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    doc = await _find_job_doc(db, job_id)
    if not doc:
        raise HTTPException(404, "Job not found")

    call_id = str(doc["_id"])
    curr_status = doc.get("processing_status", "pending")
    if curr_status in ["completed", "failed", "cancelled"]:
        return {
            "ok": True,
            "message": f"Job is already {curr_status}",
            "job_id": doc.get("job_id", job_id),
            "call_id": call_id,
            "status": curr_status,
        }

    # Cancel active task if running in background
    cancel_task_for_call(call_id)

    # Update database status to cancelled
    await db.calls.update_one(
        {"_id": doc["_id"]},
        {"$set": {
            "processing_status": "cancelled",
            "error": "Job ended by user",
            "progress": 0,
            "updated_at": datetime.now(timezone.utc),
        }}
    )

    return {
        "ok": True,
        "message": "Job ended successfully",
        "job_id": doc.get("job_id", job_id),
        "call_id": call_id,
        "status": "cancelled",
    }


@router.delete("/{job_id}")
async def delete_job(job_id: str, _=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    doc = await _find_job_doc(db, job_id)
    if not doc:
        raise HTTPException(404, "Job not found")

    call_id = str(doc["_id"])

    # Cancel task if running
    cancel_task_for_call(call_id)

    # Delete call record
    await db.calls.delete_one({"_id": doc["_id"]})

    # Delete associated evaluations and notifications
    await db.evaluations.delete_many({"call_id": call_id})
    await db.notifications.delete_many({"call_id": call_id})

    return {
        "ok": True,
        "message": "Job deleted successfully",
        "job_id": doc.get("job_id", job_id),
        "call_id": call_id,
    }
