import logging

logger = logging.getLogger(__name__)


def normalize_conversation(segments: list[dict], role_mapping: dict) -> list[dict]:
    """Convert SPEAKER_0X labeled segments to Agent/Customer structured format."""
    if not segments:
        return []

    agent_label = role_mapping.get("agent", "SPEAKER_00")
    customer_label = role_mapping.get("customer", "SPEAKER_01")

    normalized = []
    for seg in segments:
        speaker = seg.get("speaker", "UNKNOWN")
        text = seg.get("text", "").strip()
        if not text:
            continue
        if speaker == agent_label:
            role = "Agent"
        elif speaker == customer_label:
            role = "Customer"
        else:
            role = speaker
        normalized.append({"speaker": role, "text": text})

    return normalized


def normalized_to_text(normalized: list[dict]) -> str:
    """Convert normalized conversation back to [Agent]/[Customer] text format."""
    return "\n\n".join(
        f"[{msg['speaker']}]\n{msg['text']}" for msg in normalized
    )


def calculate_metrics(normalized: list[dict]) -> dict:
    """Calculate conversation metrics from normalized conversation."""
    if not normalized:
        return {
            "agent_message_count": 0,
            "customer_message_count": 0,
            "total_messages": 0,
            "agent_word_count": 0,
            "customer_word_count": 0,
            "total_words": 0,
            "agent_talk_percentage": 0.0,
            "customer_talk_percentage": 0.0,
            "avg_response_time_estimate": 0.0,
            "total_interactions": 0,
        }

    agent_words = 0
    customer_words = 0
    agent_msgs = 0
    customer_msgs = 0
    transitions = 0
    prev_speaker = None

    for msg in normalized:
        speaker = msg.get("speaker", "")
        text = msg.get("text", "")
        word_count = len(text.split())

        if speaker == "Agent":
            agent_words += word_count
            agent_msgs += 1
        elif speaker == "Customer":
            customer_words += word_count
            customer_msgs += 1

        if prev_speaker and speaker != prev_speaker:
            transitions += 1
        prev_speaker = speaker

    total_words = agent_words + customer_words
    total_msgs = agent_msgs + customer_msgs

    return {
        "agent_message_count": agent_msgs,
        "customer_message_count": customer_msgs,
        "total_messages": total_msgs,
        "agent_word_count": agent_words,
        "customer_word_count": customer_words,
        "total_words": total_words,
        "agent_talk_percentage": round((agent_words / total_words * 100), 1) if total_words else 0.0,
        "customer_talk_percentage": round((customer_words / total_words * 100), 1) if total_words else 0.0,
        "avg_response_time_estimate": round(transitions / max(total_msgs, 1), 3),
        "total_interactions": transitions,
    }
