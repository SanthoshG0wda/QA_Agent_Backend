import logging

logger = logging.getLogger(__name__)


def reconstruct_from_utterances(utterances: list[dict]) -> tuple[list[dict], str]:
    """Convert Deepgram utterances into cleaned, merged segment list and text.

    Steps:
    1. Remove empty/filler utterances
    2. Merge consecutive same-speaker utterances
    3. Build [SPEAKER_0X] labeled text for AI evaluation

    Returns (segments, labeled_text).
    """
    if not utterances:
        return [], ""

    cleaned = _remove_empty(utterances)
    merged = _merge_consecutive(cleaned)
    labeled_text = _to_labeled_text(merged)
    logger.info(
        "Reconstructed %d utterances into %d segments",
        len(utterances), len(merged),
    )
    return merged, labeled_text


def _remove_empty(utterances: list[dict]) -> list[dict]:
    result = []
    removed = 0
    for utt in utterances:
        text = utt.get("text", "").strip()
        if not text:
            removed += 1
            continue
        result.append({
            "speaker": utt["speaker"],
            "start": utt.get("start", 0),
            "end": utt.get("end", 0),
            "text": text,
        })
    if removed:
        logger.info("Removed %d empty utterances", removed)
    return result


def _merge_consecutive(utterances: list[dict]) -> list[dict]:
    if not utterances:
        return []

    merged = [dict(utterances[0])]
    merge_count = 0
    for utt in utterances[1:]:
        if utt["speaker"] == merged[-1]["speaker"]:
            merged[-1]["text"] += " " + utt["text"]
            merged[-1]["end"] = utt["end"]
            merge_count += 1
        else:
            merged.append(dict(utt))

    if merge_count:
        logger.info("Merged %d consecutive same-speaker utterances", merge_count)
    return merged


def _to_labeled_text(segments: list[dict]) -> str:
    return "\n\n".join(
        f"[{seg['speaker']}]\n{seg['text']}" for seg in segments
    )
