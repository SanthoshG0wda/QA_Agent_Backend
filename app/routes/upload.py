import asyncio
import logging
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from ..database import get_db
from ..models.call import create_call_doc, call_to_dict
from ..models.notification import create_notification_doc
from ..auth.token_utils import get_current_user
from ..services.transcription import transcribe_audio
from ..services.evaluation_service import evaluate_call
from ..config import MAX_CONCURRENT_JOBS

logger = logging.getLogger(__name__)
router = APIRouter()

# Strong reference set to prevent GC from collecting background tasks
_background_tasks: set[asyncio.Task] = set()
_PROCESSING_TIMEOUT = 300  # 5 minutes max per call

# Concurrency control semaphore — limits simultaneous Deepgram/Groq/NIM calls
_processing_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

# Queue tracking
_queued_count = 0
_running_count = 0


async def _update_progress(call_id: str, progress: int, status: str = None):
    db = get_db()
    if db is None:
        return
    try:
        obj_id = _validate_id(call_id, "call_id")
        update = {"progress": progress}
        if status:
            update["processing_status"] = status
        await db.calls.update_one({"_id": obj_id}, {"$set": update})
    except Exception:
        pass


def _validate_id(id_str: str, name: str = "id") -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise HTTPException(400, f"Invalid {name}: '{id_str}' is not a valid ID")


async def _run_with_timeout(call_id: str, audio_bytes: bytes, content_type: str):
    global _queued_count, _running_count
    _queued_count += 1
    await _update_progress(call_id, 0, "queued")
    try:
        async with _processing_semaphore:
            _queued_count -= 1
            _running_count += 1
            await _update_progress(call_id, 5, "processing")
            await asyncio.wait_for(_process_upload(call_id, audio_bytes, content_type), timeout=_PROCESSING_TIMEOUT)
            _running_count -= 1
    except asyncio.TimeoutError:
        _queued_count -= 1
        _running_count -= 1
        logger.error("Upload %s: processing timed out after %ds", call_id, _PROCESSING_TIMEOUT)
        db = get_db()
        if db is not None:
            try:
                obj_id = _validate_id(call_id, "call_id")
                await db.calls.update_one(
                    {"_id": obj_id},
                    {"$set": {"processing_status": "failed", "error": "Processing timed out"}},
                )
            except Exception:
                pass


async def _process_upload(call_id: str, audio_bytes: bytes, content_type: str):
    db = get_db()
    if db is None:
        return

    try:
        obj_id = _validate_id(call_id, "call_id")
    except HTTPException:
        return

    await db.calls.update_one({"_id": obj_id}, {"$set": {"processing_status": "processing", "progress": 10}})

    update_fields = {}
    try:
        await _update_progress(call_id, 15)

        # Reuse existing transcript if already stored (for re-evaluations)
        existing_call = await db.calls.find_one({"_id": obj_id}, {"transcript": 1, "deepgram_utterances": 1})
        if existing_call and existing_call.get("transcript") and existing_call.get("deepgram_utterances"):
            raw_transcript = existing_call["transcript"]
            utterances = existing_call["deepgram_utterances"]
            logger.info("Upload %s: reusing existing transcript (%d utterances)", call_id, len(utterances))
        else:
            await _update_progress(call_id, 20)
            raw_transcript, utterances, duration_seconds = await transcribe_audio(audio_bytes, content_type)
            update_fields["transcript"] = raw_transcript
            update_fields["deepgram_utterances"] = utterances
            update_fields["duration_seconds"] = duration_seconds
            logger.info("Upload %s: Deepgram transcription completed (%d utterances, %.1fs)", call_id, len(utterances), duration_seconds)

        await _update_progress(call_id, 40)

        call_doc = await db.calls.find_one({"_id": obj_id})
        if not call_doc:
            return

        try:
            await _update_progress(call_id, 50)
            eval_result = await evaluate_call(call_doc, utterances, raw_transcript)
            await _update_progress(call_id, 90)
        except Exception as e:
            logger.error("Upload %s: evaluation pipeline failed: %s", call_id, e, exc_info=True)
            update_fields["processing_status"] = "failed"
            update_fields["eval_error"] = str(e)
            update_fields["progress"] = 0
            await db.calls.update_one({"_id": obj_id}, {"$set": update_fields})
            return

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

        eval_status = eval_result.get("status", "completed")
        update_fields["processing_status"] = eval_status
        if eval_result.get("error"):
            update_fields["eval_error"] = eval_result["error"]

        update_fields["overall_score"] = eval_result.get("overall_score", 0)
        update_fields["critical_error"] = eval_result.get("critical_error", False)
        update_fields["progress"] = 100

        await db.calls.update_one({"_id": obj_id}, {"$set": update_fields})

        if eval_status == "completed":
            asyncio.create_task(_create_notification(obj_id, eval_result))

        logger.info(
            "Upload %s processed in %.2f s (status=%s)",
            call_id, eval_result.get("pipeline_timing", {}).get("total", 0), eval_status,
        )
    except Exception as e:
        logger.error("Upload processing %s failed: %s", call_id, e, exc_info=True)
        update_fields["processing_status"] = "failed"
        update_fields["error"] = str(e)
        update_fields["progress"] = 0
        await db.calls.update_one(
            {"_id": obj_id},
            {"$set": update_fields},
        )


async def _create_notification(obj_id, eval_result):
    try:
        db = get_db()
        if db is None:
            return
        call_doc = await db.calls.find_one({"_id": obj_id})
        if call_doc:
            agent_name = call_doc.get("agent_name", "Unknown")
            dept_name = call_doc.get("department_name", "")
            score = eval_result.get("overall_score", eval_result.get("processing_metrics", {}).get("overall_score", 0))
            notif = create_notification_doc(
                user_id=call_doc.get("uploaded_by", ""),
                evaluation_id=eval_result.get("evaluation_id", ""),
                title="Evaluation Completed",
                message=f"{agent_name} - {dept_name}\nScore: {score}/100",
            )
            await db.notifications.insert_one(notif)
    except Exception:
        logger.warning("Failed to create notification (non-blocking)", exc_info=True)


async def _next_job_id(db) -> str:
    from datetime import datetime
    year = datetime.utcnow().strftime("%Y")
    prefix = f"EVL-{year}-"
    last = await db.calls.find_one({"job_id": {"$regex": f"^{prefix}"}}, sort=[("job_id", -1)])
    if last:
        last_num = int(last["job_id"].split("-")[-1])
        new_num = last_num + 1
    else:
        new_num = 1
    return f"{prefix}{new_num:05d}"


@router.post("/upload")
async def upload_audio(
    file: UploadFile = File(...),
    agent_id: str = Form(""),
    agent_name: str = Form(""),
    department_id: str = Form(""),
    department_name: str = Form(""),
    notes: str = Form(""),
    payload: dict = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(400, "No file provided")

    content = await file.read()
    content_type = file.content_type or "audio/wav"

    db = get_db()
    if db is None:
        raise HTTPException(503, "Database not connected")

    if agent_id and not agent_name:
        try:
            agent_doc = await db.agents.find_one({"_id": _validate_id(agent_id, "agent_id")})
            if agent_doc:
                agent_name = agent_doc.get("name", "")
                if not department_id:
                    department_id = agent_doc.get("department_id", "")
                if not department_name:
                    department_name = agent_doc.get("department_name", "")
        except HTTPException:
            pass

    job_id = await _next_job_id(db)

    call_doc = create_call_doc(
        filename=file.filename,
        uploaded_by=payload.get("sub", ""),
        agent_id=agent_id,
        agent_name=agent_name,
        department_id=department_id,
        department_name=department_name,
        notes=notes,
        job_id=job_id,
    )
    result = await db.calls.insert_one(call_doc)
    call_id = str(result.inserted_id)

    task = asyncio.create_task(_run_with_timeout(call_id, content, content_type))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "call_id": call_id,
        "job_id": job_id,
        "status": "processing",
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
            "deepgram_utterances": call_doc.get("deepgram_utterances", []),
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
