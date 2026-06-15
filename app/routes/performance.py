from fastapi import APIRouter, Depends
from ..services.timing import get_average_timings, clear_timings
from ..auth.token_utils import get_current_user

router = APIRouter()


@router.get("/performance")
async def get_performance(_=Depends(get_current_user)):
    return get_average_timings()


@router.delete("/performance")
async def reset_performance(_=Depends(get_current_user)):
    clear_timings()
    return {"ok": True}
