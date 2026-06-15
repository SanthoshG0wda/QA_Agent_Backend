import logging

from ..ai.deepgram_client import transcribe_audio as deepgram_transcribe
from .conversation_reconstruction import reconstruct_from_utterances

logger = logging.getLogger(__name__)


async def transcribe_audio(file_path: str) -> tuple[str, list[dict]]:
    """Transcribe audio using Deepgram.

    Returns (full_transcript, utterance_segments).
    utterance_segments is a list of {speaker, start, end, text} dicts.
    """
    result = await deepgram_transcribe(file_path)
    transcript = result["transcript"]
    utterances = result["utterances"]
    return transcript, utterances
