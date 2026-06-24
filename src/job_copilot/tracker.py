import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .config import TRACKER_DB_PATH
from .logging_config import get_logger
from .models import ApplicationCreate, ApplicationRecord, now_iso


logger = get_logger(__name__)

STATUSES = [
    "Needs Review",
    "Draft",
    "Ready to Apply",
    "Applied",
    "Awaiting response",
    "Interviewing",
    "Rejected",
    "Offer",
]

DASHBOARD_STATUSES = [
    "Applied",
    "Interviewing",
    "Rejected",
    "Offer",
    "Awaiting response",
]


class TrackerRepository:
    def __init__(self, db_path: Path = TRACKER_DB_PATH) -> None:
        self.db_path = db_path

    def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    apply_link TEXT,
                    status TEXT NOT NULL,
                    application_date TEXT NOT NULL,
                    fit_score INTEGER,
                    ats_match_percent INTEGER,
                    notes TEXT,
                    cv_tex_path TEXT,
                    cover_letter_tex_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            existing_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(applications)").fetchall()
            }
            if "ats_match_percent" not in existing_columns:
                conn.execute("ALTER TABLE applications ADD COLUMN ats_match_percent INTEGER")
            if "notes" not in existing_columns:
                conn.execute("ALTER TABLE applications ADD COLUMN notes TEXT")
            if "created_at" not in existing_columns:
                conn.execute("ALTER TABLE applications ADD COLUMN created_at TEXT")
            self._create_indexes(conn)
            conn.commit()

    def save(self, application: ApplicationCreate) -> int:
        self.init()
        application = application.validated()
        now = now_iso()
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.execute(
                """
                INSERT INTO applications (
                    job_title,
                    company,
                    location,
                    apply_link,
                    status,
                    application_date,
                    fit_score,
                    ats_match_percent,
                    notes,
                    cv_tex_path,
                    cover_letter_tex_path,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application.job_title,
                    application.company,
                    application.location,
                    application.apply_link,
                    application.status,
                    application.application_date,
                    application.fit_score,
                    application.ats_match_percent,
                    application.notes,
                    application.cv_tex_path,
                    application.cover_letter_tex_path,
                    now,
                    now,
                ),
            )
            conn.commit()
            row_id = int(cursor.lastrowid)
        logger.info("Saved application row id=%s company=%s status=%s", row_id, application.company, application.status)
        return row_id

    def list(self) -> list[ApplicationRecord]:
        self.init()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                    id,
                    job_title,
                    company,
                    location,
                    apply_link,
                    status,
                    application_date,
                    fit_score,
                    ats_match_percent,
                    notes,
                    cv_tex_path,
                    cover_letter_tex_path,
                    created_at,
                    updated_at
                FROM applications
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._record_from_row(dict(row)) for row in rows]

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_company ON applications(company)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_application_date ON applications(application_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_updated_at ON applications(updated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_ats_match ON applications(ats_match_percent)")

    def _record_from_row(self, row: dict[str, Any]) -> ApplicationRecord:
        return ApplicationRecord(
            id=int(row.get("id") or 0),
            job_title=str(row.get("job_title") or ""),
            company=str(row.get("company") or ""),
            location=str(row.get("location") or ""),
            apply_link=str(row.get("apply_link") or ""),
            status=str(row.get("status") or ""),
            application_date=str(row.get("application_date") or ""),
            fit_score=row.get("fit_score"),
            ats_match_percent=row.get("ats_match_percent"),
            notes=str(row.get("notes") or ""),
            cv_tex_path=str(row.get("cv_tex_path") or ""),
            cover_letter_tex_path=str(row.get("cover_letter_tex_path") or ""),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )


def init_db(db_path: Path = TRACKER_DB_PATH) -> None:
    TrackerRepository(db_path).init()


def save_application(
    job_title: str,
    company: str,
    location: str,
    apply_link: str,
    status: str,
    application_date: str,
    fit_score: int | None = None,
    ats_match_percent: int | None = None,
    notes: str = "",
    cv_tex_path: str = "",
    cover_letter_tex_path: str = "",
    db_path: Path = TRACKER_DB_PATH,
) -> int:
    return TrackerRepository(db_path).save(
        ApplicationCreate(
            job_title=job_title,
            company=company,
            location=location,
            apply_link=apply_link,
            status=status,
            application_date=application_date,
            fit_score=fit_score,
            ats_match_percent=ats_match_percent,
            notes=notes,
            cv_tex_path=cv_tex_path,
            cover_letter_tex_path=cover_letter_tex_path,
        )
    )


def list_applications(db_path: Path = TRACKER_DB_PATH) -> list[dict[str, Any]]:
    return [record.as_dict() for record in TrackerRepository(db_path).list()]
