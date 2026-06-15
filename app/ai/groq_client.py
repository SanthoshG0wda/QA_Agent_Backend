import httpx
import json
import logging
import time
from ..config import GROQ_API_KEY, GROQ_MODEL
from ..services.role_identifier import SYSTEM_PROMPT
from ..services.timing import record_timing

logger = logging.getLogger(__name__)


async def evaluate_transcript(transcript: str) -> dict:
    if not GROQ_API_KEY:
        return _fallback_result()

    t0 = time.time()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Evaluate this call transcript:\n\n{transcript}"},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        record_timing("groq", time.time() - t0)
        return result


def _fallback_result() -> dict:
    return {
        "agent": "SPEAKER_00",
        "customer": "SPEAKER_01",
        "confidence": 0.5,
        "opening_score": 5,
        "communication_score": 8,
        "listening_score": 8,
        "knowledge_score": 8,
        "discovery_score": 5,
        "call_control_score": 5,
        "professionalism_score": 5,
        "compliance_score": 3,
        "closing_score": 3,
        "overall_score": 50,
        "strengths": ["Transcript available"],
        "improvements": ["Set GROQ_API_KEY for AI evaluation"],
        "critical_error": False,
        "errors": [],
        "conversation_summary": "",
        "quality_findings": {
            "missing_introduction": False,
            "missing_company_name": False,
            "missing_discovery_questions": False,
            "missing_objection_handling": False,
            "missing_call_closing": False,
            "details": [],
        },
    }
