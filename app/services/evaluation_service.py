import asyncio
import logging
import time
from ..config import FAST_MODE
from ..ai.groq_client import evaluate_transcript
from ..ai.nim_client import detect_critical_errors
from ..models.evaluation import create_evaluation_doc
from ..database import get_db
from ..services.role_identifier import replace_speaker_labels
from ..services.conversation_cleaner import clean_and_merge_pipeline, segments_to_text
from ..services.conversation_normalizer import normalize_conversation, normalized_to_text, calculate_metrics
from ..services.role_detector import heuristic_detect_roles, validate_agent_text
from ..services.timing import record_timing

logger = logging.getLogger(__name__)


def _convert_corrected_to_text(corrected: list[dict]) -> str:
    """Convert corrected_conversation array back to [Agent]/[Customer] text."""
    return "\n\n".join(
        f"[{m['speaker']}]\n{m['text']}" for m in corrected if m.get("text", "").strip()
    )


async def evaluate_call(call_doc: dict, diarized: str = "", raw_transcript: str = "") -> dict:
    """Full conversation pipeline.

    In FAST_MODE: skips diarization, uses AI conversation reconstruction from raw transcript.
    In LEGACY_MODE: uses diarized transcript with speaker labels.

    Returns dict with all pipeline artifacts.
    """

    timing = {}
    t_total = time.time()

    # ── Determine input ──────────────────────────────────────────
    if FAST_MODE:
        # FAST_MODE: use raw transcript, AI reconstructs speakers
        input_for_ai = raw_transcript or call_doc.get("transcript", "") or call_doc.get("agent_customer_transcript", "")
        logger.info("FAST_MODE enabled — skipping diarization, using AI reconstruction")
    else:
        # LEGACY_MODE: use diarized or labeled transcript
        input_for_ai = diarized or call_doc.get("agent_customer_transcript") or call_doc.get("transcript", "")

    # ── Clean & merge segments (for legacy mode or as heuristic backup) ──
    t0 = time.time()
    segments, clean_diarized = clean_and_merge_pipeline(input_for_ai)
    timing["cleanup_merge"] = round(time.time() - t0, 3)

    # ── Run Groq + NIM concurrently ──────────────────────────────
    t1 = time.time()
    groq_result, nim_result = await asyncio.gather(
        evaluate_transcript(clean_diarized),
        detect_critical_errors(clean_diarized),
    )
    timing["groq_nim_concurrent"] = round(time.time() - t1, 3)

    # ── Extract role mapping ─────────────────────────────────────
    heuristic_used = False
    role_diagnostics = {}

    if FAST_MODE and groq_result.get("corrected_conversation"):
        corrected = groq_result["corrected_conversation"]
        role_mapping = {
            "agent": groq_result.get("agent", "SPEAKER_00"),
            "customer": groq_result.get("customer", "SPEAKER_01"),
            "confidence": groq_result.get("confidence", 0.0),
        }
        normalized = corrected
        agent_customer_text = _convert_corrected_to_text(corrected)

        # Validate AI-reconstructed Agent text
        agent_texts = [m["text"] for m in corrected if m.get("speaker") == "Agent"]
        if agent_texts:
            validation = validate_agent_text(agent_texts)
            if not validation["valid"]:
                logger.warning(
                    "AI reconstruction validation failed (issues: %s), role confidence=%.2f",
                    validation["issues"], role_mapping["confidence"],
                )
            role_mapping["validation"] = validation
    else:
        # Use role mapping from Groq result
        ai_roles = {
            "agent": groq_result.get("agent", "SPEAKER_00"),
            "customer": groq_result.get("customer", "SPEAKER_01"),
            "confidence": groq_result.get("confidence", 0.0),
        }
        role_mapping = dict(ai_roles)

        # Fallback to heuristics if low confidence
        should_fallback = (
            role_mapping["confidence"] < 0.80
            or role_mapping["confidence"] == 0.0
            or groq_result.get("agent") is None
        )
        if should_fallback and segments:
            logger.info(
                "Low AI confidence (%.2f), applying heuristic fallback",
                role_mapping["confidence"],
            )
            t_fb = time.time()
            hr = heuristic_detect_roles(segments)
            role_mapping = {
                "agent": hr["agent"],
                "customer": hr["customer"],
                "confidence": hr["confidence"],
            }
            role_diagnostics = {
                "agent_score": hr.get("agent_score", 0),
                "customer_score": hr.get("customer_score", 0),
                "speaker_scores": hr.get("speaker_scores", {}),
            }
            heuristic_used = True
            timing["heuristic_fallback"] = round(time.time() - t_fb, 3)

        # Normalize conversation
        normalized = normalize_conversation(segments, role_mapping)
        agent_customer_text = normalized_to_text(normalized)

        # Rule 10: Validate agent text, force heuristic if needed
        agent_texts = [m["text"] for m in normalized if m["speaker"] == "Agent"]
        if agent_texts and not heuristic_used:
            validation = validate_agent_text(agent_texts)
            if not validation["valid"] and segments:
                logger.warning(
                    "Validation failed (issues: %s), forcing heuristic correction",
                    validation["issues"],
                )
                t_val = time.time()
                hr = heuristic_detect_roles(segments)
                role_mapping = {
                    "agent": hr["agent"],
                    "customer": hr["customer"],
                    "confidence": hr["confidence"],
                }
                role_diagnostics = {
                    "agent_score": hr.get("agent_score", 0),
                    "customer_score": hr.get("customer_score", 0),
                    "speaker_scores": hr.get("speaker_scores", {}),
                }
                heuristic_used = True
                normalized = normalize_conversation(segments, role_mapping)
                agent_customer_text = normalized_to_text(normalized)
                timing["validation_correction"] = round(time.time() - t_val, 3)

    # ── Calculate metrics ────────────────────────────────────────
    metrics = calculate_metrics(normalized)

    # ── Build scores from Groq result ────────────────────────────
    scores = {
        "opening_score": groq_result.get("opening_score", 0),
        "communication_score": groq_result.get("communication_score", 0),
        "listening_score": groq_result.get("listening_score", 0),
        "knowledge_score": groq_result.get("knowledge_score", 0),
        "discovery_score": groq_result.get("discovery_score", 0),
        "call_control_score": groq_result.get("call_control_score", 0),
        "professionalism_score": groq_result.get("professionalism_score", 0),
        "compliance_score": groq_result.get("compliance_score", 0),
        "closing_score": groq_result.get("closing_score", 0),
        "overall_score": groq_result.get("overall_score", 0),
    }

    strengths = groq_result.get("strengths", [])
    improvements = groq_result.get("improvements", [])

    # Merge critical errors from Groq + NIM
    groq_err = groq_result.get("critical_error", False)
    nim_err = nim_result.get("critical_error", False)
    combined = list(dict.fromkeys(
        groq_result.get("errors", []) + nim_result.get("errors", [])
    ))

    conversation_summary = groq_result.get("conversation_summary", "")
    quality_findings = groq_result.get("quality_findings", {})

    # ── Store evaluation ─────────────────────────────────────────
    db = get_db()
    eval_doc = create_evaluation_doc(
        call_id=str(call_doc.get("_id", "")),
        scores=scores,
        strengths=strengths,
        improvements=improvements,
        critical_error=groq_err or nim_err,
        critical_errors=combined,
    )
    t2 = time.time()
    eval_result = await db.evaluations.insert_one(eval_doc)
    timing["database_insert"] = round(time.time() - t2, 3)

    timing["total"] = round(time.time() - t_total, 3)

    pipeline_debug = {
        "fast_mode": FAST_MODE,
        "role_confidence": role_mapping.get("confidence", 0),
        "heuristic_used": heuristic_used,
        "merged_segments": len(normalized),
        "agent_score": role_diagnostics.get("agent_score", 0),
        "customer_score": role_diagnostics.get("customer_score", 0),
        "correction_applied": heuristic_used,
        "validation": role_mapping.get("validation", {}),
    }

    return {
        "evaluation_id": str(eval_result.inserted_id),
        "agent_customer_transcript": agent_customer_text,
        "corrected_conversation": normalized if FAST_MODE else [],
        "normalized_conversation": normalized,
        "conversation_summary": conversation_summary,
        "role_mapping": role_mapping,
        "conversation_metrics": metrics,
        "quality_findings": quality_findings,
        "pipeline_timing": timing,
        "pipeline_debug": pipeline_debug,
    }
