import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from job_copilot.exceptions import ValidationError
from job_copilot.tracker import list_applications, save_application


def test_tracker_saves_lists_and_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "applications.db"
    row_id = save_application(
        "Junior Software Engineer",
        "Acme",
        "Dubai, UAE",
        "https://example.com/apply",
        "Applied",
        "2026-06-25",
        82,
        77,
        "Source: LinkedIn.",
        "cv.tex",
        "cover.tex",
        db_path,
    )

    rows = list_applications(db_path)
    assert row_id == 1
    assert rows[0]["company"] == "Acme"
    assert rows[0]["notes"] == "Source: LinkedIn."
    assert rows[0]["ats_match_percent"] == 77

    with closing(sqlite3.connect(db_path)) as conn:
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(applications)").fetchall()}
    assert "idx_applications_status" in indexes
    assert "idx_applications_company" in indexes


def test_tracker_repository_validates_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        save_application(
            "",
            "Acme",
            "",
            "",
            "Applied",
            "2026-06-25",
            db_path=tmp_path / "applications.db",
        )

    with pytest.raises(ValidationError):
        save_application(
            "Engineer",
            "Acme",
            "",
            "",
            "Applied",
            "25-06-2026",
            db_path=tmp_path / "applications.db",
        )

    with pytest.raises(ValidationError):
        save_application(
            "Engineer",
            "Acme",
            "",
            "",
            "Applied",
            "2026-06-25",
            ats_match_percent=130,
            db_path=tmp_path / "applications.db",
        )
