import logging
import re

logger = logging.getLogger(__name__)

# --- Weighted Signal Definitions ---

# Rule 1: Strong Agent introduction signals (+50 each)
INTRODUCTION_SIGNALS = [
    (r"\bthis is\s+\w+", 50),
    (r"\bmy name is\b", 50),
    (r"\bI['']?m\s+calling\b", 50),
    (r"\bcalling from\b", 50),
    (r"\bI['']?m\s+\w+\s+(?:from|with)\b", 50),
    (r"\bfollowing up\b", 40),
    (r"\bthe reason I['']?m calling\b", 50),
    (r"\bI represent\b", 50),
    (r"\bI work for\b", 50),
    (r"\bI work at\b", 50),
    (r"\bI'm reaching out\b", 40),
    (r"\bI'd like to\s+(?:talk|speak|discuss|introduce)\b", 40),
]

# Rule 2: Product explanation signals (+30 each)
PRODUCT_SIGNALS = [
    (r"\blaunch(?:ed|ing)?\b", 30),
    (r"\bnew\s+product\b", 30),
    (r"\bproduct\s+(?:feature|benefit|launch|line)\b", 30),
    (r"\bpricing?\b", 30),
    (r"\boffer\b", 30),
    (r"\bdiscount\b", 30),
    (r"\bpromotion\b", 30),
    (r"\bpackage\b", 30),
    (r"\bsubscription\b", 30),
    (r"\bprice\b", 30),
    (r"\brate\b", 25),
    (r"\bdeal\b", 25),
    (r"\bsave\s+\d+%\b", 30),
    (r"\b\d+%\s+(?:off|discount|launch)\b", 30),
    (r"\bintroduc(?:e|ing|tion)\s+(?:our|a|the)\b", 30),
    (r"\bhere['']?s what we\b", 25),
    (r"\bwe have\s+(?:\w+\s+){0,3}(?:product|service|offer|plan|package)\b", 25),
    (r"\bwe offer\b", 25),
    (r"\bwe provide\b", 25),
    (r"\bwe specialize\b", 25),
]

# Agent conversation leadership signals (+15 each)
LEADERSHIP_SIGNALS = [
    (r"\bhow\s+(?:are|can|may|would|do)\b", 15),
    (r"\bwhat\s+(?:is|are|do|would|about)\b", 15),
    (r"\bwould you like\b", 15),
    (r"\bdo you have any questions\b", 15),
    (r"\blet me explain\b", 15),
    (r"\bI want to discuss\b", 15),
    (r"\bthe reason\b", 10),
    (r"\bfirst of all\b", 10),
    (r"\bthank you for\b", 10),
    (r"\bI appreciate\b", 10),
]

# General Agent signals (+5 each)
AGENT_GENERAL = [
    (r"\bcompany\b", 5),
    (r"\bproduct\b", 5),
    (r"\bservice\b", 5),
    (r"\bsolution\b", 5),
    (r"\bcommunity\b", 5),
    (r"\bteam\b", 5),
    (r"\bcustomer\b", 5),
    (r"\baccount\b", 5),
    (r"\bhave a good\b", 5),
    (r"\bwould you be interested\b", 5),
    (r"\bI can help\b", 5),
    (r"\bdo you need\b", 5),
]

# Rule 4: Strong Customer short response signals (+10 each)
CUSTOMER_SHORT = [
    (r"^yes$", 10),
    (r"^no$", 10),
    (r"^okay$", 10),
    (r"^ok$", 10),
    (r"^sure$", 10),
    (r"^right$", 8),
    (r"^good$", 8),
    (r"^bye$", 8),
    (r"^thanks$", 8),
    (r"^got it$", 10),
    (r"^thank you$", 8),
    (r"\blet me check\b", 10),
    (r"\bsend\s+(?:me|the)\s+(?:details?|info)\b", 10),
    (r"\bI['']?ll\s+(?:check|see|let you know|get back)\b", 10),
    (r"\bI need to\s+(?:check|ask|think|confirm)\b", 10),
    (r"\bcan you (?:send|share|email|text)\b", 10),
    (r"\bplease send\b", 10),
    (r"\bI['']?m\s+(?:good|fine|okay|doing well)\b", 8),
    (r"\bI['']?m\s+doing\s+good\b", 8),
]

# General Customer signals (+3 each)
CUSTOMER_GENERAL = [
    (r"\byes\b", 3),
    (r"\bno\b", 3),
    (r"\bokay\b", 3),
    (r"\bsure\b", 3),
    (r"\buh huh\b", 3),
    (r"\bmm[ -]?hmm\b", 3),
    (r"\bthanks?\b", 3),
    (r"\bthank you\b", 3),
    (r"\bI see\b", 3),
    (r"\bI understand\b", 3),
    (r"\bthat makes sense\b", 3),
    (r"\bgoodbye\b", 3),
    (r"\bbye\b", 3),
    (r"\bhave a good\b", 3),
    (r"\bquestion\b", 3),
    (r"\bwhat does that mean\b", 3),
    (r"\bcan you explain\b", 3),
    (r"\bcan you repeat\b", 3),
    (r"\bI didn['']?t catch\b", 3),
]


def score_speaker_weighted(texts: list[str]) -> dict:
    """Score how Agent-like and Customer-like a speaker's texts are, using weighted signals."""
    agent_score = 0
    customer_score = 0
    intro_score = 0
    product_score = 0
    leadership_score = 0
    combined = " ".join(texts).lower()
    word_count = len(combined.split())
    question_count = combined.count("?")
    text_len = len(combined)

    for pattern, weight in INTRODUCTION_SIGNALS:
        if re.search(pattern, combined):
            agent_score += weight
            intro_score += weight

    for pattern, weight in PRODUCT_SIGNALS:
        if re.search(pattern, combined):
            agent_score += weight
            product_score += weight

    for pattern, weight in LEADERSHIP_SIGNALS:
        if re.search(pattern, combined):
            agent_score += weight
            leadership_score += weight

    for pattern, weight in AGENT_GENERAL:
        if re.search(pattern, combined):
            agent_score += weight

    for pattern, weight in CUSTOMER_SHORT:
        if re.search(pattern, combined):
            customer_score += weight

    for pattern, weight in CUSTOMER_GENERAL:
        if re.search(pattern, combined):
            customer_score += weight

    return {
        "agent_score": agent_score,
        "customer_score": customer_score,
        "introduction_score": intro_score,
        "product_score": product_score,
        "leadership_score": leadership_score,
        "word_count": word_count,
        "question_count": question_count,
        "text_length": text_len,
    }


# Rule 5: Long monologue / topic continuity detection
PRODUCT_TOPIC_MARKERS = [
    r"\bproduct\b", r"\blaunch\b", r"\bdiscount\b", r"\boffer\b",
    r"\bprice\b", r"\bpackage\b", r"\bpromotion\b", r"\bdeal\b",
    r"\bsubscription\b", r"\bplan\b", r"\boption\b", r"\bfeature\b",
    r"\bbenefit\b", r"\bservice\b", r"\bsolution\b", r"\brate\b",
]


def _has_product_topic(text: str) -> bool:
    """Check if text discusses product-related topics."""
    lower = text.lower()
    return any(re.search(p, lower) for p in PRODUCT_TOPIC_MARKERS)


# Rule 6: Agent text validation (Rule 10)
def validate_agent_text(agent_texts: list[str]) -> dict:
    """Verify Agent text contains expected elements. Returns validation result."""
    combined = " ".join(agent_texts).lower()
    has_introduction = any(
        re.search(p, combined) for p, _ in INTRODUCTION_SIGNALS
    )
    has_company_mention = bool(
        re.search(r"\bfrom\s+\w+", combined)
        or re.search(r"\b(?:at|with)\s+\w+", combined)
        or "company" in combined
        or "team" in combined
    )
    has_product_discussion = _has_product_topic(combined)
    issues = []
    if not has_introduction:
        issues.append("missing_introduction")
    if not has_company_mention:
        issues.append("missing_company_mention")
    return {
        "valid": has_introduction or has_company_mention,
        "has_introduction": has_introduction,
        "has_company_mention": has_company_mention,
        "has_product_discussion": has_product_discussion,
        "issues": issues,
    }


def heuristic_detect_roles(segments: list[dict]) -> dict:
    """Rule-based role detection using weighted signal analysis.

    Implements Rules 1-6 from the conversation intelligence layer.
    Returns role mapping with full diagnostics.
    """
    if not segments:
        return {"agent": "SPEAKER_00", "customer": "SPEAKER_01", "confidence": 0.0,
                "agent_score": 0, "customer_score": 0, "correction_applied": False}

    # Group texts by speaker
    speaker_texts: dict[str, list[str]] = {}
    speaker_original: dict[str, list[str]] = {}
    for seg in segments:
        speaker = seg.get("speaker", "UNKNOWN")
        text = seg.get("text", "")
        if speaker not in speaker_texts:
            speaker_texts[speaker] = []
            speaker_original[speaker] = []
        speaker_texts[speaker].append(text)
        speaker_original[speaker].append(text)

    # Score each speaker
    speaker_scores = {}
    for speaker, texts in speaker_texts.items():
        scores = score_speaker_weighted(texts)
        speaker_scores[speaker] = scores

    speakers = list(speaker_scores.keys())

    if len(speakers) == 1:
        return {"agent": speakers[0], "customer": speakers[0], "confidence": 0.9,
                "agent_score": speaker_scores[speakers[0]]["agent_score"],
                "customer_score": speaker_scores[speakers[0]]["customer_score"],
                "correction_applied": False}

    # Find best agent (highest agent score)
    best_agent = max(speakers, key=lambda s: speaker_scores[s]["agent_score"])

    # Find best customer (highest customer score, not same as agent)
    remaining = [s for s in speakers if s != best_agent]
    if remaining:
        best_customer = max(remaining, key=lambda s: speaker_scores[s]["customer_score"])
    else:
        best_customer = best_agent

    # If the best agent has zero agent score, fall back to word count
    if speaker_scores[best_agent]["agent_score"] == 0:
        best_agent = max(speakers, key=lambda s: speaker_scores[s]["word_count"])
        remaining = [s for s in speakers if s != best_agent]
        if remaining:
            best_customer = max(remaining, key=lambda s: speaker_scores[s]["customer_score"])
        else:
            best_customer = best_agent

    agent_sc = speaker_scores[best_agent]["agent_score"]
    customer_sc = speaker_scores[best_agent]["customer_score"]
    total_sc = agent_sc + customer_sc

    # Calculate confidence based on score gap
    if total_sc > 0:
        confidence = round(agent_sc / total_sc, 2)
    else:
        confidence = 0.5

    confidence = min(max(confidence, 0.5), 0.99)

    logger.info(
        "Heuristic roles: agent=%s (score=%d, intro=%d, product=%d, leadership=%d, words=%d), "
        "customer=%s (score=%d), confidence=%.2f",
        best_agent, agent_sc,
        speaker_scores[best_agent]["introduction_score"],
        speaker_scores[best_agent]["product_score"],
        speaker_scores[best_agent]["leadership_score"],
        speaker_scores[best_agent]["word_count"],
        best_customer, speaker_scores[best_customer]["customer_score"],
        confidence,
    )

    correction_applied = True  # Heuristic was used (as opposed to pure AI)

    return {
        "agent": best_agent,
        "customer": best_customer,
        "confidence": confidence,
        "agent_score": agent_sc,
        "customer_score": customer_sc,
        "correction_applied": correction_applied,
        "speaker_scores": {
            s: {
                "agent_score": speaker_scores[s]["agent_score"],
                "customer_score": speaker_scores[s]["customer_score"],
                "word_count": speaker_scores[s]["word_count"],
            }
            for s in speakers
        },
    }
