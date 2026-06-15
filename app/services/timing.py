import time
import logging

logger = logging.getLogger(__name__)

_timing_data: dict[str, list[float]] = {}


def record_timing(stage: str, duration: float):
    if stage not in _timing_data:
        _timing_data[stage] = []
    _timing_data[stage].append(duration)
    logger.info("TIMING [%s]: %.3f s", stage, duration)


def get_average_timings() -> dict:
    return {
        stage: {
            "avg_s": round(sum(durations) / len(durations), 3),
            "count": len(durations),
            "total_s": round(sum(durations), 3),
        }
        for stage, durations in _timing_data.items()
    }


def clear_timings():
    _timing_data.clear()
