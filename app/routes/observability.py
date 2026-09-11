from fastapi import APIRouter, Depends
from ..database import get_db
from ..auth.token_utils import require_role

router = APIRouter()

@router.get("/observability/summary")
async def observability_summary(current_user = Depends(require_role("service"))):
    db = get_db()
    # Calls overview
    total_calls = await db.calls.count_documents({})
    pending_calls = await db.calls.count_documents({"processing_status": {"$in": ["pending", "queued", "processing"]}})
    failed_calls = await db.calls.count_documents({"processing_status": "failed"})
    
    # Evaluations overview
    total_evals = await db.evaluations.count_documents({})
    critical_evals = await db.evaluations.count_documents({"critical_error": True})
    failed_evals = await db.evaluations.count_documents({"status": "failed"})
    
    # Recent errors
    recent_errors = []
    cursor = db.evaluations.find({"$or": [{"status": "failed"}, {"critical_error": True}]}).sort("created_at", -1).limit(20)
    async for doc in cursor:
        recent_errors.append({
            "id": str(doc.get("_id")),
            "call_id": str(doc.get("call_id")),
            "status": doc.get("status"),
            "critical_error": doc.get("critical_error"),
            "errors": doc.get("critical_errors", [])[:3],
            "created_at": doc.get("created_at"),
            "warnings": doc.get("warnings", [])
        })
    
    # Performance timings
    perf = await db.performance.find_one({}) if hasattr(db, 'performance') else None
    # Jobs
    jobs_count = await db.jobs.count_documents({}) if hasattr(db, 'jobs') else 0
    active_jobs = await db.jobs.count_documents({"status": {"$in": ["running", "queued"]}}) if hasattr(db, 'jobs') else 0
    
    return {
        "calls": {
            "total": total_calls,
            "pending": pending_calls,
            "failed": failed_calls
        },
        "evaluations": {
            "total": total_evals,
            "critical": critical_evals,
            "failed": failed_evals
        },
        "recent_errors": recent_errors,
        "jobs": {
            "total": jobs_count,
            "active": active_jobs
        },
        "performance": perf
    }
