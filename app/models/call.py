from datetime import datetime, timezone


def create_call_doc(filename: str, transcript: str = "",
                    uploaded_by: str = "", agent_id: str = "",
                    agent_name: str = "", department_id: str = "",
                    department_name: str = "", duration_seconds: int = 0,
                    notes: str = "", job_id: str = "") -> dict:
    return {
        "filename": filename,
        "transcript": transcript,
        "deepgram_utterances": [],
        "agent_customer_transcript": "",
        "corrected_conversation": [],
        "normalized_conversation": [],
        "conversation_summary": "",
        "role_mapping": {},
        "conversation_metrics": {},
        "quality_findings": {},
        "pipeline_timing": {},
        "pipeline_debug": {},
        "processing_metrics": {},
        "processing_status": "pending",
        "progress": 0,
        "uploaded_by": uploaded_by,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "department_id": department_id,
        "department_name": department_name,
        "duration_seconds": duration_seconds,
        "notes": notes,
        "job_id": job_id,
        "overall_score": 0,
        "critical_error": False,
        "created_at": datetime.now(timezone.utc),
    }


def call_to_dict(doc) -> dict:
    created_at = doc.get("created_at")
    if created_at is not None:
        created_at = created_at.isoformat()
    return {
        "id": str(doc.get("_id", "")),
        "filename": doc.get("filename", ""),
        "transcript": doc.get("transcript", ""),
        "deepgram_utterances": doc.get("deepgram_utterances", []),
        "agent_customer_transcript": doc.get("agent_customer_transcript", ""),
        "corrected_conversation": doc.get("corrected_conversation", []),
        "normalized_conversation": doc.get("normalized_conversation", []),
        "conversation_summary": doc.get("conversation_summary", ""),
        "role_mapping": doc.get("role_mapping", {}),
        "conversation_metrics": doc.get("conversation_metrics", {}),
        "quality_findings": doc.get("quality_findings", {}),
        "pipeline_timing": doc.get("pipeline_timing", {}),
        "pipeline_debug": doc.get("pipeline_debug", {}),
        "processing_metrics": doc.get("processing_metrics", {}),
        "processing_status": doc.get("processing_status", "pending"),
        "progress": doc.get("progress", 0),
        "uploaded_by": doc.get("uploaded_by", ""),
        "agent_id": doc.get("agent_id", ""),
        "agent_name": doc.get("agent_name", ""),
        "department_id": doc.get("department_id", ""),
        "department_name": doc.get("department_name", ""),
        "duration_seconds": doc.get("duration_seconds", 0),
        "notes": doc.get("notes", ""),
        "job_id": doc.get("job_id", ""),
        "overall_score": doc.get("overall_score", 0),
        "critical_error": doc.get("critical_error", False),
        "created_at": created_at or "",
    }
