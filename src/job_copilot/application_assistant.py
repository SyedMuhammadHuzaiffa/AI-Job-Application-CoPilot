from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .config import EXPORT_DIR, TRACKER_DB_PATH
from .latex import write_exports
from .llm import generate_tailoring
from .llm_client import ChatClient
from .logging_config import get_logger
from .profile import enhance_profile
from .tracker import save_application, update_application_status


logger = get_logger(__name__)

ASSISTANT_STATUS_LABELS = [
    "Draft",
    "Ready to Apply",
    "Applied",
    "Awaiting Response",
    "Interviewing",
    "Rejected",
    "Offer",
]

STATUS_TO_TRACKER = {
    "Draft": "Draft",
    "Ready to Apply": "Ready to Apply",
    "Applied": "Applied",
    "Awaiting Response": "Awaiting response",
    "Interviewing": "Interviewing",
    "Rejected": "Rejected",
    "Offer": "Offer",
}

SAFETY_CHECKLIST = [
    "I reviewed every generated claim against my profile.",
    "I confirmed no invented experience, GPA, authorization, passport status, or certifications were added.",
    "I will submit manually and will not bypass CAPTCHA or job-site rules.",
    "I understand this assistant must stop before final submission.",
]


@dataclass(frozen=True)
class ApplicationPacket:
    job_title: str
    company: str
    apply_url: str
    location: str
    cv_tex_path: str
    cover_letter_tex_path: str
    answers: list[dict[str, str]]
    linkedin_outreach: dict[str, str]
    checklist: list[str]
    copy_fields: dict[str, str]
    result: dict[str, Any]
    tracker_id: int | None = None
    discovered_job_id: int | None = None
    status: str = "Draft"

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_title": self.job_title,
            "company": self.company,
            "apply_url": self.apply_url,
            "location": self.location,
            "cv_tex_path": self.cv_tex_path,
            "cover_letter_tex_path": self.cover_letter_tex_path,
            "answers": self.answers,
            "linkedin_outreach": self.linkedin_outreach,
            "checklist": self.checklist,
            "copy_fields": self.copy_fields,
            "result": self.result,
            "tracker_id": self.tracker_id,
            "discovered_job_id": self.discovered_job_id,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApplicationPacket":
        return cls(
            job_title=str(data.get("job_title") or ""),
            company=str(data.get("company") or ""),
            apply_url=str(data.get("apply_url") or ""),
            location=str(data.get("location") or ""),
            cv_tex_path=str(data.get("cv_tex_path") or ""),
            cover_letter_tex_path=str(data.get("cover_letter_tex_path") or ""),
            answers=[dict(item) for item in data.get("answers", []) if isinstance(item, dict)],
            linkedin_outreach=dict(data.get("linkedin_outreach") or {}),
            checklist=[str(item) for item in data.get("checklist", [])],
            copy_fields={str(key): str(value) for key, value in dict(data.get("copy_fields") or {}).items()},
            result=dict(data.get("result") or {}),
            tracker_id=data.get("tracker_id"),
            discovered_job_id=data.get("discovered_job_id"),
            status=str(data.get("status") or "Draft"),
        )


def build_application_packet(
    profile: dict[str, Any],
    saved_job: dict[str, Any],
    model: str | None = None,
    export_dir: Path = EXPORT_DIR,
    tracker_db_path: Path = TRACKER_DB_PATH,
    chat_client: ChatClient | None = None,
    save_draft: bool = True,
) -> ApplicationPacket:
    profile = enhance_profile(profile)
    job_description = saved_job_to_prompt(saved_job)
    result = generate_tailoring(profile, job_description, model=model, chat_client=chat_client)
    result.setdefault("job", {})
    result["job"]["title"] = result["job"].get("title") or saved_job.get("role") or saved_job.get("job_title") or ""
    result["job"]["company"] = result["job"].get("company") or saved_job.get("company") or ""
    result["job"]["location"] = result["job"].get("location") or saved_job.get("location") or ""
    result["job"]["apply_link"] = result["job"].get("apply_link") or saved_job.get("apply_url") or saved_job.get("apply_link") or ""

    job_meta = {
        "title": str(result["job"].get("title") or ""),
        "company": str(result["job"].get("company") or ""),
        "location": str(result["job"].get("location") or ""),
        "apply_link": str(result["job"].get("apply_link") or ""),
    }
    paths = write_exports(profile, result, job_meta, export_dir)
    checklist = _dedupe([*result.get("approval_checklist", []), *SAFETY_CHECKLIST])
    copy_fields = build_copy_fields(profile, result)
    answers = [
        {
            "question": str(item.get("question") or ""),
            "answer": str(item.get("answer") or ""),
        }
        for item in result.get("application_answers", [])
        if isinstance(item, dict)
    ]

    tracker_id = None
    if save_draft:
        tracker_id = save_application(
            job_title=job_meta["title"],
            company=job_meta["company"],
            location=job_meta["location"],
            apply_link=job_meta["apply_link"],
            status="Draft",
            application_date=date.today().isoformat(),
            fit_score=int(result.get("fit", {}).get("score", 0)),
            ats_match_percent=int(result.get("fit", {}).get("ats_match_percent", 0)),
            notes="Generated by Guided Application Assistant. Human review required before applying.",
            cv_tex_path=str(paths["cv"]),
            cover_letter_tex_path=str(paths["cover_letter"]),
            db_path=tracker_db_path,
        )

    logger.info("Built application packet for company=%s role=%s", job_meta["company"], job_meta["title"])
    return ApplicationPacket(
        job_title=job_meta["title"],
        company=job_meta["company"],
        apply_url=job_meta["apply_link"],
        location=job_meta["location"],
        cv_tex_path=str(paths["cv"]),
        cover_letter_tex_path=str(paths["cover_letter"]),
        answers=answers,
        linkedin_outreach=dict(result.get("linkedin_outreach") or {}),
        checklist=checklist,
        copy_fields=copy_fields,
        result=result,
        tracker_id=tracker_id,
        discovered_job_id=saved_job.get("id"),
    )


def saved_job_to_prompt(job: dict[str, Any]) -> str:
    parts = [
        f"Job title: {job.get('role') or job.get('job_title') or ''}",
        f"Company: {job.get('company') or ''}",
        f"Location: {job.get('location') or ''}",
        f"Apply URL: {job.get('apply_url') or job.get('apply_link') or ''}",
        f"Source: {job.get('source') or ''}",
        f"Description: {job.get('description') or ''}",
        f"Missing skills from prior match: {', '.join(job.get('missing_skills') or [])}",
        f"Missing keywords from prior match: {', '.join(job.get('missing_keywords') or [])}",
    ]
    return "\n".join(part for part in parts if part.strip())


def build_copy_fields(profile: dict[str, Any], result: dict[str, Any] | None = None) -> dict[str, str]:
    profile = enhance_profile(profile)
    result = result or {}
    personal = profile.get("personal_information", {})
    additional = profile.get("additional_information", {})
    name_parts = str(personal.get("name") or "").split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    skills = profile.get("skills", {})
    projects = [project for project in profile.get("projects", []) if isinstance(project, dict)]
    experience = [item for item in profile.get("experience", []) if isinstance(item, dict)]

    return {
        "First name": _known(first_name),
        "Last name": _known(last_name),
        "Email": _known(personal.get("email")),
        "Phone": _known(personal.get("phone")),
        "LinkedIn": _known(personal.get("linkedin")),
        "GitHub": _known(personal.get("github")),
        "Location": _known(personal.get("location")),
        "Availability": _known(additional.get("availability")),
        "Relocation answer": _relocation_answer(profile),
        "English proficiency": _known(additional.get("english_proficiency") or profile.get("english_proficiency")),
        "Programming tools answer": _tools_answer(skills),
        "Project answer": _project_answer(projects),
        "AI tools answer": _ai_tools_answer(skills),
        "Track record answer": _track_record_answer(experience, projects),
        "LinkedIn outreach message": _known((result.get("linkedin_outreach") or {}).get("recruiter_message")),
    }


def apply_packet_status(
    packet: ApplicationPacket,
    status_label: str,
    approved: bool = False,
    tracker_db_path: Path = TRACKER_DB_PATH,
) -> ApplicationPacket:
    tracker_status = STATUS_TO_TRACKER.get(status_label)
    if not tracker_status:
        raise ValueError(f"Unsupported status: {status_label}")
    if tracker_status == "Applied" and not approved:
        raise ValueError("User approval is required before marking an application Applied.")
    if packet.tracker_id is None:
        raise ValueError("Application packet has not been saved to the tracker yet.")
    update_application_status(packet.tracker_id, tracker_status, tracker_db_path)
    data = packet.as_dict()
    data["status"] = status_label
    return ApplicationPacket.from_dict(data)


def _known(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "Not specified in profile."


def _relocation_answer(profile: dict[str, Any]) -> str:
    preferences = profile.get("career_preferences", {})
    willingness = preferences.get("relocation_willingness")
    locations = preferences.get("preferred_locations") or []
    if willingness:
        return str(willingness)
    if locations:
        return f"Preferred locations: {', '.join(str(item) for item in locations)}."
    return "Not specified in profile."


def _tools_answer(skills: dict[str, Any]) -> str:
    categories = ["languages", "frontend", "backend", "databases", "cloud", "devops", "testing", "tools"]
    tools: list[str] = []
    for category in categories:
        tools.extend(str(item) for item in skills.get(category, []) if str(item).strip())
    return ", ".join(_dedupe(tools)) if tools else "Not specified in profile."


def _project_answer(projects: list[dict[str, Any]]) -> str:
    if not projects:
        return "Not specified in profile."
    project = projects[0]
    parts = [
        str(project.get("name") or "Project"),
        str(project.get("description") or "").strip(),
    ]
    technologies = project.get("technologies") or []
    if technologies:
        parts.append(f"Technologies: {', '.join(str(item) for item in technologies)}.")
    highlights = project.get("highlights") or []
    if highlights:
        parts.append(f"Highlight: {str(highlights[0])}")
    return " ".join(part for part in parts if part)


def _ai_tools_answer(skills: dict[str, Any]) -> str:
    values = [str(item) for item in skills.get("ai_tools", []) if str(item).strip()]
    return ", ".join(values) if values else "Not specified in profile."


def _track_record_answer(experience: list[dict[str, Any]], projects: list[dict[str, Any]]) -> str:
    statements: list[str] = []
    for item in experience[:2]:
        title = item.get("title") or "Experience"
        achievements = item.get("achievements") or []
        if achievements:
            statements.append(f"{title}: {achievements[0]}")
    for project in projects[:2]:
        highlights = project.get("highlights") or []
        if highlights:
            statements.append(f"{project.get('name') or 'Project'}: {highlights[0]}")
    return " ".join(statements) if statements else "Not specified in profile."


def _dedupe(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            output.append(text)
    return output
