import httpx
import logging
import time
from ..config import NVIDIA_API_KEY, NVIDIA_MODEL, NVIDIA_BASE_URL
from ..services.timing import record_timing
from ..services.json_parser import safe_json_parse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a compliance and error detection system for call center recordings.
The transcript contains speakers labeled [SPEAKER_00], [SPEAKER_01], [Agent], [Customer], etc.
Identify which speaker is the Agent (call center employee), then analyze only the Agent's statements.
Ignore Customer statements.

Critical errors to detect in Agent behavior:
1. Abusive language - swearing, threats, harassment
2. Incorrect information - false claims about products, pricing, policies
3. Compliance violation - missing required disclosures, regulatory breaches
4. Company misrepresentation - falsely claiming authority, misleading about company
5. Privacy violation - sharing PII without consent, mishandling sensitive data
6. Missing company identification - agent failed to identify their company

Return JSON only:
{
  "critical_error": true/false,
  "errors": ["list of error descriptions"]
}

If no critical errors found:
{
  "critical_error": false,
  "errors": []
}"""


async def detect_critical_errors(transcript: str) -> dict:
    if not NVIDIA_API_KEY:
        return {"critical_error": False, "errors": []}

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {NVIDIA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": NVIDIA_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Analyze this transcript for critical errors:\n\n{transcript}"},
                    ],
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = safe_json_parse(content, {
                "critical_error": False,
                "errors": [],
                "parse_warning": True,
            })
            record_timing("nim", time.time() - t0)
            return result
    except httpx.HTTPStatusError as e:
        logger.error("NIM HTTP error: %s - %s", e.response.status_code, e.response.text[:500])
    except httpx.TimeoutException:
        logger.error("NIM request timed out after 120s")
    except Exception as e:
        logger.error("NIM request failed: %s", e, exc_info=True)

    record_timing("nim", time.time() - t0)
    return {
        "critical_error": False,
        "errors": [],
        "nim_error": True,
    }
