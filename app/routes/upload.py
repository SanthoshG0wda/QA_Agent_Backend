import os
import uuid
import asyncio
import logging
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from ..config import UPLOAD_DIR, FAST_MODE
from ..database import get_db
from ..models.call import create_call_doc, call_to_dict
from ..auth.token_utils import get_current_user
from ..services.transcription import transcribe_audio
from ..services.diarization import diarize_audio, merge_with_transcript
from ..services.evaluation_service import evaluate_call

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_id(id_str: str, name: str = "id") -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise HTTPException(400, f"Invalid {name}: '{id_str}' is not a valid ID")


async def _process_upload(call_id: str, file_path: str):
    """Background processor for uploaded calls."""
    db = get_db()
    if db is None:
        return

    try:
        obj_id = _validate_id(call_id, "call_id")
    except HTTPException:
        return

    await db.calls.update_one({"_id": obj_id}, {"$set": {"processing_status": "processing"}})

    try:
        plain_transcript, whisper_segments = await transcribe_audio(file_path)
        raw_transcript = plain_transcript

        diarized = ""
        if not FAST_MODE and whisper_segments:
            diarization_segments = await diarize_audio(file_path)
            if diarization_segments:
                diarized = merge_with_transcript(whisper_segments, diarization_segments)

        call_doc = await db.calls.find_one({"_id": obj_id})
        if not call_doc:
            return

        eval_result = await evaluate_call(call_doc, diarized, raw_transcript)

        update_fields = {"processing_status": "completed"}
        if plain_transcript:
            update_fields["transcript"] = plain_transcript
        if diarized:
            update_fields["diarized_transcript"] = diarized
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

        await db.calls.update_one({"_id": obj_id}, {"$set": update_fields})

        logger.info(
            "Upload %s processed in %.2f s (FAST_MODE=%s)",
            call_id, eval_result.get("pipeline_timing", {}).get("total", 0), FAST_MODE,
        )
    except Exception as e:
        logger.error("Upload processing %s failed: %s", call_id, e, exc_info=True)
        await db.calls.update_one(
            {"_id": obj_id},
            {"$set": {"processing_status": "failed"}},
        )


@router.post("/upload")
async def upload_audio(file: UploadFile = File(...), payload: dict = Depends(get_current_user)):
    if not file.filename:
        raise HTTPException(400, "No file provided")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1] or ".wav"
    stored_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    call_doc = create_call_doc(
        filename=file.filename,
        file_path=file_path,
        uploaded_by=payload.get("sub", ""),
    )
    result = await db.calls.insert_one(call_doc)
    call_id = str(result.inserted_id)

    asyncio.create_task(_process_upload(call_id, file_path))

    return {
        "call_id": call_id,
        "status": "pending",
        "message": "Upload received. Processing started.",
    }


@router.get("/calls")
async def list_calls(_=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    docs = await db.calls.find().sort("created_at", -1).to_list(100)
    return [call_to_dict(d) for d in docs]


@router.get("/calls/{call_id}")
async def get_call(call_id: str, _=Depends(get_current_user)):
    obj_id = _validate_id(call_id, "call_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    doc = await db.calls.find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(404, "Call not found")
    return call_to_dict(doc)


@router.get("/calls/{call_id}/evaluation")
async def get_call_evaluation(call_id: str, _=Depends(get_current_user)):
    obj_id = _validate_id(call_id, "call_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    call_doc = await db.calls.find_one({"_id": obj_id})
    if not call_doc:
        raise HTTPException(404, "Call not found")
    eval_doc = await db.evaluations.find_one({"call_id": call_id})
    if not eval_doc:
        return {
            "id": "",
            "call_id": call_id,
            "processing_status": call_doc.get("processing_status", "pending"),
            "transcript": call_doc.get("transcript", ""),
            "diarized_transcript": call_doc.get("diarized_transcript", ""),
            "agent_customer_transcript": call_doc.get("agent_customer_transcript", ""),
            "corrected_conversation": call_doc.get("corrected_conversation", []),
            "normalized_conversation": call_doc.get("normalized_conversation", []),
            "conversation_summary": call_doc.get("conversation_summary", ""),
            "role_mapping": call_doc.get("role_mapping", {}),
            "conversation_metrics": call_doc.get("conversation_metrics", {}),
            "quality_findings": call_doc.get("quality_findings", {}),
            "pipeline_timing": call_doc.get("pipeline_timing", {}),
            "agent_id": call_doc.get("agent_id", ""),
            "agent_name": "",
            "agent_department": "",
        }
    from ..models.evaluation import evaluation_to_dict
    result = evaluation_to_dict(eval_doc)
    result["transcript"] = call_doc.get("transcript", "")
    result["diarized_transcript"] = call_doc.get("diarized_transcript", "")
    result["agent_customer_transcript"] = call_doc.get("agent_customer_transcript", "")
    result["corrected_conversation"] = call_doc.get("corrected_conversation", [])
    result["normalized_conversation"] = call_doc.get("normalized_conversation", [])
    result["conversation_summary"] = call_doc.get("conversation_summary", "")
    result["role_mapping"] = call_doc.get("role_mapping", {})
    result["conversation_metrics"] = call_doc.get("conversation_metrics", {})
    result["quality_findings"] = call_doc.get("quality_findings", {})
    result["pipeline_timing"] = call_doc.get("pipeline_timing", {})
    result["processing_status"] = call_doc.get("processing_status", "completed")
    agent_id = call_doc.get("agent_id", "")
    if agent_id:
        try:
            agent_doc = await db.agents.find_one({"_id": _validate_id(agent_id, "agent_id")})
            result["agent_name"] = agent_doc.get("name", "") if agent_doc else ""
            result["agent_department"] = agent_doc.get("department", "") if agent_doc else ""
        except HTTPException:
            result["agent_name"] = ""
            result["agent_department"] = ""
    else:
        result["agent_name"] = ""
        result["agent_department"] = ""
    return result


@router.delete("/calls/{call_id}")
async def delete_call(call_id: str, payload: dict = Depends(get_current_user)):
    obj_id = _validate_id(call_id, "call_id")
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    if payload.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    result = await db.calls.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Call not found")
    return {"ok": True}
