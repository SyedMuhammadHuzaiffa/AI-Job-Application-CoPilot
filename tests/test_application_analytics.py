from pathlib import Path

from job_copilot.application_analytics import (
    analytics_to_dataframes,
    compute_application_analytics,
    load_analytics_rows,
)
from job_copilot.tracker import save_application


def test_application_analytics_metrics_breakdowns_and_insights(tmp_path: Path) -> None:
    tracker_db = tmp_path / "tracker.db"
    discovery_db = tmp_path / "missing_discovery.db"
    rows = [
        ("Junior Backend Engineer", "Beta", "Lahore, Pakistan", "Interviewing", 88, 86, "Source: Lever."),
        ("Graduate Software Engineer", "Gamma", "Remote", "Rejected", 65, 62, "Source: RemoteOK."),
        ("Junior Full Stack Engineer", "Delta", "Dubai, UAE", "Offer", 93, 91, "Source: Greenhouse."),
        ("Draft Role", "DraftCo", "Karachi", "Draft", 50, 50, "Source: Manual."),
    ]
    for title, company, location, status, fit, ats, notes in rows:
        save_application(
            title,
            company,
            location,
            f"https://example.com/{company.lower()}",
            status,
            "2026-06-25",
            fit,
            ats,
            notes,
            db_path=tracker_db,
        )

    analytics = compute_application_analytics(load_analytics_rows(tracker_db, discovery_db))
    metrics = analytics["metrics"]
    assert metrics["applications_sent"] == 3
    assert metrics["interviews_received"] == 2
    assert metrics["rejections"] == 1
    assert metrics["offers"] == 1
    assert metrics["response_rate"] == 100.0
    assert metrics["interview_rate"] == 66.7
    assert metrics["offer_rate"] == 33.3

    sources = {row["source"] for row in analytics["breakdowns"]["by_source"]}
    countries = {row["country"] for row in analytics["breakdowns"]["by_country"]}
    assert {"Lever", "RemoteOK", "Greenhouse"} <= sources
    assert {"Pakistan", "Remote", "UAE"} <= countries
    assert analytics["charts"]["applications_over_time"] == [{"month": "2026-06", "applications": 3}]
    assert any("ATS scores" in insight for insight in analytics["insights"])

    frames = analytics_to_dataframes(analytics)
    assert not frames["by_source"].empty
    assert not frames["applications"].empty
