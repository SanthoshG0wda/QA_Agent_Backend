import logging
import time
from ..config import HF_TOKEN
from .timing import record_timing

logger = logging.getLogger(__name__)

_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        from pyannote.audio import Pipeline
        t0 = time.time()
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=HF_TOKEN,
        )
        logger.info("Diarization pipeline loaded in %.2f s", time.time() - t0)
    return _pipeline


def _diarize_sync(audio_path: str) -> list[dict]:
    from pyannote.core import Annotation
    pipeline = get_pipeline()
    result = pipeline(audio_path)
    annotation = None
    if isinstance(result, Annotation):
        annotation = result
    else:
        for attr in ("speaker_diarization", "exclusive_speaker_diarization"):
            candidate = getattr(result, attr, None)
            if isinstance(candidate, Annotation):
                annotation = candidate
                break
    if annotation is None:
        return []
    segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        segments.append({
            "speaker": speaker,
            "start": round(turn.start, 2),
            "end": round(turn.end, 2),
        })
    return segments


def merge_with_transcript(whisper_segments: list[dict], diarization_segments: list[dict]) -> str:
    if not diarization_segments:
        return None
    merged = []
    for wseg in whisper_segments:
        ws, we = wseg["start"], wseg["end"]
        wc = (ws + we) / 2
        speaker = None
        for dseg in diarization_segments:
            if dseg["start"] <= wc <= dseg["end"]:
                speaker = dseg["speaker"]
                break
        label = speaker or "UNKNOWN"
        merged.append(f"[{label}]\n{wseg['text']}")
    return "\n\n".join(merged)


async def diarize_audio(audio_path: str) -> list[dict] | None:
    if not HF_TOKEN:
        logger.warning("HF_TOKEN not set, skipping diarization")
        return None
    try:
        import asyncio
        import functools
        t0 = time.time()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, functools.partial(_diarize_sync, audio_path))
        record_timing("diarization", time.time() - t0)
        return result
    except Exception as e:
        logger.warning("Diarization failed: %s", e, exc_info=True)
        return None
