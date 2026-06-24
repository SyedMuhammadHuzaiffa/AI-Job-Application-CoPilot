import json
import textwrap
from copy import deepcopy
from typing import Any

from .config import DEFAULT_MODEL, SETTINGS
from .exceptions import OpenAIConfigError
from .llm_client import ChatClient, get_default_chat_client
from .logging_config import get_logger
from .profile import profile_to_prompt_text


logger = get_logger(__name__)
APPLY_LABELS = {"Strong Apply", "Apply", "Stretch Apply", "Low Probability"}

SYSTEM_PROMPT = """You are a Resume Intelligence Engine for a truthful job application co-pilot.

Compare the candidate profile, current CV text, and job description. Your job is to help the candidate decide whether to apply and how to optimize the CV before applying.

Hard confidence rules:
- Never invent experience.
- Never add technologies not present in the candidate profile or current CV.
- Never claim professional experience for academic or personal projects.
- Never convert suggested keywords into factual claims.
- If evidence is weak or missing, say so directly.
- Always explain recommendations.
- Keep recommendations concise and professional.

Return only valid JSON with this exact shape:
{
  "scores": {
    "overall_match_score": 0,
    "ats_match_score": 0,
    "technical_match_score": 0,
    "experience_match_score": 0,
    "education_match_score": 0
  },
  "missing_keywords": {
    "present_in_profile": [],
    "missing_from_profile": [],
    "mentioned_in_projects_but_not_cv": [],
    "mentioned_in_skills_but_not_summary": []
  },
  "project_prioritization": [
    {
      "project_name": "",
      "relevance_score": 0,
      "why_it_matters": "",
      "recommended_bullet_points": []
    }
  ],
  "skill_prioritization": {
    "skills_to_move_higher": [
      {
        "skill": "",
        "reason": ""
      }
    ],
    "skills_to_remove_from_focus": [
      {
        "skill": "",
        "reason": ""
      }
    ],
    "skills_to_emphasize": [
      {
        "skill": "",
        "reason": ""
      }
    ]
  },
  "summary_rewriter": {
    "original_summary": "",
    "optimized_summary": "",
    "reasoning": ""
  },
  "apply_recommendation": {
    "label": "Stretch Apply",
    "reasoning": ""
  },
  "confidence_rules_applied": []
}
"""


DEFAULT_ANALYSIS: dict[str, Any] = {
    "scores": {
        "overall_match_score": 0,
        "ats_match_score": 0,
        "technical_match_score": 0,
        "experience_match_score": 0,
        "education_match_score": 0,
    },
    "missing_keywords": {
        "present_in_profile": [],
        "missing_from_profile": [],
        "mentioned_in_projects_but_not_cv": [],
        "mentioned_in_skills_but_not_summary": [],
    },
    "project_prioritization": [],
    "skill_prioritization": {
        "skills_to_move_higher": [],
        "skills_to_remove_from_focus": [],
        "skills_to_emphasize": [],
    },
    "summary_rewriter": {
        "original_summary": "",
        "optimized_summary": "",
        "reasoning": "",
    },
    "apply_recommendation": {
        "label": "Stretch Apply",
        "reasoning": "",
    },
    "confidence_rules_applied": [
        "Never invent experience.",
        "Never add technologies not present in the candidate profile or current CV.",
        "Never claim professional experience for academic or personal projects.",
        "Always explain recommendations.",
    ],
}


def build_profile_cv_text(profile: dict[str, Any]) -> str:
    personal = profile.get("personal_information", {})
    additional = profile.get("additional_information", {})
    sections: list[str] = []

    if personal.get("name"):
        sections.append(f"Name: {personal['name']}")
    if additional.get("summary"):
        sections.append(f"Summary: {additional['summary']}")

    education_lines = []
    for item in profile.get("education", []):
        if not isinstance(item, dict):
            continue
        parts = [
            item.get("degree"),
            item.get("university"),
            item.get("campus"),
            item.get("graduation_year"),
        ]
        education_lines.append(" | ".join(str(part) for part in parts if part))
    if education_lines:
        sections.append("Education:\n" + "\n".join(f"- {line}" for line in education_lines))

    skill_lines = []
    for category, values in profile.get("skills", {}).items():
        if values:
            skill_lines.append(f"- {category}: {', '.join(str(value) for value in values)}")
    if skill_lines:
        sections.append("Skills:\n" + "\n".join(skill_lines))

    experience_lines = []
    for item in profile.get("experience", []):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or "Experience"
        company = f" at {item['company']}" if item.get("company") else ""
        achievements = "\n".join(f"  - {achievement}" for achievement in item.get("achievements", []))
        experience_lines.append(f"- {title}{company}\n{achievements}".strip())
    if experience_lines:
        sections.append("Experience:\n" + "\n".join(experience_lines))

    project_lines = []
    for item in profile.get("projects", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "Project"
        technologies = ", ".join(str(value) for value in item.get("technologies", []))
        description = item.get("description") or ""
        highlights = "\n".join(f"  - {highlight}" for highlight in item.get("highlights", []))
        project_lines.append(f"- {name} ({technologies})\n  {description}\n{highlights}".strip())
    if project_lines:
        sections.append("Projects:\n" + "\n".join(project_lines))

    return "\n\n".join(sections)


def generate_resume_intelligence(
    profile: dict[str, Any],
    cv_text: str,
    job_description: str,
    model: str | None = None,
    temperature: float = 0.1,
    chat_client: ChatClient | None = None,
) -> dict[str, Any]:
    selected_model = model or SETTINGS.default_model or DEFAULT_MODEL
    client = chat_client or get_default_chat_client(SETTINGS)
    user_prompt = f"""Candidate profile:
{profile_to_prompt_text(profile)}

Current CV text:
{cv_text}

Job description:
{job_description}

Analyze the resume intelligently:
1. Score overall, ATS, technical, experience, and education match from 0 to 100.
2. Extract important job keywords and categorize them into:
   - present in profile
   - missing from profile
   - mentioned in projects but not CV
   - mentioned in skills but not summary
3. Rank every project by relevance for this job.
4. Recommend skills to move higher, remove from focus, and emphasize.
5. Rewrite the summary truthfully.
6. Decide whether this is Strong Apply, Apply, Stretch Apply, or Low Probability.
7. Explain every recommendation.

Do not add technologies, experience, certifications, GPA, or professional claims that are not present in the supplied profile or CV text.
"""

    logger.info("Generating resume intelligence with model=%s", selected_model)
    content = client.create_json_chat(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        model=selected_model,
        temperature=temperature,
    )
    return normalize_resume_intelligence(_parse_json_object(content))


def normalize_resume_intelligence(data: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(DEFAULT_ANALYSIS)
    for key in result:
        if key in data:
            result[key] = data[key]

    if not isinstance(result["scores"], dict):
        result["scores"] = deepcopy(DEFAULT_ANALYSIS["scores"])
    for key in DEFAULT_ANALYSIS["scores"]:
        result["scores"][key] = _bounded_percent(result["scores"].get(key, 0))

    if not isinstance(result["missing_keywords"], dict):
        result["missing_keywords"] = deepcopy(DEFAULT_ANALYSIS["missing_keywords"])
    for key in DEFAULT_ANALYSIS["missing_keywords"]:
        result["missing_keywords"][key] = _string_list(result["missing_keywords"].get(key))

    projects = []
    for item in _as_list(result.get("project_prioritization")):
        if not isinstance(item, dict):
            continue
        project = {
            "project_name": str(item.get("project_name") or item.get("name") or "").strip(),
            "relevance_score": _bounded_percent(item.get("relevance_score", 0)),
            "why_it_matters": str(item.get("why_it_matters", "") or "").strip(),
            "recommended_bullet_points": _string_list(item.get("recommended_bullet_points")),
        }
        if project["project_name"]:
            projects.append(project)
    result["project_prioritization"] = sorted(projects, key=lambda item: item["relevance_score"], reverse=True)

    if not isinstance(result["skill_prioritization"], dict):
        result["skill_prioritization"] = deepcopy(DEFAULT_ANALYSIS["skill_prioritization"])
    for key in DEFAULT_ANALYSIS["skill_prioritization"]:
        result["skill_prioritization"][key] = _reason_items(result["skill_prioritization"].get(key))

    if not isinstance(result["summary_rewriter"], dict):
        result["summary_rewriter"] = deepcopy(DEFAULT_ANALYSIS["summary_rewriter"])
    for key in DEFAULT_ANALYSIS["summary_rewriter"]:
        result["summary_rewriter"][key] = str(result["summary_rewriter"].get(key, "") or "").strip()

    if not isinstance(result["apply_recommendation"], dict):
        result["apply_recommendation"] = deepcopy(DEFAULT_ANALYSIS["apply_recommendation"])
    label = str(result["apply_recommendation"].get("label") or "Stretch Apply").strip()
    if label not in APPLY_LABELS:
        label = "Stretch Apply"
    result["apply_recommendation"]["label"] = label
    result["apply_recommendation"]["reasoning"] = str(
        result["apply_recommendation"].get("reasoning", "") or ""
    ).strip()

    result["confidence_rules_applied"] = _string_list(result.get("confidence_rules_applied"))
    if not result["confidence_rules_applied"]:
        result["confidence_rules_applied"] = list(DEFAULT_ANALYSIS["confidence_rules_applied"])

    return result


def analysis_to_markdown(analysis: dict[str, Any]) -> str:
    analysis = normalize_resume_intelligence(analysis)
    scores = analysis["scores"]
    recommendation = analysis["apply_recommendation"]

    lines = [
        "# Resume Intelligence Analysis",
        "",
        "## Match Scores",
        f"- Overall Match Score: {scores['overall_match_score']}/100",
        f"- ATS Match Score: {scores['ats_match_score']}/100",
        f"- Technical Match Score: {scores['technical_match_score']}/100",
        f"- Experience Match Score: {scores['experience_match_score']}/100",
        f"- Education Match Score: {scores['education_match_score']}/100",
        "",
        "## Apply Recommendation",
        f"**{recommendation['label']}**",
        "",
        recommendation["reasoning"] or "No reasoning provided.",
        "",
        "## Missing Keywords",
    ]

    keyword_labels = {
        "present_in_profile": "Present in profile",
        "missing_from_profile": "Missing from profile",
        "mentioned_in_projects_but_not_cv": "Mentioned in projects but not CV",
        "mentioned_in_skills_but_not_summary": "Mentioned in skills but not summary",
    }
    for key, label in keyword_labels.items():
        lines.extend([f"### {label}", *_markdown_bullets(analysis["missing_keywords"].get(key, [])), ""])

    lines.append("## Project Prioritization")
    for project in analysis["project_prioritization"]:
        lines.extend(
            [
                f"### {project['project_name']} ({project['relevance_score']}/100)",
                project["why_it_matters"] or "No rationale provided.",
                "",
                "Recommended bullet points:",
                *_markdown_bullets(project["recommended_bullet_points"]),
                "",
            ]
        )

    lines.append("## Skill Prioritization")
    skill_labels = {
        "skills_to_move_higher": "Skills to move higher",
        "skills_to_remove_from_focus": "Skills to remove from focus",
        "skills_to_emphasize": "Skills to emphasize",
    }
    for key, label in skill_labels.items():
        lines.append(f"### {label}")
        items = analysis["skill_prioritization"].get(key, [])
        if items:
            for item in items:
                lines.append(f"- {item['skill']}: {item['reason']}")
        else:
            lines.append("- None.")
        lines.append("")

    summary = analysis["summary_rewriter"]
    lines.extend(
        [
            "## Summary Rewriter",
            "### Original summary",
            summary["original_summary"] or "No original summary provided.",
            "",
            "### Optimized summary",
            summary["optimized_summary"] or "No optimized summary generated.",
            "",
            "### Reasoning",
            summary["reasoning"] or "No reasoning provided.",
            "",
            "## Confidence Rules Applied",
            *_markdown_bullets(analysis["confidence_rules_applied"]),
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def markdown_to_pdf_bytes(markdown_text: str, title: str = "Resume Intelligence Analysis") -> bytes:
    lines = _markdown_to_plain_lines(markdown_text)
    pages: list[list[str]] = [[]]
    for line in lines:
        wrapped = textwrap.wrap(line, width=92) or [""]
        for wrapped_line in wrapped:
            if len(pages[-1]) >= 48:
                pages.append([])
            pages[-1].append(wrapped_line)

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        None,  # type: ignore[list-item]
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_object_ids: list[int] = []
    content_object_ids: list[int] = []

    for page_lines in pages:
        content = _pdf_page_content(page_lines)
        content_id = len(objects) + 1
        content_object_ids.append(content_id)
        objects.append(
            b"<< /Length "
            + str(len(content)).encode("ascii")
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )
        page_id = len(objects) + 1
        page_object_ids.append(page_id)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode(
                "ascii"
            )
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("ascii")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "latin-1", "replace"
        )
    )
    return bytes(pdf)


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


def _reason_items(value: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            skill = str(item.get("skill", "") or "").strip()
            reason = str(item.get("reason", "") or "").strip()
        else:
            skill = str(item).strip()
            reason = ""
        if skill:
            items.append({"skill": skill, "reason": reason})
    return items


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _bounded_percent(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(0, min(100, number))


def _markdown_bullets(items: list[str]) -> list[str]:
    if not items:
        return ["- None."]
    return [f"- {item}" for item in items]


def _markdown_to_plain_lines(markdown_text: str) -> list[str]:
    plain_lines = []
    for line in markdown_text.splitlines():
        line = line.replace("**", "")
        if line.startswith("# "):
            line = line[2:].upper()
        elif line.startswith("## "):
            line = line[3:].upper()
        elif line.startswith("### "):
            line = line[4:]
        plain_lines.append(line)
    return plain_lines


def _pdf_page_content(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "14 TL", "50 760 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("T*")
        commands.append(f"({_pdf_escape(line)}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", "replace")


def _pdf_escape(text: str) -> str:
    sanitized = text.encode("latin-1", "replace").decode("latin-1")
    return sanitized.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
