from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from .exceptions import ValidationError


VALID_APPLICATION_STATUSES = {
    "Needs Review",
    "Draft",
    "Ready to Apply",
    "Applied",
    "Awaiting response",
    "Interviewing",
    "Rejected",
    "Offer",
}


@dataclass(frozen=True)
class JobMeta:
    title: str = ""
    company: str = ""
    location: str = ""
    apply_link: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ApplicationCreate:
    job_title: str
    company: str
    location: str
    apply_link: str
    status: str
    application_date: str
    fit_score: int | None = None
    ats_match_percent: int | None = None
    notes: str = ""
    cv_tex_path: str = ""
    cover_letter_tex_path: str = ""

    def validated(self) -> "ApplicationCreate":
        job_title = self.job_title.strip()
        company = self.company.strip()
        status = self.status.strip()
        if not job_title:
            raise ValidationError("Job title is required for the tracker.")
        if not company:
            raise ValidationError("Company is required for the tracker.")
        if status not in VALID_APPLICATION_STATUSES:
            raise ValidationError(f"Unsupported status: {status}")
        _validate_date(self.application_date)
        return ApplicationCreate(
            job_title=job_title,
            company=company,
            location=self.location.strip(),
            apply_link=self.apply_link.strip(),
            status=status,
            application_date=self.application_date,
            fit_score=_bounded_optional_percent(self.fit_score, "fit_score"),
            ats_match_percent=_bounded_optional_percent(self.ats_match_percent, "ats_match_percent"),
            notes=self.notes.strip(),
            cv_tex_path=self.cv_tex_path.strip(),
            cover_letter_tex_path=self.cover_letter_tex_path.strip(),
        )


@dataclass(frozen=True)
class ApplicationRecord(ApplicationCreate):
    id: int = 0
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validate_date(value: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError("Application date must use YYYY-MM-DD format.") from exc


def _bounded_optional_percent(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a number from 0 to 100.") from exc
    if number < 0 or number > 100:
        raise ValidationError(f"{field_name} must be from 0 to 100.")
    return number


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
