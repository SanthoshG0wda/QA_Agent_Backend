import os
import uuid
import logging
import time
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from ..config import UPLOAD_DIR
from ..database import get_db
from ..models.agent import create_agent_doc, agent_to_dict
from ..models.call import create_call_doc
from ..models.evaluation import evaluation_to_dict
from ..auth.token_utils import get_current_user, require_role
from ..services.transcription import transcribe_audio
from ..services.diarization import diarize_audio, merge_with_transcript
from ..services.evaluation_service import evaluate_call
from ..services.timing import record_timing

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_id(id_str: str, name: str = "id") -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise HTTPException(400, f"Invalid {name}: '{id_str}' is not a valid ID")


@router.post("/agents")
async def create_agent(body: dict, _=Depends(require_role("admin"))):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    name = body.get("name", "").strip()
    email = body.get("email", "").strip().lower()
    department = body.get("department", "").strip()
    if not name or not email:
        raise HTTPException(400, "Name and email are required")
    existing = await db.agents.find_one({"email": email})
    if existing:
        raise HTTPException(400, "Agent with this email already exists")
    doc = create_agent_doc(name, email, department)
    result = await db.agents.insert_one(doc)
    return {"id": str(result.inserted_id)}


@router.get("/agents")
async def list_agents(_=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    docs = await db.agents.find().sort("created_at", -1).to_list(100)
    result = []
    for doc in docs:
        agent_id = str(doc["_id"])
        calls_count = await db.calls.count_documents({"agent_id": agent_id})
        evals = await db.evaluations.find({"call_id": {"$in": [
            str(c["_id"]) for c in await db.calls.find({"agent_id": agent_id}).to_list(1000)
        ]}}).to_list(1000)
        total_score = sum(e.get("overall_score", 0) for e in evals)
        avg = round(total_score / len(evals), 1) if evals else 0
        entry = agent_to_dict(doc)
        entry["total_calls"] = calls_count
        entry["average_score"] = avg
        result.append(entry)
    return result


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, _=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    doc = await db.agents.find_one({"_id": _validate_id(agent_id, "agent_id")})
    if not doc:
        raise HTTPException(404, "Agent not found")
    calls_count = await db.calls.count_documents({"agent_id": agent_id})
    evals = await db.evaluations.find({"call_id": {"$in": [
        str(c["_id"]) for c in await db.calls.find({"agent_id": agent_id}).to_list(1000)
    ]}}).to_list(1000)
    total_score = sum(e.get("overall_score", 0) for e in evals)
    critical_count = sum(1 for e in evals if e.get("critical_error"))
    entry = agent_to_dict(doc)
    entry["total_calls"] = calls_count
    entry["average_score"] = round(total_score / len(evals), 1) if evals else 0
    entry["critical_errors"] = critical_count
    return entry


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, _=Depends(require_role("admin"))):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    result = await db.agents.delete_one({"_id": _validate_id(agent_id, "agent_id")})
    if result.deleted_count == 0:
        raise HTTPException(404, "Agent not found")
    return {"ok": True}


async def _process_agent_call(call_id: str, file_path: str):
    """Background processor for agent call uploads."""
    import asyncio
    from ..services.transcription import transcribe_audio
    from ..services.diarization import diarize_audio, merge_with_transcript
    from ..services.evaluation_service import evaluate_call
    from ..config import FAST_MODE

    db = get_db()
    if db is None:
        return

    await db.calls.update_one({"_id": _validate_id(call_id, "call_id")}, {"$set": {"processing_status": "processing"}})

    try:
        plain_transcript, whisper_segments = await transcribe_audio(file_path)
        raw_transcript = plain_transcript

        diarized = ""
        if not FAST_MODE and whisper_segments:
            diarization_segments = await diarize_audio(file_path)
            if diarization_segments:
                diarized = merge_with_transcript(whisper_segments, diarization_segments)

        call_doc = await db.calls.find_one({"_id": _validate_id(call_id, "call_id")})
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

        await db.calls.update_one({"_id": _validate_id(call_id, "call_id")}, {"$set": update_fields})

        logger.info(
            "Agent call %s processed in %.2f s (FAST_MODE=%s)",
            call_id, eval_result.get("pipeline_timing", {}).get("total", 0), FAST_MODE,
        )
    except Exception as e:
        logger.error("Agent call %s processing failed: %s", call_id, e, exc_info=True)
        await db.calls.update_one(
            {"_id": _validate_id(call_id, "call_id")},
            {"$set": {"processing_status": "failed"}},
        )


@router.post("/agents/{agent_id}/upload")
async def upload_agent_call(agent_id: str, file: UploadFile = File(...),
                            _=Depends(require_role("admin"))):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    agent_doc = await db.agents.find_one({"_id": _validate_id(agent_id, "agent_id")})
    if not agent_doc:
        raise HTTPException(404, "Agent not found")
    if not file.filename:
        raise HTTPException(400, "No file provided")

    import asyncio
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1] or ".wav"
    stored_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_name)
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    call_doc_data = create_call_doc(filename=file.filename, file_path=file_path,
                                    uploaded_by=str(agent_doc["_id"]))
    call_doc_data["agent_id"] = agent_id
    result = await db.calls.insert_one(call_doc_data)
    call_id = str(result.inserted_id)

    asyncio.create_task(_process_agent_call(call_id, file_path))

    return {
        "call_id": call_id,
        "status": "pending",
        "message": "Call upload received. Processing started. Poll GET /api/calls/{id} for status.",
    }


@router.get("/agents/{agent_id}/evaluations")
async def agent_evaluations(agent_id: str, _=Depends(get_current_user)):
    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")
    agent_doc = await db.agents.find_one({"_id": _validate_id(agent_id, "agent_id")})
    if not agent_doc:
        raise HTTPException(404, "Agent not found")
    calls = await db.calls.find({"agent_id": agent_id}).to_list(1000)
    call_ids = [str(c["_id"]) for c in calls]
    evals = await db.evaluations.find({"call_id": {"$in": call_ids}}).sort("created_at", -1).to_list(100)
    result = []
    for e in evals:
        entry = evaluation_to_dict(e)
        call_doc = next((c for c in calls if str(c["_id"]) == e.get("call_id")), None)
        entry["filename"] = call_doc.get("filename", "") if call_doc else ""
        result.append(entry)
    return result
