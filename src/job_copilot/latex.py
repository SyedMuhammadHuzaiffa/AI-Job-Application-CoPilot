import re
import textwrap
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


def render_cv_pdf_bytes(profile: dict[str, Any], result: dict[str, Any]) -> bytes:
    tex = render_cv_tex(profile, result)
    name = _personal_information(profile).get("name") or "Tailored CV"
    return text_to_pdf_bytes(_latex_to_plain_text(tex), title=f"{name} - Tailored CV")


def render_cover_letter_pdf_bytes(
    profile: dict[str, Any],
    result: dict[str, Any],
    job_meta: dict[str, str],
) -> bytes:
    tex = render_cover_letter_tex(profile, result, job_meta)
    company = job_meta.get("company") or result.get("job", {}).get("company") or "Company"
    return text_to_pdf_bytes(_latex_to_plain_text(tex), title=f"Cover Letter - {company}")


def text_to_pdf_bytes(text: str, title: str = "Document") -> bytes:
    lines = [title, ""] + text.splitlines()
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
    page_ids: list[int] = []
    for page_lines in pages:
        content = _pdf_page_content(page_lines)
        content_id = len(objects) + 1
        objects.append(
            b"<< /Length "
            + str(len(content)).encode("ascii")
            + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )
        page_id = len(objects) + 1
        page_ids.append(page_id)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode(
                "ascii"
            )
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

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


def _latex_to_plain_text(tex: str) -> str:
    text = tex
    text = re.sub(r"%.*", "", text)
    replacements = {
        r"\&": "&",
        r"\%": "%",
        r"\$": "$",
        r"\#": "#",
        r"\_": "_",
        r"\{": "{",
        r"\}": "}",
        r"\textbackslash{}": "\\",
        r"\textasciitilde{}": "~",
        r"\textasciicircum{}": "^",
        r"\mid": "|",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"\\(?:documentclass|usepackage)(?:\[[^\]]*\])?\{[^}]*\}", "", text)
    text = re.sub(r"\\(?:begin|end)\{[^}]*\}", "\n", text)
    text = re.sub(r"\\(?:section|subsection|textbf)\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\item\s*", "- ", text)
    text = re.sub(r"\\\\", "\n", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", "", text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


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
