import logging
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Depends
from ..database import get_db
from ..services.evaluation_service import evaluate_call
from ..models.evaluation import evaluation_to_dict
from ..auth.token_utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_id(id_str: str, name: str = "id") -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise HTTPException(400, f"Invalid {name}: '{id_str}' is not a valid ID")


@router.post("/evaluate/{call_id}")
async def evaluate_call_endpoint(call_id: str, _=Depends(get_current_user)):
    obj_id = _validate_id(call_id, "call_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")

    call_doc = await db.calls.find_one({"_id": obj_id})
    if not call_doc:
        raise HTTPException(404, "Call not found")

    await db.calls.update_one({"_id": obj_id}, {"$set": {"processing_status": "processing"}})

    raw_transcript = call_doc.get("transcript", "")
    utterances = call_doc.get("deepgram_utterances", [])

    try:
        eval_result = await evaluate_call(call_doc, utterances, raw_transcript)
    except Exception as e:
        logger.error("Evaluation pipeline failed for call %s: %s", call_id, e, exc_info=True)
        await db.calls.update_one(
            {"_id": obj_id},
            {"$set": {"processing_status": "failed", "eval_error": str(e)}},
        )
        raise HTTPException(500, f"Evaluation failed: {e}")

    update_fields = {"processing_status": "completed"}
    if raw_transcript:
        update_fields["transcript"] = raw_transcript
    if utterances:
        update_fields["deepgram_utterances"] = utterances
    if eval_result.get("agent_customer_transcript"):
        update_fields["agent_customer_transcript"] = eval_result["agent_customer_transcript"]
    if eval_result.get("corrected_conversation"):
        update_fields["corrected_conversation"] = eval_result["corrected_conversation"]
    if eval_result.get("normalized_conversation"):
        update_fields["normalized_conversation"] = eval_result["normalized_conversation"]
    if eval_result.get("conversation_summary"):
        update_fields["conversation_summary"] = eval_result["conversation_summary"]
    if eval_result.get("role_mapping"):
        update_fields["role_mapping"] = eval_result["role_mapping"]
    if eval_result.get("conversation_metrics"):
        update_fields["conversation_metrics"] = eval_result["conversation_metrics"]
    if eval_result.get("quality_findings"):
        update_fields["quality_findings"] = eval_result["quality_findings"]
    if eval_result.get("pipeline_timing"):
        update_fields["pipeline_timing"] = eval_result["pipeline_timing"]
    if eval_result.get("pipeline_debug"):
        update_fields["pipeline_debug"] = eval_result["pipeline_debug"]
    if eval_result.get("processing_metrics"):
        update_fields["processing_metrics"] = eval_result["processing_metrics"]

    await db.calls.update_one({"_id": obj_id}, {"$set": update_fields})

    logger.info(
        "Call %s evaluated in %.2f s (status=%s)",
        call_id, eval_result.get("pipeline_timing", {}).get("total", 0),
        eval_result.get("status", "completed"),
    )

    return {"evaluation_id": eval_result["evaluation_id"]}


@router.get("/evaluation/{evaluation_id}")
async def get_evaluation(evaluation_id: str, _=Depends(get_current_user)):
    obj_id = _validate_id(evaluation_id, "evaluation_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    doc = await db.evaluations.find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(404, "Evaluation not found")

    result = evaluation_to_dict(doc)
    try:
        call_obj_id = _validate_id(doc.get("call_id", ""), "call_id")
        call_doc = await db.calls.find_one({"_id": call_obj_id})
    except HTTPException:
        call_doc = None

    if call_doc:
        result["transcript"] = call_doc.get("transcript", "")
        result["deepgram_utterances"] = call_doc.get("deepgram_utterances", [])
        result["agent_customer_transcript"] = call_doc.get("agent_customer_transcript", "")
        result["corrected_conversation"] = call_doc.get("corrected_conversation", [])
        result["normalized_conversation"] = call_doc.get("normalized_conversation", [])
        result["conversation_summary"] = call_doc.get("conversation_summary", "")
        result["role_mapping"] = call_doc.get("role_mapping", {})
        result["conversation_metrics"] = call_doc.get("conversation_metrics", {})
        result["quality_findings"] = call_doc.get("quality_findings", {})
        result["pipeline_timing"] = call_doc.get("pipeline_timing", {})
        result["processing_status"] = call_doc.get("processing_status", "completed")
        result["agent_id"] = call_doc.get("agent_id", "")
        agent_id = call_doc.get("agent_id", "")
        if agent_id:
            try:
                agent_obj_id = _validate_id(agent_id, "agent_id")
                agent_doc = await db.agents.find_one({"_id": agent_obj_id})
                result["agent_name"] = agent_doc.get("name", "") if agent_doc else ""
                result["agent_department"] = agent_doc.get("department", "") if agent_doc else ""
            except HTTPException:
                result["agent_name"] = ""
                result["agent_department"] = ""
        else:
            result["agent_name"] = ""
            result["agent_department"] = ""
    else:
        result["transcript"] = ""
        result["deepgram_utterances"] = []
        result["agent_customer_transcript"] = ""
        result["corrected_conversation"] = []
        result["normalized_conversation"] = []
        result["conversation_summary"] = ""
        result["role_mapping"] = {}
        result["conversation_metrics"] = {}
        result["quality_findings"] = {}
        result["pipeline_timing"] = {}
        result["processing_status"] = ""
        result["agent_id"] = ""
        result["agent_name"] = ""
        result["agent_department"] = ""
    return result


@router.get("/calls/{call_id}/status")
async def get_call_status(call_id: str, _=Depends(get_current_user)):
    obj_id = _validate_id(call_id, "call_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    call_doc = await db.calls.find_one({"_id": obj_id})
    if not call_doc:
        raise HTTPException(404, "Call not found")
    status = call_doc.get("processing_status", "pending")
    result = {"call_id": call_id, "status": status, "progress": call_doc.get("progress", 0)}
    if status == "failed":
        result["error"] = call_doc.get("transcript_error") or call_doc.get("eval_error") or "Processing failed"
    eval_doc = await db.evaluations.find_one({"call_id": call_id})
    if eval_doc:
        result["evaluation_id"] = str(eval_doc["_id"])
        result["evaluation_status"] = eval_doc.get("status", "completed")
    return result


@router.get("/evaluations")
async def list_evaluations(_=Depends(get_current_user)):
    try:
        db = get_db()
        if db is None:
            raise HTTPException(503, "Database not connected")
        docs = await db.evaluations.find().sort("created_at", -1).to_list(length=100)
        return [evaluation_to_dict(doc) for doc in docs]
    except Exception as e:
        logger.error("List evaluations failed: %s", e, exc_info=True)
        raise HTTPException(500, str(e))
