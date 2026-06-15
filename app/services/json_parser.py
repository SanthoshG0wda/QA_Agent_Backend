import json
import re
import logging

logger = logging.getLogger(__name__)


def safe_json_parse(content: str, default: dict | None = None) -> dict:
    if not content or not content.strip():
        logger.warning("safe_json_parse: empty content")
        return _fallback(default)

    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    if content.startswith("```"):
        lines = content.splitlines()
        cleaned = []
        for line in lines:
            if line.strip().startswith("```"):
                continue
            cleaned.append(line)
        cleaned_str = "\n".join(cleaned).strip()
        try:
            return json.loads(cleaned_str)
        except json.JSONDecodeError:
            pass

    brace_match = re.search(r"\{.*\}", content, re.DOTALL)
    if brace_match:
        candidate = brace_match.group()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    bracket_match = re.search(r"\[.*\]", content, re.DOTALL)
    if bracket_match:
        candidate = bracket_match.group()
        try:
            result = json.loads(candidate)
            if isinstance(result, list):
                return {"items": result, "parse_warning": True}
        except json.JSONDecodeError:
            pass

    logger.warning(
        "safe_json_parse: could not extract JSON from: %.200s",
        content.replace("\n", " "),
    )
    return _fallback(default)


def _fallback(default: dict | None) -> dict:
    if default is not None:
        return default
    return {
        "parse_error": True,
        "error": "Could not parse AI response as JSON",
    }
