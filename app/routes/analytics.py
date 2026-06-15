from fastapi import APIRouter, Depends
from ..database import get_db
from ..auth.token_utils import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
async def get_summary(_=Depends(get_current_user)):
    db = get_db()
    if db is None:
        return {}
    total_calls = await db.calls.count_documents({})
    total_agents = await db.agents.count_documents({})
    evals = await db.evaluations.find().to_list(1000)
    total_score = sum(e.get("overall_score", 0) for e in evals)
    avg_score = round(total_score / len(evals), 1) if evals else 0
    critical_count = sum(1 for e in evals if e.get("critical_error"))
    week_ago = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    from datetime import timedelta
    week_ago = week_ago - timedelta(days=7)
    calls_week = await db.calls.count_documents({"created_at": {"$gte": week_ago}})
    return {
        "total_calls": total_calls,
        "total_agents": total_agents,
        "avg_score": avg_score,
        "critical_errors": critical_count,
        "calls_this_week": calls_week,
    }


@router.get("/trends")
async def get_trends(_=Depends(get_current_user)):
    db = get_db()
    if db is None:
        return []
    evals = await db.evaluations.find().sort("created_at", 1).to_list(500)
    from collections import Counter
    by_month = Counter()
    for e in evals:
        d = e.get("created_at")
        if d:
            key = f"{d.year}-{d.month:02d}"
            by_month[key] += e.get("overall_score", 0)
    return [{"month": m, "avg": round(s / max(1, (by_month[m] or 1)), 1)}
            for m, s in sorted(by_month.items())]


@router.get("/categories")
async def get_category_stats(_=Depends(get_current_user)):
    db = get_db()
    if db is None:
        return {}
    evals = await db.evaluations.find().to_list(500)
    if not evals:
        return {}
    keys = ["opening_score", "communication_score", "listening_score", "knowledge_score",
            "discovery_score", "call_control_score", "professionalism_score",
            "compliance_score", "closing_score"]
    maxes = {"opening_score": 10, "communication_score": 15, "listening_score": 15,
             "knowledge_score": 15, "discovery_score": 10, "call_control_score": 10,
             "professionalism_score": 10, "compliance_score": 5, "closing_score": 5}
    result = {}
    for k in keys:
        vals = [e.get(k, 0) for e in evals]
        avg = sum(vals) / len(vals) if vals else 0
        result[k.replace("_score", "")] = round(avg / maxes[k] * 100, 1)
    return result
