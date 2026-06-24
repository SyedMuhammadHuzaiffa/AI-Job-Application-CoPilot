from pathlib import Path

from job_copilot.application_analytics import compute_application_analytics, load_analytics_rows
from job_copilot.job_discovery import upsert_job
from job_copilot.tracker import save_application


def test_analytics_enriches_rows_from_discovery_cache(tmp_path: Path) -> None:
    tracker_db = tmp_path / "tracker.db"
    discovery_db = tmp_path / "jobs.db"
    job = {
        "company": "DiscoverCo",
        "role": "Junior Software Engineer",
        "location": "Dubai",
        "country": "UAE",
        "source": "Greenhouse",
        "source_priority": 1,
        "apply_url": "https://example.com/discover",
        "description": "Python",
        "overall_match_score": 88,
        "ats_match_estimate": 84,
        "rank_score": 90,
        "junior": True,
    }
    upsert_job(job, discovery_db)
    save_application(
        "Junior Software Engineer",
        "DiscoverCo",
        "",
        "https://example.com/discover",
        "Applied",
        "2026-06-25",
        None,
        None,
        "",
        db_path=tracker_db,
    )

    rows = load_analytics_rows(tracker_db, discovery_db)
    assert rows[0]["source"] == "Greenhouse"
    assert rows[0]["country"] == "UAE"
    assert rows[0]["fit_score"] == 88
    assert rows[0]["ats_match_percent"] == 84

    analytics = compute_application_analytics([])
    assert analytics["metrics"]["applications_sent"] == 0
    assert "No sent applications yet" in analytics["insights"][-1]
