from fastapi import APIRouter, Depends
from ..services.timing import get_average_timings, clear_timings
from ..auth.token_utils import get_current_user
from ..routes.upload import _queued_count, _running_count
from ..config import MAX_CONCURRENT_JOBS

router = APIRouter()


@router.get("/performance")
async def get_performance(_=Depends(get_current_user)):
    timings = get_average_timings()
    timings["queue"] = {
        "queued_jobs": _queued_count,
        "running_jobs": _running_count,
        "max_concurrent": MAX_CONCURRENT_JOBS,
    }
    return timings


@router.delete("/performance")
async def reset_performance(_=Depends(get_current_user)):
    clear_timings()
    return {"ok": True}
