import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import EXPORT_DIR, TEMPLATE_DIR


LATEX_REPLACEMENTS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return "".join(LATEX_REPLACEMENTS.get(char, char) for char in text)


def _safe_slug(*parts: str) -> str:
    raw = "-".join(part for part in parts if part).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "application"


def _personal_information(profile: dict[str, Any]) -> dict[str, Any]:
    if isinstance(profile.get("personal_information"), dict):
        return profile["personal_information"]
    return profile.get("basics", {})


def _profile_summary(profile: dict[str, Any]) -> str:
    additional = profile.get("additional_information", {})
    if isinstance(additional, dict) and additional.get("summary"):
        return str(additional["summary"])
    return str(profile.get("summary", "") or "")


def _join_contact(personal: dict[str, Any], additional: dict[str, Any] | None = None) -> str:
    additional = additional or {}
    fields = [
        personal.get("email"),
        personal.get("phone"),
        personal.get("location"),
        personal.get("linkedin"),
        personal.get("github"),
        additional.get("portfolio"),
    ]
    return " $\\mid$ ".join(latex_escape(field) for field in fields if field)


def _render_itemize(items: list[Any]) -> str:
    lines = [rf"\item {latex_escape(item)}" for item in items if str(item).strip()]
    return "\n".join(lines) if lines else r"\item Not specified."


def _render_education(profile: dict[str, Any]) -> str:
    blocks = []
    for item in profile.get("education", []):
        if not isinstance(item, dict):
            continue
        header = " -- ".join(
            latex_escape(value)
            for value in [
                item.get("degree"),
                item.get("university") or item.get("school"),
                item.get("campus"),
                item.get("graduation_year") or item.get("dates"),
            ]
            if value
        )
        details = _render_itemize(item.get("relevant_coursework") or item.get("details", []))
        blocks.append(rf"\textbf{{{header}}}" + "\n" + rf"\begin{{itemize}}{details}\end{{itemize}}")
    return "\n\n".join(blocks) if blocks else "Not specified."


def _render_skills(profile: dict[str, Any], highlighted: list[str]) -> str:
    profile_skills = profile.get("skills", {})
    lines = []

    if highlighted:
        lines.append(rf"\textbf{{Relevant to role:}} {latex_escape(', '.join(highlighted))}\\")

    if isinstance(profile_skills, dict):
        for category, values in profile_skills.items():
            if values:
                lines.append(rf"\textbf{{{latex_escape(category.title())}:}} {latex_escape(', '.join(values))}\\")
    elif isinstance(profile_skills, list):
        lines.append(latex_escape(", ".join(profile_skills)))

    return "\n".join(lines) if lines else "Not specified."


def _render_projects(profile: dict[str, Any]) -> str:
    blocks = []
    for project in profile.get("projects", []):
        if not isinstance(project, dict):
            continue
        name = latex_escape(project.get("name", "Project"))
        tech = latex_escape(", ".join(project.get("technologies", [])))
        link = latex_escape(project.get("github_link") or project.get("link", ""))
        header_parts = [rf"\textbf{{{name}}}"]
        if tech:
            header_parts.append(tech)
        if link:
            header_parts.append(link)
        project_lines = []
        if project.get("description"):
            project_lines.append(project["description"])
        project_lines.extend(project.get("highlights") or project.get("bullets", []))
        bullets = _render_itemize(project_lines)
        blocks.append(" -- ".join(header_parts) + "\n" + rf"\begin{{itemize}}{bullets}\end{{itemize}}")
    return "\n\n".join(blocks) if blocks else "Not specified."


def _render_tailored_bullets(result: dict[str, Any]) -> str:
    bullets = []
    for item in result.get("cv", {}).get("bullets", []):
        if not isinstance(item, dict):
            continue
        source = latex_escape(item.get("source", "Profile"))
        tailored = latex_escape(item.get("tailored", ""))
        if tailored:
            bullets.append(rf"\item \textbf{{{source}:}} {tailored}")
    return "\n".join(bullets) if bullets else r"\item Add tailored bullets after human review."


def render_cv_tex(profile: dict[str, Any], result: dict[str, Any], template_path: Path | None = None) -> str:
    template = (template_path or TEMPLATE_DIR / "cv_template.tex").read_text(encoding="utf-8")
    personal = _personal_information(profile)
    additional = profile.get("additional_information", {})
    cv = result.get("cv", {})

    replacements = {
        "{{NAME}}": latex_escape(personal.get("name", "")),
        "{{CONTACT}}": _join_contact(personal, additional if isinstance(additional, dict) else {}),
        "{{SUMMARY}}": latex_escape(cv.get("summary") or _profile_summary(profile)),
        "{{SKILLS}}": _render_skills(profile, cv.get("skills_to_highlight", [])),
        "{{EDUCATION}}": _render_education(profile),
        "{{TAILORED_BULLETS}}": _render_tailored_bullets(result),
        "{{PROJECTS}}": _render_projects(profile),
    }

    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def render_cover_letter_tex(
    profile: dict[str, Any],
    result: dict[str, Any],
    job_meta: dict[str, str],
    template_path: Path | None = None,
) -> str:
    template = (template_path or TEMPLATE_DIR / "cover_letter_template.tex").read_text(encoding="utf-8")
    personal = _personal_information(profile)
    letter = result.get("cover_letter", {})
    paragraphs = letter.get("body", [])
    body = "\n\n".join(latex_escape(paragraph) for paragraph in paragraphs if str(paragraph).strip())

    replacements = {
        "{{NAME}}": latex_escape(personal.get("name", "")),
        "{{EMAIL}}": latex_escape(personal.get("email", "")),
        "{{PHONE}}": latex_escape(personal.get("phone", "")),
        "{{LOCATION}}": latex_escape(personal.get("location", "")),
        "{{TODAY}}": latex_escape(date.today().strftime("%B %d, %Y")),
        "{{RECIPIENT}}": latex_escape(letter.get("recipient") or "Hiring Manager"),
        "{{COMPANY}}": latex_escape(job_meta.get("company") or result.get("job", {}).get("company") or "the company"),
        "{{JOB_TITLE}}": latex_escape(job_meta.get("title") or result.get("job", {}).get("title") or "the role"),
        "{{BODY}}": body or "Please add a reviewed cover letter body.",
    }

    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def write_exports(
    profile: dict[str, Any],
    result: dict[str, Any],
    job_meta: dict[str, str],
    export_dir: Path = EXPORT_DIR,
) -> dict[str, Path]:
    export_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    slug = _safe_slug(job_meta.get("company", ""), job_meta.get("title", ""), timestamp)

    cv_path = export_dir / f"{slug}-cv.tex"
    cover_path = export_dir / f"{slug}-cover-letter.tex"

    cv_path.write_text(render_cv_tex(profile, result), encoding="utf-8")
    cover_path.write_text(render_cover_letter_tex(profile, result, job_meta), encoding="utf-8")

    return {"cv": cv_path, "cover_letter": cover_path}
