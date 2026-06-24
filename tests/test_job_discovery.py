import json
from pathlib import Path

from job_copilot.job_discovery import (
    SearchFilters,
    build_search_links,
    export_jobs_csv,
    export_jobs_json,
    job_dashboard_stats,
    list_discovered_jobs,
    match_job_to_profile,
    rank_job,
    search_jobs,
    set_discovered_job_status,
    upsert_job,
)


def _profile() -> dict:
    return {
        "personal_information": {"name": "Aisha Khan"},
        "education": [{"degree": "BS Software Engineering", "university": "Example University"}],
        "skills": {"languages": ["Python"], "backend": ["FastAPI", "REST APIs"], "databases": ["PostgreSQL"]},
        "projects": [
            {
                "name": "API Tracker",
                "description": "REST API tracker",
                "technologies": ["Python", "FastAPI", "PostgreSQL"],
                "highlights": ["Built tested REST APIs."],
            }
        ],
        "experience": [],
    }


def test_job_match_rank_upsert_export_and_tracker_integration(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    job = {
        "company": "Acme",
        "role": "Graduate Backend Software Engineer",
        "location": "Dubai, UAE",
        "country": "UAE",
        "source": "Greenhouse",
        "source_priority": 1,
        "apply_url": "https://example.com/acme",
        "description": "Python FastAPI PostgreSQL REST API graduate role with visa sponsorship.",
        "graduate": True,
        "junior": True,
        "sponsorship_available": True,
    }

    match = match_job_to_profile(job, _profile())
    assert match["overall_match_score"] > 0
    assert "Python" not in match["missing_skills"]
    job.update(match)
    job["rank_score"] = rank_job(job, SearchFilters())
    fingerprint = upsert_job(job, db_path)
    assert fingerprint

    jobs = list_discovered_jobs(db_path)
    assert jobs[0]["company"] == "Acme"
    assert export_jobs_csv(jobs).startswith(b"company,role")
    assert json.loads(export_jobs_json(jobs))[0]["company"] == "Acme"
    assert job_dashboard_stats(db_path)["total_jobs_found"] == 1

    tracker_id = set_discovered_job_status(jobs[0]["id"], "Applied", db_path)
    assert tracker_id is not None


def test_search_jobs_uses_configured_safe_fetchers(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "jobs.db"
    config_path = tmp_path / "sources.json"
    config_path.write_text(
        json.dumps(
            {
                "enabled_connectors": ["RemoteOK"],
                "greenhouse_boards": [],
                "lever_companies": [],
                "company_career_pages": [],
                "platform_search_templates": [{"source": "LinkedIn Jobs", "url": "https://example.com?q={query}&l={location}"}],
            }
        ),
        encoding="utf-8",
    )

    import job_copilot.job_discovery as jd

    monkeypatch.setattr(
        jd,
        "_fetch_remoteok",
        lambda filters: [
            {
                "company": "RemoteCo",
                "role": "Junior Software Engineer",
                "location": "Remote",
                "country": "Remote",
                "source": "RemoteOK",
                "apply_url": "https://remote.example/job",
                "description": "Python REST API junior remote role.",
                "remote_available": True,
                "junior": True,
            }
        ],
    )

    result = search_jobs(SearchFilters(remote=True), _profile(), db_path, config_path)
    assert result["new_count"] == 1
    assert result["jobs"][0]["company"] == "RemoteCo"
    assert result["search_links"][0]["source"] == "LinkedIn Jobs"


def test_build_search_links_formats_query() -> None:
    links = build_search_links(
        SearchFilters(role="graduate software engineer", country="UAE", city="Dubai"),
        {"platform_search_templates": [{"source": "Test", "url": "https://example.com?q={query}&l={location}"}]},
    )
    assert "graduate+software+engineer" in links[0]["url"]
    assert "Dubai+UAE" in links[0]["url"]
