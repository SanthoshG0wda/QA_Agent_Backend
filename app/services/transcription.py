import logging

from ..ai.deepgram_client import transcribe_audio as deepgram_transcribe
from .conversation_reconstruction import reconstruct_from_utterances

logger = logging.getLogger(__name__)


async def transcribe_audio(audio_bytes: bytes, content_type: str = "audio/wav") -> tuple[str, list[dict]]:
    result = await deepgram_transcribe(audio_bytes, content_type)
    transcript = result["transcript"]
    utterances = result["utterances"]
    return transcript, utterances
