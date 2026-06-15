import httpx
import logging
import time
from ..config import GROQ_API_KEY, GROQ_MODEL
from ..services.timing import record_timing
from ..services.json_parser import safe_json_parse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Call Quality Analyst and conversation reconstructor.

INPUT HANDLING:
- If the transcript has speaker labels ([SPEAKER_00], [Agent], [Customer], etc.), parse them into a structured conversation.
- If the transcript is raw text WITHOUT speaker labels, reconstruct the conversation by identifying who is speaking based on context and content cues.

RECONSTRUCTION RULES (for raw transcripts):
- The Agent introduces themselves, mentions their company, leads the conversation, explains products.
- The Customer gives short replies, answers questions, requests clarification.
- Split the text into natural speaking turns. Each turn becomes one entry in corrected_conversation.
- Merge consecutive same-speaker segments into a single message.
- Remove empty/filler segments.

ROLE IDENTIFICATION:
- Identify which speaker is Agent and which is Customer.
- Rate your confidence (0.0 to 1.0) in the role assignment.

EVALUATION (always evaluate ONLY the Agent):
- opening_score: max 10 (greeting, introduction, company name, confirmation, purpose)
- communication_score: max 15 (clarity, confidence, grammar, professionalism)
- listening_score: max 15 (interruptions, acknowledgment, follow-ups, understanding)
- knowledge_score: max 15 (product knowledge, correct info, explanation, objection handling)
- discovery_score: max 10 (probing questions, requirements, pain points)
- call_control_score: max 10 (logical flow, focus, objection management)
- professionalism_score: max 10 (respect, empathy, positive attitude)
- compliance_score: max 5 (required disclosures, confidentiality)
- closing_score: max 5 (summary, next steps, ending)
- overall_score: max 100 (sum of all)

Also provide:
- strengths: array of strings
- improvements: array of strings

CRITICAL ERROR DETECTION (Agent only):
Check for: abusive language, incorrect information, compliance violations, company misrepresentation, privacy violations, missing company identification.

CONVERSATION SUMMARY: 2-3 sentences describing the call.

QUALITY FINDINGS:
- missing_introduction: Agent did not introduce themselves
- missing_company_name: Agent did not mention their company
- missing_discovery_questions: Agent asked no discovery questions
- missing_objection_handling: Agent did not address concerns
- missing_call_closing: Agent did not close properly

Return ONLY valid JSON with this exact structure:
{
  "agent": "SPEAKER_00",
  "customer": "SPEAKER_01",
  "confidence": 0.95,
  "corrected_conversation": [
    {"speaker": "Agent", "text": "Hello. This is Seema calling."},
    {"speaker": "Customer", "text": "Hi."}
  ],
  "opening_score": 0,
  "communication_score": 0,
  "listening_score": 0,
  "knowledge_score": 0,
  "discovery_score": 0,
  "call_control_score": 0,
  "professionalism_score": 0,
  "compliance_score": 0,
  "closing_score": 0,
  "overall_score": 0,
  "strengths": [],
  "improvements": [],
  "critical_error": false,
  "errors": [],
  "conversation_summary": "",
  "quality_findings": {
    "missing_introduction": false,
    "missing_company_name": false,
    "missing_discovery_questions": false,
    "missing_objection_handling": false,
    "missing_call_closing": false,
    "details": []
  }
}"""


async def evaluate_transcript(transcript: str) -> dict:
    if not GROQ_API_KEY:
        return _fallback_result()

    t0 = time.time()
    try:
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
            result = safe_json_parse(content, _fallback_result())
            record_timing("groq", time.time() - t0)
            return result
    except httpx.HTTPStatusError as e:
        logger.error("Groq HTTP error: %s - %s", e.response.status_code, e.response.text[:500])
    except httpx.TimeoutException:
        logger.error("Groq request timed out after 120s")
    except Exception as e:
        logger.error("Groq request failed: %s", e, exc_info=True)

    record_timing("groq", time.time() - t0)
    result = _fallback_result()
    result["groq_error"] = True
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
