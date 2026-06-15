import re
import logging

logger = logging.getLogger(__name__)


def parse_diarized_text(text: str) -> list[dict]:
    """Parse '[SPEAKER_00]\\ntext' format into structured segment list."""
    if not text:
        return []

    segments = []
    blocks = text.split("\n\n")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        speaker_line = lines[0].strip()
        speaker = speaker_line.strip("[]") if speaker_line.startswith("[") else None
        content = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        if speaker:
            segments.append({"speaker": speaker, "text": content})
        else:
            segments.append({"speaker": "UNKNOWN", "text": block})
    return segments


def clean_segments(segments: list[dict]) -> list[dict]:
    """Remove empty, null, whitespace-only, and speaker-only segments."""
    cleaned = []
    removed_count = 0
    for seg in segments:
        text = seg.get("text", "")
        if text is None:
            removed_count += 1
            continue
        text = text.strip()
        if not text:
            removed_count += 1
            continue
        speaker = seg.get("speaker", "")
        if text == f"[{speaker}]" or text == speaker:
            removed_count += 1
            continue
        cleaned.append({"speaker": speaker, "text": text})
    if removed_count:
        logger.info("Cleaned %d empty/null/placeholder segments", removed_count)
    return cleaned


def merge_consecutive_segments(segments: list[dict]) -> list[dict]:
    """Merge consecutive messages from the same speaker."""
    if not segments:
        return []

    merged = [dict(segments[0])]
    merge_count = 0
    for seg in segments[1:]:
        if seg["speaker"] == merged[-1]["speaker"]:
            merged[-1]["text"] += " " + seg["text"]
            merge_count += 1
        else:
            merged.append(dict(seg))
    if merge_count:
        logger.info("Merged %d consecutive same-speaker segments", merge_count)
    return merged


def segments_to_text(segments: list[dict]) -> str:
    """Convert segment list back to diarized text format."""
    return "\n\n".join(
        f"[{seg['speaker']}]\n{seg['text']}" for seg in segments
    )


def clean_and_merge_pipeline(diarized_text: str) -> tuple[list[dict], str]:
    """Run parse → clean → merge → text.
    Returns (segments, cleaned_text)."""
    segments = parse_diarized_text(diarized_text)
    segments = clean_segments(segments)
    segments = merge_consecutive_segments(segments)
    cleaned_text = segments_to_text(segments)
    return segments, cleaned_text
