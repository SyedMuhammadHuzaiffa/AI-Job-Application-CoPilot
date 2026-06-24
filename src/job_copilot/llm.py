import json
from copy import deepcopy
from typing import Any

from .config import DEFAULT_MODEL, SETTINGS
from .exceptions import OpenAIConfigError
from .llm_client import ChatClient, get_default_chat_client
from .logging_config import get_logger
from .profile import profile_to_prompt_text
from .prompts import SYSTEM_PROMPT, build_user_prompt


logger = get_logger(__name__)


DEFAULT_RESULT: dict[str, Any] = {
    "job": {
        "title": "",
        "company": "",
        "location": "",
        "apply_link": "",
    },
    "fit": {
        "score": 0,
        "ats_match_percent": 0,
        "strengths": [],
        "gaps": [],
        "skill_gaps": [],
        "recommended_learning_topics": [],
        "strategy": [],
    },
    "ats_keywords": [],
    "cv": {
        "summary": "",
        "skills_to_highlight": [],
        "bullets": [],
    },
    "cover_letter": {
        "recipient": "Hiring Manager",
        "body": [],
    },
    "application_answers": [],
    "linkedin_outreach": {
        "connection_note": "",
        "recruiter_message": "",
        "follow_up_message": "",
    },
    "interview_prep": {
        "technical_questions": [],
        "behavioral_questions": [],
    },
    "approval_checklist": [],
}


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object.")
    return parsed


def _bounded_percent(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, min(100, number))


def _normalize_result(data: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(DEFAULT_RESULT)

    for section in result:
        if section in data:
            result[section] = data[section]

    if not isinstance(result["job"], dict):
        result["job"] = deepcopy(DEFAULT_RESULT["job"])

    if not isinstance(result["fit"], dict):
        result["fit"] = deepcopy(DEFAULT_RESULT["fit"])

    result["fit"]["score"] = _bounded_percent(result["fit"].get("score", 0))
    result["fit"]["ats_match_percent"] = _bounded_percent(
        result["fit"].get("ats_match_percent", 0)
    )

    for key in ("strengths", "gaps", "skill_gaps", "recommended_learning_topics", "strategy"):
        result["fit"][key] = [str(item).strip() for item in _ensure_list(result["fit"].get(key)) if str(item).strip()]

    if not result["fit"]["skill_gaps"] and result["fit"]["gaps"]:
        result["fit"]["skill_gaps"] = result["fit"]["gaps"]

    result["ats_keywords"] = [
        str(item).strip() for item in _ensure_list(result.get("ats_keywords")) if str(item).strip()
    ]

    if not isinstance(result["cv"], dict):
        result["cv"] = deepcopy(DEFAULT_RESULT["cv"])
    result["cv"]["skills_to_highlight"] = [
        str(item).strip()
        for item in _ensure_list(result["cv"].get("skills_to_highlight"))
        if str(item).strip()
    ]

    bullets = []
    for item in _ensure_list(result["cv"].get("bullets")):
        if isinstance(item, dict):
            source = str(item.get("source", "")).strip()
            tailored = str(item.get("tailored", "")).strip()
            if tailored:
                bullets.append({"source": source, "tailored": tailored})
        elif str(item).strip():
            bullets.append({"source": "Not specified", "tailored": str(item).strip()})
    result["cv"]["bullets"] = bullets

    if not isinstance(result["cover_letter"], dict):
        result["cover_letter"] = deepcopy(DEFAULT_RESULT["cover_letter"])
    result["cover_letter"]["recipient"] = str(
        result["cover_letter"].get("recipient") or "Hiring Manager"
    ).strip()
    result["cover_letter"]["body"] = [
        str(item).strip()
        for item in _ensure_list(result["cover_letter"].get("body"))
        if str(item).strip()
    ]

    answers = []
    for item in _ensure_list(result.get("application_answers")):
        if isinstance(item, dict):
            question = str(item.get("question", "")).strip()
            answer = str(item.get("answer", "")).strip()
            if question or answer:
                answers.append({"question": question, "answer": answer})
    result["application_answers"] = answers

    if not isinstance(result["linkedin_outreach"], dict):
        result["linkedin_outreach"] = deepcopy(DEFAULT_RESULT["linkedin_outreach"])
    for key in ("connection_note", "recruiter_message", "follow_up_message"):
        result["linkedin_outreach"][key] = str(result["linkedin_outreach"].get(key, "") or "").strip()

    if not isinstance(result["interview_prep"], dict):
        result["interview_prep"] = deepcopy(DEFAULT_RESULT["interview_prep"])
    for key in ("technical_questions", "behavioral_questions"):
        result["interview_prep"][key] = [
            str(item).strip()
            for item in _ensure_list(result["interview_prep"].get(key))
            if str(item).strip()
        ]

    result["approval_checklist"] = [
        str(item).strip()
        for item in _ensure_list(result.get("approval_checklist"))
        if str(item).strip()
    ]

    return result


def generate_tailoring(
    profile: dict[str, Any],
    job_description: str,
    model: str | None = None,
    temperature: float = 0.2,
    chat_client: ChatClient | None = None,
) -> dict[str, Any]:
    """Generate fit analysis and tailored application material."""
    selected_model = model or SETTINGS.default_model or DEFAULT_MODEL
    client = chat_client or get_default_chat_client(SETTINGS)
    logger.info("Generating tailored application draft with model=%s", selected_model)
    content = client.create_json_chat(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(profile_to_prompt_text(profile), job_description),
        model=selected_model,
        temperature=temperature,
    )
    return _normalize_result(_parse_json_object(content))
