import asyncio
import functools
import logging
import time
from faster_whisper import WhisperModel

from .timing import record_timing

logger = logging.getLogger(__name__)

model = None


def get_model():
    global model
    if model is None:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute = "float16" if device == "cuda" else "int8"
        logger.info("Loading Whisper small model on %s with %s", device, compute)
        t0 = time.time()
        model = WhisperModel("small", device=device, compute_type=compute)
        logger.info("Whisper model loaded in %.2f s", time.time() - t0)
    return model


def load_model():
    get_model()


def _transcribe_sync(file_path: str) -> tuple[str, list[dict]]:
    model = get_model()
    segments, _ = model.transcribe(file_path, language="en", beam_size=1)
    texts = []
    segs = []
    for seg in segments:
        texts.append(seg.text)
        segs.append({
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": seg.text,
        })
    return " ".join(texts), segs


async def transcribe_audio(file_path: str) -> tuple[str, list[dict]]:
    t0 = time.time()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, functools.partial(_transcribe_sync, file_path))
    record_timing("transcription", time.time() - t0)
    return result
