import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import requests

import job_copilot.job_discovery as jd
from job_copilot.job_discovery import (
    SearchFilters,
    ensure_source_config,
    list_alerts,
    list_discovered_jobs,
    list_saved_searches,
    save_search,
    set_discovered_job_status,
    update_alerts_for_saved_searches,
    upsert_job,
)


class FakeResponse:
    def __init__(self, payload: Any = None, text: str = "", fail: bool = False) -> None:
        self.payload = payload
        self.text = text
        self.fail = fail

    def json(self) -> Any:
        return self.payload

    def raise_for_status(self) -> None:
        if self.fail:
            raise requests.HTTPError("boom")


def test_source_config_defaults_and_saved_search_alerts(tmp_path: Path) -> None:
    config_path = tmp_path / "sources.json"
    config = ensure_source_config(config_path)
    assert config_path.exists()
    assert "RemoteOK" in config["enabled_connectors"]

    db_path = tmp_path / "jobs.db"
    search_id = save_search("", SearchFilters(role="software engineer"), db_path)
    assert list_saved_searches(db_path)[0]["id"] == search_id

    job = {
        "company": "AlertCo",
        "role": "Junior Software Engineer",
        "location": "Karachi, Pakistan",
        "country": "Pakistan",
        "source": "Lever",
        "source_priority": 2,
        "apply_url": "https://example.com/alert",
        "description": "junior software engineer python",
        "overall_match_score": 70,
        "ats_match_estimate": 65,
        "rank_score": 80,
        "junior": True,
    }
    fingerprint = upsert_job(job, db_path)
    update_alerts_for_saved_searches([fingerprint], db_path)
    alerts = list_alerts(db_path)
    assert alerts
    assert "AlertCo" in alerts[0]["message"]


def test_list_filters_status_errors_and_duplicate_upsert(tmp_path: Path) -> None:
    db_path = tmp_path / "jobs.db"
    job = {
        "company": "FilterCo",
        "role": "Junior Backend Engineer",
        "location": "Remote",
        "country": "Remote",
        "source": "RemoteOK",
        "source_priority": 4,
        "apply_url": "https://example.com/filter",
        "description": "remote junior backend role",
        "overall_match_score": 66,
        "ats_match_estimate": 60,
        "rank_score": 72,
        "remote_available": True,
        "junior": True,
    }
    first = upsert_job(dict(job), db_path)
    second_job = dict(job)
    second_job["source"] = "Lever"
    second_job["source_priority"] = 2
    second = upsert_job(second_job, db_path)
    assert first == second

    filtered = list_discovered_jobs(
        db_path,
        filters=SearchFilters(role="backend", remote=True, junior=True, graduate=False),
        limit=5,
    )
    assert len(filtered) == 1
    assert "Lever" in filtered[0]["source"]

    assert set_discovered_job_status(filtered[0]["id"], "Saved", db_path, also_save_tracker=False) is None
    with pytest.raises(ValueError):
        set_discovered_job_status(filtered[0]["id"], "Bad", db_path)
    with pytest.raises(ValueError):
        set_discovered_job_status(9999, "Applied", db_path)


def test_fetch_adapters_and_request_retry(monkeypatch) -> None:
    monkeypatch.setattr(
        jd,
        "_request_json",
        lambda url: [
            {},
            {
                "company": "RemoteCo",
                "position": "Junior Python Engineer",
                "location": "",
                "salary": "$1",
                "url": "https://remote.example",
                "date": "2026-06-01",
                "description": "<p>Python remote</p>",
            },
        ],
    )
    assert jd._fetch_remoteok(SearchFilters())[0]["company"] == "RemoteCo"

    monkeypatch.setattr(
        jd,
        "_request_json",
        lambda url: {
            "jobs": [
                {
                    "title": "Graduate Engineer",
                    "location": {"name": "Dubai"},
                    "absolute_url": "https://greenhouse.example",
                    "updated_at": "2026-06-01",
                    "content": "<b>Python</b>",
                }
            ]
        },
    )
    greenhouse = jd._fetch_greenhouse({"greenhouse_boards": [{"board_token": "acme", "company": "Acme"}]}, SearchFilters())
    assert greenhouse[0]["source"] == "Greenhouse"

    monkeypatch.setattr(
        jd,
        "_request_json",
        lambda url: [
            {
                "text": "Junior Developer",
                "categories": {"location": "Lahore"},
                "lists": [{"text": "Build APIs"}],
                "hostedUrl": "https://lever.example",
                "createdAt": 123,
            }
        ],
    )
    lever = jd._fetch_lever({"lever_companies": [{"slug": "acme", "company": "Acme"}]}, SearchFilters())
    assert lever[0]["source"] == "Lever"


def test_company_page_and_request_get(monkeypatch) -> None:
    monkeypatch.setattr(jd, "_robots_allows", lambda url: True)
    monkeypatch.setattr(
        jd,
        "_request_text",
        lambda url: '<a href="/jobs/junior-software-engineer">Junior Software Engineer</a><a href="/about">About</a>',
    )
    jobs = jd._fetch_company_page({"company": "PageCo", "country": "Pakistan", "url": "https://page.example/careers"}, SearchFilters())
    assert jobs == [
        {
            "company": "PageCo",
            "role": "Junior Software Engineer",
            "location": "Pakistan",
            "country": "Pakistan",
            "city": "",
            "salary": "",
            "source": "Company Career Page",
            "apply_url": "https://page.example/jobs/junior-software-engineer",
            "description": "Junior Software Engineer",
            "raw_payload": {"career_page": "https://page.example/careers"},
        }
    ]

    calls = {"count": 0}

    def fake_get(url: str, headers: dict[str, str], timeout: int) -> FakeResponse:
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.Timeout("temporary")
        return FakeResponse(payload={"ok": True})

    monkeypatch.setattr(jd.requests, "get", fake_get)
    monkeypatch.setattr(jd.time, "sleep", lambda _: None)
    assert jd._request_json("https://example.com") == {"ok": True}
    assert calls["count"] == 2


def test_normalization_filter_helpers_and_decode() -> None:
    assert jd._normalize_job({"company": "", "role": "Engineer", "apply_url": ""}) is None
    normalized = jd._normalize_job(
        {
            "company": "NormCo",
            "role": "Graduate Software Engineer",
            "location": "Dubai",
            "apply_url": "https://norm.example",
            "description": "Remote hybrid visa sponsorship 0-2 years Python SQL",
        }
    )
    assert normalized is not None
    assert normalized["country"] == "UAE"
    assert normalized["remote_available"] is True
    assert normalized["hybrid_available"] is True
    assert normalized["sponsorship_available"] is True
    assert normalized["graduate"] is True
    assert normalized["junior"] is True
    assert normalized["experience_required"]

    assert jd._job_matches_filters(normalized, SearchFilters(country="UAE", remote=True, graduate=True))
    assert not jd._job_matches_filters(normalized, SearchFilters(country="Pakistan"))
    assert "python" in jd.extract_job_keywords(normalized)
    assert jd._infer_city("Karachi, Pakistan") == "Karachi"
    assert jd._strip_html("<p>Hello&nbsp;world</p>") == "Hello world"

    decoded = jd._decode_job_row(
        {
            "missing_skills": "[\"AWS\"]",
            "missing_keywords": "not-json",
            "recommended_projects": "[]",
            "remote_available": 1,
            "hybrid_available": 0,
            "sponsorship_available": 1,
            "graduate": 1,
            "junior": 0,
            "internship": 0,
        }
    )
    assert decoded["missing_skills"] == ["AWS"]
    assert decoded["missing_keywords"] == []
    assert decoded["remote_available"] is True
