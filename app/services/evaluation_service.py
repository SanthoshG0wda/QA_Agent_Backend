import asyncio
import logging
import time
from ..config import ENABLE_NIM
from ..ai.groq_client import evaluate_transcript
from ..ai.nim_client import detect_critical_errors
from ..models.evaluation import create_evaluation_doc
from ..database import get_db
from ..services.conversation_reconstruction import reconstruct_from_utterances
from ..services.conversation_normalizer import normalize_conversation, normalized_to_text, calculate_metrics
from ..services.role_detector import heuristic_detect_roles, validate_agent_text

logger = logging.getLogger(__name__)


def _convert_corrected_to_text(corrected: list[dict]) -> str:
    return "\n\n".join(
        f"[{m['speaker']}]\n{m['text']}" for m in corrected if m.get("text", "").strip()
    )


async def _nim_skipped():
    return {"critical_error": False, "errors": [], "nim_skipped": True}


async def evaluate_call(call_doc: dict, deepgram_utterances: list[dict], raw_transcript: str = "") -> dict:
    """Full conversation pipeline using Deepgram utterances.

    Deepgram handles both STT and diarization. This pipeline:
    1. Reconstructs utterance segments from Deepgram
    2. Runs Groq QA + NIM concurrently (NIM optional via ENABLE_NIM)
    3. Falls back to heuristic role detection if needed
    4. Always saves evaluation to MongoDB

    Returns dict with all pipeline artifacts. Never raises on AI failures.
    """

    timing = {}
    warnings = []
    t_total = time.time()

    # ── Stage 1: Reconstruct conversation from Deepgram utterances ──
    t0 = time.time()
    segments, labeled_text = reconstruct_from_utterances(deepgram_utterances)
    timing["reconstruction"] = round(time.time() - t0, 3)
    logger.info("TIMING [reconstruction]: %.3f s (%d segments)", timing["reconstruction"], len(segments))

    # Use raw transcript if no utterances available (Deepgram fallback)
    input_for_ai = labeled_text or raw_transcript or call_doc.get("transcript", "")

    # ── Stage 2: Groq + NIM concurrently ──────────────────────────
    t1 = time.time()
    groq_default = {
        "agent": "SPEAKER_00",
        "customer": "SPEAKER_01",
        "confidence": 0.0,
        "overall_score": 0,
        "strengths": [],
        "improvements": [],
        "critical_error": False,
        "errors": [],
        "conversation_summary": "",
        "quality_findings": {},
        "opening_score": 0, "communication_score": 0, "listening_score": 0,
        "knowledge_score": 0, "discovery_score": 0, "call_control_score": 0,
        "professionalism_score": 0, "compliance_score": 0, "closing_score": 0,
    }
    try:
        t_groq = time.time()
        groq_task = evaluate_transcript(input_for_ai)
        nim_task = detect_critical_errors(input_for_ai) if ENABLE_NIM else _nim_skipped()

        results = await asyncio.gather(groq_task, nim_task, return_exceptions=True)

        if isinstance(results[0], Exception):
            logger.error("Groq evaluation failed: %s", results[0], exc_info=True)
            warnings.append(f"Groq AI evaluation failed: {results[0]}")
            groq_result = dict(groq_default)
            groq_result["groq_error"] = True
        else:
            groq_result = results[0]
            timing["groq"] = round(time.time() - t_groq, 3)
            logger.info("TIMING [groq]: %.3f s", timing["groq"])

        if isinstance(results[1], Exception):
            logger.error("NIM error detection failed: %s", results[1], exc_info=True)
            warnings.append(f"NVIDIA NIM critical error detection failed: {results[1]}")
            nim_result = {"critical_error": False, "errors": [], "nim_error": True}
        else:
            nim_result = results[1]
            if nim_result.get("nim_skipped"):
                timing["nim"] = 0.0
                logger.info("TIMING [nim]: skipped (ENABLE_NIM=false)")
            else:
                timing["nim"] = round(time.time() - t_groq - (timing.get("groq", 0)), 3)
                logger.info("TIMING [nim]: %.3f s", timing["nim"])
    except Exception as e:
        logger.error("AI concurrent execution failed: %s", e, exc_info=True)
        groq_result = dict(groq_default)
        groq_result["groq_error"] = True
        nim_result = {"critical_error": False, "errors": [], "nim_error": True}

    timing["ai_total"] = round(time.time() - t1, 3)
    logger.info("TIMING [ai_total]: %.3f s", timing["ai_total"])

    # ── Extract role mapping ─────────────────────────────────────
    heuristic_used = False
    role_diagnostics = {}

    # When Groq returns a corrected_conversation (AI reconstruction), use it directly
    if groq_result.get("corrected_conversation"):
        corrected = groq_result["corrected_conversation"]
        role_mapping = {
            "agent": groq_result.get("agent", "SPEAKER_00"),
            "customer": groq_result.get("customer", "SPEAKER_01"),
            "confidence": groq_result.get("confidence", 0.0),
        }
        normalized = corrected
        agent_customer_text = _convert_corrected_to_text(corrected)

        agent_texts = [m["text"] for m in corrected if m.get("speaker") == "Agent"]
        if agent_texts:
            validation = validate_agent_text(agent_texts)
            if not validation["valid"]:
                logger.warning(
                    "AI reconstruction validation failed (issues: %s), role confidence=%.2f",
                    validation["issues"], role_mapping["confidence"],
                )
            role_mapping["validation"] = validation
    elif segments:
        ai_roles = {
            "agent": groq_result.get("agent", "SPEAKER_00"),
            "customer": groq_result.get("customer", "SPEAKER_01"),
            "confidence": groq_result.get("confidence", 0.0),
        }
        role_mapping = dict(ai_roles)

        should_fallback = (
            role_mapping["confidence"] < 0.80
            or role_mapping["confidence"] == 0.0
            or groq_result.get("agent") is None
        )
        if should_fallback:
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
            logger.info("Heuristic fallback completed in %.3f s", timing["heuristic_fallback"])

        normalized = normalize_conversation(segments, role_mapping)
        agent_customer_text = normalized_to_text(normalized)

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
                logger.info("Validation correction completed in %.3f s", timing["validation_correction"])
    else:
        normalized = []
        agent_customer_text = raw_transcript or call_doc.get("transcript", "")
        role_mapping = {"agent": "Speaker_0", "customer": "Speaker_1", "confidence": 0.5}
        warnings.append("No utterance segments available — using raw transcript only")

    # ── Calculate metrics ────────────────────────────────────────
    metrics = calculate_metrics(normalized) if normalized else {}

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

    groq_err = groq_result.get("critical_error", False)
    nim_err = nim_result.get("critical_error", False)
    combined = list(dict.fromkeys(
        groq_result.get("errors", []) + nim_result.get("errors", [])
    ))

    conversation_summary = groq_result.get("conversation_summary", "")
    quality_findings = groq_result.get("quality_findings", {})

    # ── Always store evaluation ──────────────────────────────────
    eval_status = "completed"
    eval_error = None

    if groq_result.get("groq_error") and nim_result.get("nim_error"):
        eval_status = "failed"
        eval_error = "Both Groq and NIM AI services failed"
        warnings.append("Both AI services failed — partial or zero scores saved")
    elif groq_result.get("groq_error"):
        warnings.append("Groq evaluation partially failed — using fallback scores")
        eval_status = "completed"
    elif nim_result.get("nim_error"):
        warnings.append("NIM critical error detection unavailable")

    db = get_db()
    if db is None:
        logger.error("Cannot save evaluation — database not connected")
        return {
            "evaluation_id": "",
            "error": "Database not connected",
            "warnings": warnings + ["Database not connected"],
            "status": "failed",
            "agent_customer_transcript": agent_customer_text,
            "corrected_conversation": groq_result.get("corrected_conversation", []),
            "normalized_conversation": normalized,
            "conversation_summary": conversation_summary,
            "role_mapping": role_mapping,
            "conversation_metrics": metrics,
            "quality_findings": quality_findings,
            "pipeline_timing": timing,
            "pipeline_debug": {},
            "processing_metrics": {},
        }

    eval_doc = create_evaluation_doc(
        call_id=str(call_doc.get("_id", "")),
        scores=scores,
        strengths=strengths,
        improvements=improvements,
        critical_error=groq_err or nim_err,
        critical_errors=combined,
        status=eval_status,
        warnings=warnings,
        error=eval_error,
    )

    t2 = time.time()
    eval_result = await db.evaluations.insert_one(eval_doc)
    timing["database_insert"] = round(time.time() - t2, 3)
    logger.info("TIMING [database_insert]: %.3f s", timing["database_insert"])

    timing["total"] = round(time.time() - t_total, 3)
    logger.info("TIMING [total_pipeline]: %.3f s", timing["total"])

    processing_metrics = {
        "total_seconds": timing["total"],
        "reconstruction_seconds": timing.get("reconstruction", 0),
        "groq_seconds": timing.get("groq", 0),
        "nim_seconds": timing.get("nim", 0),
        "ai_total_seconds": timing.get("ai_total", 0),
        "database_insert_seconds": timing.get("database_insert", 0),
        "utterance_count": len(deepgram_utterances),
        "speaker_count": len({u.get("speaker") for u in deepgram_utterances}) if deepgram_utterances else 0,
        "nim_enabled": ENABLE_NIM,
        "heuristic_fallback_used": heuristic_used,
    }

    pipeline_debug = {
        "deepgram_utterances": len(deepgram_utterances),
        "reconstructed_segments": len(segments),
        "role_confidence": role_mapping.get("confidence", 0),
        "heuristic_used": heuristic_used,
        "merged_segments": len(normalized),
        "agent_score": role_diagnostics.get("agent_score", 0),
        "customer_score": role_diagnostics.get("customer_score", 0),
        "correction_applied": heuristic_used,
        "validation": role_mapping.get("validation", {}),
        "warnings": warnings,
        "groq_error": groq_result.get("groq_error", False),
        "nim_error": nim_result.get("nim_error", False),
        "processing_metrics": processing_metrics,
    }

    return {
        "evaluation_id": str(eval_result.inserted_id),
        "agent_customer_transcript": agent_customer_text,
        "corrected_conversation": groq_result.get("corrected_conversation", []),
        "normalized_conversation": normalized,
        "conversation_summary": conversation_summary,
        "role_mapping": role_mapping,
        "conversation_metrics": metrics,
        "quality_findings": quality_findings,
        "pipeline_timing": timing,
        "pipeline_debug": pipeline_debug,
        "processing_metrics": processing_metrics,
        "warnings": warnings,
        "status": eval_status,
        "error": eval_error,
    }
