from datetime import datetime, timezone


def create_call_doc(filename: str, file_path: str = "", transcript: str = "",
                    diarized_transcript: str = "", agent_customer_transcript: str = "",
                    uploaded_by: str = "", agent_id: str = "") -> dict:
    return {
        "filename": filename,
        "file_path": file_path,
        "transcript": transcript,
        "diarized_transcript": diarized_transcript,
        "agent_customer_transcript": agent_customer_transcript,
        "corrected_conversation": [],
        "normalized_conversation": [],
        "conversation_summary": "",
        "role_mapping": {},
        "conversation_metrics": {},
        "quality_findings": {},
        "pipeline_timing": {},
        "pipeline_debug": {},
        "processing_status": "pending",
        "uploaded_by": uploaded_by,
        "agent_id": agent_id,
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
        "diarized_transcript": doc.get("diarized_transcript", ""),
        "agent_customer_transcript": doc.get("agent_customer_transcript", ""),
        "corrected_conversation": doc.get("corrected_conversation", []),
        "normalized_conversation": doc.get("normalized_conversation", []),
        "conversation_summary": doc.get("conversation_summary", ""),
        "role_mapping": doc.get("role_mapping", {}),
        "conversation_metrics": doc.get("conversation_metrics", {}),
        "quality_findings": doc.get("quality_findings", {}),
        "pipeline_timing": doc.get("pipeline_timing", {}),
        "pipeline_debug": doc.get("pipeline_debug", {}),
        "processing_status": doc.get("processing_status", "pending"),
        "uploaded_by": doc.get("uploaded_by", ""),
        "agent_id": doc.get("agent_id", ""),
        "created_at": created_at or "",
    }
