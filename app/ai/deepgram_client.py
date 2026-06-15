import httpx
import logging
import time
import mimetypes
from ..config import DEEPGRAM_API_KEY
from ..services.timing import record_timing

logger = logging.getLogger(__name__)

DEEPGRAM_BASE = "https://api.deepgram.com/v1/listen"

DEFAULT_OPTIONS = {
    "model": "nova-3",
    "language": "en",
    "smart_format": "true",
    "punctuate": "true",
    "paragraphs": "true",
    "utterances": "true",
    "diarize": "true",
}


async def transcribe_audio(file_path: str) -> dict:
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY is not set")

    t0 = time.time()
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "audio/wav"

    t_read = time.time()
    with open(file_path, "rb") as f:
        audio_data = f.read()
    file_read_time = time.time() - t_read
    logger.info("TIMING [file_read]: %.3f s (%d bytes)", file_read_time, len(audio_data))

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            DEEPGRAM_BASE,
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": mime_type,
            },
            params=DEFAULT_OPTIONS,
            content=audio_data,
        )
        resp.raise_for_status()
        result = resp.json()

    api_time = time.time() - t0
    elapsed = time.time() - t0
    record_timing("deepgram", elapsed)
    logger.info("TIMING [deepgram_api]: %.3f s (file_read=%.3f s)", api_time, file_read_time)

    transcript = _extract_transcript(result)
    utterances = _extract_utterances(result)
    speaker_count = _count_speakers(utterances)

    logger.info(
        "Deepgram transcribed %.2fs audio in %.2fs (speakers=%d, utterances=%d)",
        result.get("metadata", {}).get("duration", 0),
        elapsed,
        speaker_count,
        len(utterances),
    )

    return {
        "transcript": transcript,
        "utterances": utterances,
        "speaker_count": speaker_count,
        "duration": result.get("metadata", {}).get("duration", 0),
        "deepgram_raw": result,
    }


def _extract_transcript(result: dict) -> str:
    try:
        return result["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError):
        logger.warning("Could not extract transcript from Deepgram response")
        return ""


def _extract_utterances(result: dict) -> list[dict]:
    utterances = []
    try:
        raw = result["results"]["channels"][0]["alternatives"][0]["paragraphs"]["paragraphs"]
        for para in raw:
            sentences = para.get("sentences", [])
            for sent in sentences:
                utterances.append({
                    "speaker": f"Speaker_{sent.get('speaker', 0)}",
                    "start": round(sent.get("start", 0), 2),
                    "end": round(sent.get("end", 0), 2),
                    "text": sent.get("text", "").strip(),
                })
    except (KeyError, IndexError):
        try:
            raw_utterances = result["results"]["utterances"]
            for utt in raw_utterances:
                utterances.append({
                    "speaker": f"Speaker_{utt.get('speaker', 0)}",
                    "start": round(utt.get("start", 0), 2),
                    "end": round(utt.get("end", 0), 2),
                    "text": utt.get("transcript", "").strip(),
                })
        except (KeyError, IndexError):
            logger.warning("Could not extract utterances from Deepgram response")

    return utterances


def _count_speakers(utterances: list[dict]) -> int:
    return len({u["speaker"] for u in utterances})
