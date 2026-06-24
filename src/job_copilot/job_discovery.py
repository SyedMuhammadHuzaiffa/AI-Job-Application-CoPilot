import csv
import hashlib
import io
import json
import re
import sqlite3
import time
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests

from .config import JOB_DISCOVERY_DB_PATH, JOB_SOURCE_CONFIG_PATH, SETTINGS
from .logging_config import get_logger
from .profile import enhance_profile
from .tracker import save_application


logger = get_logger(__name__)
USER_AGENT = "JobApplicationCopilot/1.0 (+local personal job discovery; respects robots.txt)"
REQUEST_TIMEOUT_SECONDS = SETTINGS.request_timeout_seconds

JOB_STATUSES = ["Found", "Saved", "Applied", "Interviewing", "Rejected", "Offer"]

SOURCE_PRIORITY = {
    "Greenhouse": 1,
    "Lever": 2,
    "Wellfound": 3,
    "RemoteOK": 4,
    "Y Combinator Jobs": 5,
    "Welcome to the Jungle": 6,
    "LinkedIn Jobs": 7,
    "Indeed": 8,
    "Glassdoor": 9,
    "Rozee.pk": 10,
    "Mustakbil": 11,
    "BrightSpyre": 12,
    "CareerOkay": 13,
    "Jobee": 14,
    "HiringCafe": 15,
    "Company Career Page": 16,
    "Bayt": 17,
    "GulfTalent": 18,
    "Naukrigulf": 19,
    "Dubizzle Jobs": 20,
    "Indeed UAE": 21,
    "LinkedIn UAE": 22,
}

GRADUATE_TERMS = {"graduate", "new grad", "fresh graduate", "trainee", "associate engineer"}
JUNIOR_TERMS = {"junior", "entry level", "entry-level", "early career", "0-1", "0-2", "1 year"}
INTERNSHIP_TERMS = {"intern", "internship"}
SPONSORSHIP_TERMS = {"visa sponsorship", "sponsorship", "relocation support", "work permit"}
REMOTE_TERMS = {"remote", "work from home", "wfh", "anywhere"}
HYBRID_TERMS = {"hybrid"}

COMMON_TECH_KEYWORDS = {
    "python",
    "javascript",
    "typescript",
    "java",
    "c++",
    "c#",
    "go",
    "rust",
    "sql",
    "react",
    "next.js",
    "node.js",
    "express",
    "fastapi",
    "django",
    "flask",
    "rest api",
    "graphql",
    "postgresql",
    "mysql",
    "mongodb",
    "sqlite",
    "redis",
    "docker",
    "kubernetes",
    "linux",
    "aws",
    "azure",
    "gcp",
    "ci/cd",
    "github actions",
    "git",
    "pytest",
    "jest",
    "unit testing",
    "agile",
    "solidity",
    "blockchain",
    "ipfs",
    "openai",
    "machine learning",
    "llm",
    "streamlit",
}

ROLE_KEYWORDS = {
    "software engineer",
    "software developer",
    "backend engineer",
    "frontend engineer",
    "full stack",
    "devops",
    "site reliability",
    "data engineer",
    "ai engineer",
    "qa engineer",
}

COUNTRY_HINTS = {
    "pakistan": {"pakistan", "karachi", "lahore", "islamabad", "rawalpindi"},
    "uae": {"uae", "united arab emirates", "dubai", "abu dhabi", "sharjah"},
    "europe": {"germany", "netherlands", "sweden", "uk", "united kingdom", "ireland", "poland", "portugal", "spain"},
}


@dataclass
class SearchFilters:
    role: str = "software engineer"
    country: str = "Any"
    city: str = ""
    remote: bool = False
    hybrid: bool = False
    visa_sponsorship: bool = False
    graduate: bool = True
    junior: bool = True
    internship: bool = False
    max_experience_years: int | None = 2
    ranking_preset: str = "Huzaifa Mode"

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "country": self.country,
            "city": self.city,
            "remote": self.remote,
            "hybrid": self.hybrid,
            "visa_sponsorship": self.visa_sponsorship,
            "graduate": self.graduate,
            "junior": self.junior,
            "internship": self.internship,
            "max_experience_years": self.max_experience_years,
            "ranking_preset": self.ranking_preset,
        }


def init_job_db(db_path: Path = JOB_DISCOVERY_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discovered_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT UNIQUE NOT NULL,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                location TEXT,
                country TEXT,
                city TEXT,
                salary TEXT,
                source TEXT NOT NULL,
                source_priority INTEGER NOT NULL,
                apply_url TEXT NOT NULL,
                date_found TEXT NOT NULL,
                date_posted TEXT,
                sponsorship_available INTEGER NOT NULL DEFAULT 0,
                remote_available INTEGER NOT NULL DEFAULT 0,
                hybrid_available INTEGER NOT NULL DEFAULT 0,
                graduate INTEGER NOT NULL DEFAULT 0,
                junior INTEGER NOT NULL DEFAULT 0,
                internship INTEGER NOT NULL DEFAULT 0,
                experience_required TEXT,
                description TEXT,
                raw_payload TEXT,
                overall_match_score INTEGER,
                ats_match_estimate INTEGER,
                missing_skills TEXT,
                missing_keywords TEXT,
                recommended_projects TEXT,
                apply_recommendation TEXT,
                rank_score INTEGER,
                status TEXT NOT NULL DEFAULT 'Found',
                last_seen TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                filters_json TEXT NOT NULL,
                ranking_preset TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_run_at TEXT,
                last_new_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                saved_search_id INTEGER,
                job_fingerprint TEXT NOT NULL,
                message TEXT NOT NULL,
                seen INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_jobs_fingerprint ON discovered_jobs(fingerprint)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_jobs_status ON discovered_jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_jobs_source ON discovered_jobs(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_jobs_country ON discovered_jobs(country)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_jobs_role ON discovered_jobs(role)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_jobs_rank ON discovered_jobs(rank_score)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_jobs_date_found ON discovered_jobs(date_found)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_saved_searches_created_at ON saved_searches(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_job_alerts_seen ON job_alerts(seen)")
        conn.commit()


def default_source_config() -> dict[str, Any]:
    return {
        "enabled_connectors": ["RemoteOK", "Greenhouse", "Lever", "Company Career Page"],
        "greenhouse_boards": [],
        "lever_companies": [],
        "company_career_pages": [
            {"company": "Systems Limited", "country": "Pakistan", "url": "https://www.systemsltd.com/careers/"},
            {"company": "Arbisoft", "country": "Pakistan", "url": "https://arbisoft.com/careers/"},
            {"company": "Tkxel", "country": "Pakistan", "url": "https://tkxel.com/careers/"},
            {"company": "10Pearls", "country": "Pakistan", "url": "https://10pearls.com/careers/"},
            {"company": "Contour Software", "country": "Pakistan", "url": "https://contour-software.com/careers/"},
            {"company": "Careem", "country": "UAE", "url": "https://www.careem.com/careers/"},
            {"company": "Motive", "country": "Pakistan", "url": "https://gomotive.com/company/careers/"},
            {"company": "Dubizzle", "country": "UAE", "url": "https://www.dubizzle.com/careers/"},
            {"company": "Noon", "country": "UAE", "url": "https://www.noon.com/careers/"},
            {"company": "Talabat", "country": "UAE", "url": "https://www.talabat.com/careers"},
            {"company": "Emirates", "country": "UAE", "url": "https://www.emiratesgroupcareers.com/"},
            {"company": "Cobblestone Energy", "country": "UAE", "url": "https://www.cobblestoneenergy.com/careers/"},
        ],
        "platform_search_templates": [
            {"source": "Wellfound", "url": "https://wellfound.com/jobs?q={query}"},
            {"source": "Y Combinator Jobs", "url": "https://www.ycombinator.com/jobs?query={query}"},
            {"source": "Welcome to the Jungle", "url": "https://www.welcometothejungle.com/en/jobs?query={query}"},
            {"source": "LinkedIn Jobs", "url": "https://www.linkedin.com/jobs/search/?keywords={query}&location={location}"},
            {"source": "Indeed", "url": "https://www.indeed.com/jobs?q={query}&l={location}"},
            {"source": "Glassdoor", "url": "https://www.glassdoor.com/Job/jobs.htm?sc.keyword={query}"},
            {"source": "Rozee.pk", "url": "https://www.rozee.pk/job/jsearch/q/{query}"},
            {"source": "Mustakbil", "url": "https://www.mustakbil.com/jobs/search?keywords={query}"},
            {"source": "BrightSpyre", "url": "https://www.brightspyre.com/jobs?query={query}"},
            {"source": "CareerOkay", "url": "https://careerokay.com/jobs/?q={query}"},
            {"source": "Jobee", "url": "https://www.jobee.pk/jobs?keyword={query}"},
            {"source": "HiringCafe", "url": "https://hiring.cafe/?search={query}"},
            {"source": "Bayt", "url": "https://www.bayt.com/en/uae/jobs/{query}-jobs/"},
            {"source": "GulfTalent", "url": "https://www.gulftalent.com/jobs/search?pos_ref={query}"},
            {"source": "Naukrigulf", "url": "https://www.naukrigulf.com/{query}-jobs"},
            {"source": "Dubizzle Jobs", "url": "https://dubai.dubizzle.com/jobs/?keywords={query}"},
            {"source": "Indeed UAE", "url": "https://ae.indeed.com/jobs?q={query}&l={location}"},
            {"source": "LinkedIn UAE", "url": "https://www.linkedin.com/jobs/search/?keywords={query}&location=United%20Arab%20Emirates"},
        ],
    }


def ensure_source_config(path: Path = JOB_SOURCE_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(default_source_config(), indent=2) + "\n", encoding="utf-8")
    data = json.loads(path.read_text(encoding="utf-8"))
    default = default_source_config()
    for key, value in default.items():
        data.setdefault(key, value)
    return data


def search_jobs(
    filters: SearchFilters,
    profile: dict[str, Any],
    db_path: Path = JOB_DISCOVERY_DB_PATH,
    config_path: Path = JOB_SOURCE_CONFIG_PATH,
) -> dict[str, Any]:
    init_job_db(db_path)
    config = ensure_source_config(config_path)
    profile = enhance_profile(profile)
    failures: list[str] = []
    fetched_jobs: list[dict[str, Any]] = []

    connectors = config.get("enabled_connectors", [])
    if "RemoteOK" in connectors:
        fetched_jobs.extend(_safe_fetch(lambda: _fetch_remoteok(filters), "RemoteOK", failures))
    if "Greenhouse" in connectors:
        fetched_jobs.extend(_safe_fetch(lambda: _fetch_greenhouse(config, filters), "Greenhouse", failures))
    if "Lever" in connectors:
        fetched_jobs.extend(_safe_fetch(lambda: _fetch_lever(config, filters), "Lever", failures))
    if "Company Career Page" in connectors:
        fetched_jobs.extend(_safe_fetch(lambda: _fetch_company_pages(config, filters), "Company Career Page", failures))

    matched_jobs: list[dict[str, Any]] = []
    new_fingerprints: list[str] = []
    for raw_job in fetched_jobs:
        job = _normalize_job(raw_job)
        if not job or not _job_matches_filters(job, filters):
            continue
        match = match_job_to_profile(job, profile)
        job.update(match)
        job["rank_score"] = rank_job(job, filters)
        fingerprint = upsert_job(job, db_path=db_path)
        job["fingerprint"] = fingerprint
        if job.get("_is_new"):
            new_fingerprints.append(fingerprint)
        matched_jobs.append(job)

    update_alerts_for_saved_searches(new_fingerprints, db_path=db_path)
    return {
        "jobs": sorted(matched_jobs, key=lambda item: item.get("rank_score", 0), reverse=True),
        "new_count": len(new_fingerprints),
        "failures": failures,
        "search_links": build_search_links(filters, config),
    }


def match_job_to_profile(job: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    profile_terms = _profile_terms(profile)
    job_keywords = extract_job_keywords(job)
    present = sorted(keyword for keyword in job_keywords if _contains_term(profile_terms["all"], keyword))
    missing = sorted(keyword for keyword in job_keywords if keyword not in present)
    missing_skills = sorted(keyword for keyword in missing if keyword in COMMON_TECH_KEYWORDS)

    project_scores = []
    for project in profile.get("projects", []):
        if not isinstance(project, dict):
            continue
        project_text = _normalize_text(
            " ".join(
                [
                    str(project.get("name") or ""),
                    str(project.get("description") or ""),
                    " ".join(project.get("technologies", [])),
                    " ".join(project.get("highlights", [])),
                ]
            )
        )
        overlap = [keyword for keyword in job_keywords if keyword in project_text]
        score = min(100, 25 + len(overlap) * 15) if overlap else 20
        project_scores.append(
            {
                "project_name": project.get("name") or "Project",
                "score": score,
                "reason": f"Overlaps with: {', '.join(overlap[:6])}" if overlap else "Limited keyword overlap with this role.",
            }
        )

    technical_score = _score_overlap(present, job_keywords)
    ats_score = min(100, round(technical_score * 0.75 + _keyword_density_score(job, profile_terms) * 0.25))
    experience_score = _experience_score(job, profile)
    education_score = _education_score(job, profile)
    overall = round(technical_score * 0.38 + ats_score * 0.22 + experience_score * 0.2 + education_score * 0.2)

    if overall >= 78:
        recommendation = "Strong Apply"
    elif overall >= 62:
        recommendation = "Apply"
    elif overall >= 45:
        recommendation = "Stretch Apply"
    else:
        recommendation = "Low Probability"

    recommended_projects = sorted(project_scores, key=lambda item: item["score"], reverse=True)[:3]
    return {
        "overall_match_score": overall,
        "ats_match_estimate": ats_score,
        "technical_match_score": technical_score,
        "experience_match_score": experience_score,
        "education_match_score": education_score,
        "missing_skills": missing_skills,
        "missing_keywords": missing[:12],
        "recommended_projects": recommended_projects,
        "apply_recommendation": recommendation,
    }


def rank_job(job: dict[str, Any], filters: SearchFilters) -> int:
    score = int(job.get("overall_match_score") or 0)
    title_text = _normalize_text(job.get("role", ""))
    location_text = _normalize_text(job.get("location", ""))
    country_text = _normalize_text(job.get("country", ""))

    if job.get("graduate") or any(term in title_text for term in GRADUATE_TERMS):
        score += 14
    if job.get("junior") or any(term in title_text for term in JUNIOR_TERMS):
        score += 12
    if job.get("sponsorship_available"):
        score += 12
    if job.get("remote_available"):
        score += 9
    if "uae" in country_text or "dubai" in location_text or "abu dhabi" in location_text:
        score += 10
    if "pakistan" in country_text or any(city in location_text for city in COUNTRY_HINTS["pakistan"]):
        score += 6

    if filters.ranking_preset == "Huzaifa Mode":
        uae = "uae" in country_text or "dubai" in location_text or "abu dhabi" in location_text
        europe = "europe" in country_text or any(term in location_text for term in COUNTRY_HINTS["europe"])
        pakistan = "pakistan" in country_text or any(city in location_text for city in COUNTRY_HINTS["pakistan"])
        if uae and job.get("sponsorship_available"):
            score += 32
        if job.get("remote_available") and "software" in title_text:
            score += 24
        if pakistan and "software" in title_text:
            score += 16
        if europe and job.get("sponsorship_available"):
            score += 12

    source_priority = int(job.get("source_priority") or 99)
    score += max(0, 12 - source_priority)
    return min(100, score)


def upsert_job(job: dict[str, Any], db_path: Path = JOB_DISCOVERY_DB_PATH) -> str:
    init_job_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    today = date.today().isoformat()
    fingerprint = job.get("fingerprint") or _fingerprint_job(job)
    job["fingerprint"] = fingerprint
    job.setdefault("date_found", today)
    job.setdefault("last_seen", now)
    job.setdefault("created_at", now)
    job.setdefault("updated_at", now)

    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute(
            "SELECT id, source, status, created_at FROM discovered_jobs WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        is_new = row is None
        if row:
            existing_sources = {source.strip() for source in str(row[1]).split(",") if source.strip()}
            existing_sources.add(job["source"])
            job["source"] = ", ".join(sorted(existing_sources))
            status = row[2]
            created_at = row[3]
        else:
            status = job.get("status", "Found")
            created_at = now

        conn.execute(
            """
            INSERT INTO discovered_jobs (
                fingerprint, company, role, location, country, city, salary, source, source_priority,
                apply_url, date_found, date_posted, sponsorship_available, remote_available,
                hybrid_available, graduate, junior, internship, experience_required, description,
                raw_payload, overall_match_score, ats_match_estimate, missing_skills, missing_keywords,
                recommended_projects, apply_recommendation, rank_score, status, last_seen, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fingerprint) DO UPDATE SET
                company=excluded.company,
                role=excluded.role,
                location=excluded.location,
                country=excluded.country,
                city=excluded.city,
                salary=excluded.salary,
                source=excluded.source,
                source_priority=MIN(discovered_jobs.source_priority, excluded.source_priority),
                apply_url=excluded.apply_url,
                date_posted=COALESCE(excluded.date_posted, discovered_jobs.date_posted),
                sponsorship_available=MAX(discovered_jobs.sponsorship_available, excluded.sponsorship_available),
                remote_available=MAX(discovered_jobs.remote_available, excluded.remote_available),
                hybrid_available=MAX(discovered_jobs.hybrid_available, excluded.hybrid_available),
                graduate=MAX(discovered_jobs.graduate, excluded.graduate),
                junior=MAX(discovered_jobs.junior, excluded.junior),
                internship=MAX(discovered_jobs.internship, excluded.internship),
                experience_required=COALESCE(excluded.experience_required, discovered_jobs.experience_required),
                description=COALESCE(excluded.description, discovered_jobs.description),
                raw_payload=excluded.raw_payload,
                overall_match_score=excluded.overall_match_score,
                ats_match_estimate=excluded.ats_match_estimate,
                missing_skills=excluded.missing_skills,
                missing_keywords=excluded.missing_keywords,
                recommended_projects=excluded.recommended_projects,
                apply_recommendation=excluded.apply_recommendation,
                rank_score=excluded.rank_score,
                status=?,
                last_seen=?,
                updated_at=?
            """,
            (
                fingerprint,
                job["company"],
                job["role"],
                job.get("location", ""),
                job.get("country", ""),
                job.get("city", ""),
                job.get("salary", ""),
                job["source"],
                int(job.get("source_priority") or 99),
                job["apply_url"],
                job.get("date_found", today),
                job.get("date_posted"),
                int(bool(job.get("sponsorship_available"))),
                int(bool(job.get("remote_available"))),
                int(bool(job.get("hybrid_available"))),
                int(bool(job.get("graduate"))),
                int(bool(job.get("junior"))),
                int(bool(job.get("internship"))),
                job.get("experience_required", ""),
                job.get("description", ""),
                json.dumps(job.get("raw_payload", {}), ensure_ascii=False),
                job.get("overall_match_score"),
                job.get("ats_match_estimate"),
                json.dumps(job.get("missing_skills", []), ensure_ascii=False),
                json.dumps(job.get("missing_keywords", []), ensure_ascii=False),
                json.dumps(job.get("recommended_projects", []), ensure_ascii=False),
                job.get("apply_recommendation", ""),
                job.get("rank_score"),
                status,
                now,
                created_at,
                now,
                status,
                now,
                now,
            ),
        )
        conn.commit()
    job["_is_new"] = is_new
    return fingerprint


def list_discovered_jobs(
    db_path: Path = JOB_DISCOVERY_DB_PATH,
    filters: SearchFilters | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    init_job_db(db_path)
    query = "SELECT * FROM discovered_jobs"
    params: list[Any] = []
    where: list[str] = []
    if filters:
        if filters.role:
            where.append("LOWER(role) LIKE ?")
            params.append(f"%{filters.role.lower()}%")
        if filters.country and filters.country != "Any":
            where.append("(LOWER(country) LIKE ? OR LOWER(location) LIKE ?)")
            country = filters.country.lower()
            params.extend([f"%{country}%", f"%{country}%"])
        if filters.city:
            where.append("LOWER(location) LIKE ?")
            params.append(f"%{filters.city.lower()}%")
        if filters.remote:
            where.append("remote_available = 1")
        if filters.hybrid:
            where.append("hybrid_available = 1")
        if filters.visa_sponsorship:
            where.append("sponsorship_available = 1")
        if filters.graduate:
            where.append("graduate = 1")
        if filters.junior:
            where.append("junior = 1")
        if filters.internship:
            where.append("internship = 1")
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY rank_score DESC, overall_match_score DESC, updated_at DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [_decode_job_row(dict(row)) for row in rows]


def job_dashboard_stats(db_path: Path = JOB_DISCOVERY_DB_PATH) -> dict[str, int]:
    init_job_db(db_path)
    today = date.today().isoformat()
    with closing(sqlite3.connect(db_path)) as conn:
        total = conn.execute("SELECT COUNT(*) FROM discovered_jobs").fetchone()[0]
        new_today = conn.execute("SELECT COUNT(*) FROM discovered_jobs WHERE date_found = ?", (today,)).fetchone()[0]
        applied = conn.execute("SELECT COUNT(*) FROM discovered_jobs WHERE status = 'Applied'").fetchone()[0]
        interviews = conn.execute("SELECT COUNT(*) FROM discovered_jobs WHERE status = 'Interviewing'").fetchone()[0]
        offers = conn.execute("SELECT COUNT(*) FROM discovered_jobs WHERE status = 'Offer'").fetchone()[0]
        highest = conn.execute("SELECT COALESCE(MAX(overall_match_score), 0) FROM discovered_jobs").fetchone()[0]
    return {
        "total_jobs_found": int(total),
        "new_today": int(new_today),
        "applied": int(applied),
        "interviews": int(interviews),
        "offers": int(offers),
        "highest_match_score": int(highest or 0),
    }


def set_discovered_job_status(
    job_id: int,
    status: str,
    db_path: Path = JOB_DISCOVERY_DB_PATH,
    also_save_tracker: bool = True,
) -> int | None:
    if status not in JOB_STATUSES:
        raise ValueError(f"Unsupported job status: {status}")
    init_job_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM discovered_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Discovered job not found.")
        conn.execute("UPDATE discovered_jobs SET status = ?, updated_at = ? WHERE id = ?", (status, now, job_id))
        conn.commit()
    if not also_save_tracker:
        return None

    tracker_status = "Needs Review" if status == "Saved" else status
    if tracker_status == "Found":
        tracker_status = "Needs Review"
    return save_application(
        job_title=row["role"],
        company=row["company"],
        location=row["location"] or "",
        apply_link=row["apply_url"] or "",
        status=tracker_status,
        application_date=date.today().isoformat(),
        fit_score=row["overall_match_score"],
        ats_match_percent=row["ats_match_estimate"],
        notes=f"Imported from Job Discovery. Source: {row['source']}. Recommendation: {row['apply_recommendation'] or 'N/A'}",
    )


def save_search(name: str, filters: SearchFilters, db_path: Path = JOB_DISCOVERY_DB_PATH) -> int:
    init_job_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO saved_searches (name, filters_json, ranking_preset, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip() or f"Search {now}", json.dumps(filters.as_dict()), filters.ranking_preset, now),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_saved_searches(db_path: Path = JOB_DISCOVERY_DB_PATH) -> list[dict[str, Any]]:
    init_job_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM saved_searches ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def list_alerts(db_path: Path = JOB_DISCOVERY_DB_PATH, only_unseen: bool = True) -> list[dict[str, Any]]:
    init_job_db(db_path)
    query = """
        SELECT job_alerts.*, saved_searches.name AS search_name
        FROM job_alerts
        LEFT JOIN saved_searches ON saved_searches.id = job_alerts.saved_search_id
    """
    if only_unseen:
        query += " WHERE job_alerts.seen = 0"
    query += " ORDER BY job_alerts.created_at DESC"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query).fetchall()
    return [dict(row) for row in rows]


def update_alerts_for_saved_searches(new_fingerprints: list[str], db_path: Path = JOB_DISCOVERY_DB_PATH) -> None:
    if not new_fingerprints:
        return
    searches = list_saved_searches(db_path)
    if not searches:
        return
    jobs = {job["fingerprint"]: job for job in list_discovered_jobs(db_path) if job.get("fingerprint") in new_fingerprints}
    now = datetime.now().isoformat(timespec="seconds")
    with closing(sqlite3.connect(db_path)) as conn:
        for search in searches:
            filters = SearchFilters(**json.loads(search["filters_json"]))
            matched = [job for job in jobs.values() if _job_matches_filters(job, filters)]
            for job in matched:
                exists = conn.execute(
                    "SELECT id FROM job_alerts WHERE saved_search_id = ? AND job_fingerprint = ?",
                    (search["id"], job["fingerprint"]),
                ).fetchone()
                if not exists:
                    conn.execute(
                        """
                        INSERT INTO job_alerts (saved_search_id, job_fingerprint, message, created_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            search["id"],
                            job["fingerprint"],
                            f"New match for {search['name']}: {job['role']} at {job['company']}",
                            now,
                        ),
                    )
            conn.execute(
                "UPDATE saved_searches SET last_run_at = ?, last_new_count = ? WHERE id = ?",
                (now, len(matched), search["id"]),
            )
        conn.commit()


def export_jobs_csv(jobs: list[dict[str, Any]]) -> bytes:
    output = io.StringIO()
    fieldnames = _export_fieldnames()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for job in jobs:
        writer.writerow(_flatten_job_for_export(job))
    return output.getvalue().encode("utf-8")


def export_jobs_json(jobs: list[dict[str, Any]]) -> bytes:
    return json.dumps(jobs, indent=2, ensure_ascii=False).encode("utf-8")


def export_jobs_excel(jobs: list[dict[str, Any]]) -> bytes:
    output = io.BytesIO()
    rows = [_flatten_job_for_export(job) for job in jobs]
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(rows, columns=_export_fieldnames()).to_excel(writer, index=False, sheet_name="Jobs")
    return output.getvalue()


def build_search_links(filters: SearchFilters, config: dict[str, Any] | None = None) -> list[dict[str, str]]:
    config = config or ensure_source_config()
    query = quote_plus(filters.role or "software engineer")
    location = quote_plus(" ".join(part for part in [filters.city, "" if filters.country == "Any" else filters.country] if part))
    links = []
    for item in config.get("platform_search_templates", []):
        links.append(
            {
                "source": item["source"],
                "url": item["url"].format(query=query, location=location),
                "note": "Official search link. Not scraped because no safe public feed is configured.",
            }
        )
    return links


def _safe_fetch(fetcher: Any, source_name: str, failures: list[str]) -> list[dict[str, Any]]:
    try:
        return fetcher()
    except Exception as exc:
        logger.warning("Job source %s failed gracefully: %s", source_name, exc)
        failures.append(f"{source_name}: {exc}")
        return []


def _request_json(url: str) -> Any:
    response = _request_get(url)
    return response.json()


def _request_text(url: str) -> str:
    return _request_get(url).text


def _request_get(url: str) -> requests.Response:
    attempts = max(1, SETTINGS.retry_attempts)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= attempts:
                break
            delay = SETTINGS.retry_backoff_seconds * (2 ** (attempt - 1))
            logger.warning("GET %s failed on attempt %s/%s: %s", url, attempt, attempts, exc)
            time.sleep(delay)
    raise RuntimeError(f"GET {url} failed after {attempts} attempt(s): {last_error}")


def _fetch_remoteok(filters: SearchFilters) -> list[dict[str, Any]]:
    query = quote_plus(filters.role or "software engineer")
    url = f"https://remoteok.com/api?tags={query}"
    data = _request_json(url)
    jobs = []
    for item in data[1:] if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        jobs.append(
            {
                "company": item.get("company") or "Unknown company",
                "role": item.get("position") or item.get("slug") or "Unknown role",
                "location": item.get("location") or "Remote",
                "country": "Remote",
                "city": "",
                "salary": item.get("salary") or "",
                "source": "RemoteOK",
                "apply_url": item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id')}",
                "date_posted": item.get("date"),
                "description": _strip_html(item.get("description") or ""),
                "remote_available": True,
                "raw_payload": item,
            }
        )
    return jobs


def _fetch_greenhouse(config: dict[str, Any], filters: SearchFilters) -> list[dict[str, Any]]:
    jobs = []
    for board in config.get("greenhouse_boards", []):
        token = board.get("board_token")
        if not token:
            continue
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        data = _request_json(url)
        company = board.get("company") or token
        for item in data.get("jobs", []):
            location = (item.get("location") or {}).get("name", "")
            jobs.append(
                {
                    "company": company,
                    "role": item.get("title") or "Unknown role",
                    "location": location,
                    "country": board.get("country") or _infer_country(location),
                    "city": _infer_city(location),
                    "salary": "",
                    "source": "Greenhouse",
                    "apply_url": item.get("absolute_url") or "",
                    "date_posted": item.get("updated_at"),
                    "description": _strip_html(item.get("content") or ""),
                    "raw_payload": item,
                }
            )
    return jobs


def _fetch_lever(config: dict[str, Any], filters: SearchFilters) -> list[dict[str, Any]]:
    jobs = []
    for company in config.get("lever_companies", []):
        slug = company.get("slug")
        if not slug:
            continue
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        data = _request_json(url)
        for item in data if isinstance(data, list) else []:
            categories = item.get("categories") or {}
            location = categories.get("location") or ""
            description = "\n".join(
                str(list_item.get("text", ""))
                for list_item in item.get("lists", [])
                if isinstance(list_item, dict)
            )
            jobs.append(
                {
                    "company": company.get("company") or slug,
                    "role": item.get("text") or "Unknown role",
                    "location": location,
                    "country": company.get("country") or _infer_country(location),
                    "city": _infer_city(location),
                    "salary": "",
                    "source": "Lever",
                    "apply_url": item.get("hostedUrl") or item.get("applyUrl") or "",
                    "date_posted": item.get("createdAt"),
                    "description": _strip_html(description),
                    "raw_payload": item,
                }
            )
    return jobs


def _fetch_company_pages(config: dict[str, Any], filters: SearchFilters) -> list[dict[str, Any]]:
    jobs = []
    pages = [page for page in config.get("company_career_pages", []) if page.get("url")]
    if not pages:
        return jobs
    max_workers = min(4, len(pages))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_fetch_company_page, page, filters) for page in pages]
        for future in as_completed(futures):
            try:
                jobs.extend(future.result())
            except Exception as exc:
                logger.warning("Company career page failed gracefully: %s", exc)
    return jobs


def _fetch_company_page(page: dict[str, Any], filters: SearchFilters) -> list[dict[str, Any]]:
    url = page.get("url")
    if not url or not _robots_allows(url):
        return []
    html = _request_text(url)
    jobs = []
    for link_text, href in _extract_job_links(html, url, filters.role):
        jobs.append(
            {
                "company": page.get("company") or "Company",
                "role": link_text,
                "location": page.get("country") or "",
                "country": page.get("country") or "",
                "city": "",
                "salary": "",
                "source": "Company Career Page",
                "apply_url": href,
                "description": link_text,
                "raw_payload": {"career_page": url},
            }
        )
    return jobs


def _normalize_job(raw_job: dict[str, Any]) -> dict[str, Any] | None:
    company = str(raw_job.get("company") or "").strip()
    role = str(raw_job.get("role") or "").strip()
    apply_url = str(raw_job.get("apply_url") or "").strip()
    if not company or not role or not apply_url:
        return None

    text = _normalize_text(" ".join(str(raw_job.get(key, "")) for key in ("role", "location", "description")))
    source = raw_job.get("source") or "Unknown"
    location = str(raw_job.get("location") or "").strip()
    country = str(raw_job.get("country") or _infer_country(location)).strip()
    city = str(raw_job.get("city") or _infer_city(location)).strip()

    job = {
        "company": company,
        "role": role,
        "location": location,
        "country": country,
        "city": city,
        "salary": str(raw_job.get("salary") or ""),
        "source": source,
        "source_priority": SOURCE_PRIORITY.get(source, 99),
        "apply_url": apply_url,
        "date_found": date.today().isoformat(),
        "date_posted": raw_job.get("date_posted"),
        "sponsorship_available": bool(raw_job.get("sponsorship_available")) or any(term in text for term in SPONSORSHIP_TERMS),
        "remote_available": bool(raw_job.get("remote_available")) or any(term in text for term in REMOTE_TERMS),
        "hybrid_available": bool(raw_job.get("hybrid_available")) or any(term in text for term in HYBRID_TERMS),
        "graduate": bool(raw_job.get("graduate")) or any(term in text for term in GRADUATE_TERMS),
        "junior": bool(raw_job.get("junior")) or any(term in text for term in JUNIOR_TERMS),
        "internship": bool(raw_job.get("internship")) or any(term in text for term in INTERNSHIP_TERMS),
        "experience_required": _extract_experience_required(text),
        "description": str(raw_job.get("description") or ""),
        "raw_payload": raw_job.get("raw_payload", raw_job),
    }
    job["fingerprint"] = _fingerprint_job(job)
    return job


def _job_matches_filters(job: dict[str, Any], filters: SearchFilters) -> bool:
    text = _normalize_text(" ".join(str(job.get(key, "")) for key in ("company", "role", "location", "country", "description")))
    if filters.role and not any(term in text for term in _role_terms(filters.role)):
        return False
    if filters.country and filters.country != "Any":
        if filters.country.lower() not in text and not any(hint in text for hint in COUNTRY_HINTS.get(filters.country.lower(), set())):
            return False
    if filters.city and filters.city.lower() not in text:
        return False
    if filters.remote and not job.get("remote_available"):
        return False
    if filters.hybrid and not job.get("hybrid_available"):
        return False
    if filters.visa_sponsorship and not job.get("sponsorship_available"):
        return False
    role_flags = []
    if filters.graduate:
        role_flags.append(bool(job.get("graduate")))
    if filters.junior:
        role_flags.append(bool(job.get("junior")))
    if filters.internship:
        role_flags.append(bool(job.get("internship")))
    if role_flags and not any(role_flags):
        title = _normalize_text(job.get("role", ""))
        if not any(term in title for term in GRADUATE_TERMS | JUNIOR_TERMS | INTERNSHIP_TERMS):
            return False
    return True


def extract_job_keywords(job: dict[str, Any]) -> set[str]:
    text = _normalize_text(" ".join(str(job.get(key, "")) for key in ("role", "description", "location")))
    keywords = {keyword for keyword in COMMON_TECH_KEYWORDS | ROLE_KEYWORDS if keyword in text}
    for token in re.findall(r"[a-z][a-z0-9+#./-]{2,}", text):
        if token in COMMON_TECH_KEYWORDS:
            keywords.add(token)
    return keywords


def _profile_terms(profile: dict[str, Any]) -> dict[str, str]:
    profile = enhance_profile(profile)
    parts = [json.dumps(profile, ensure_ascii=False)]
    return {"all": _normalize_text(" ".join(parts))}


def _score_overlap(present: list[str], required: set[str]) -> int:
    if not required:
        return 50
    return min(100, round((len(present) / len(required)) * 100))


def _keyword_density_score(job: dict[str, Any], profile_terms: dict[str, str]) -> int:
    keywords = extract_job_keywords(job)
    if not keywords:
        return 50
    present = sum(1 for keyword in keywords if _contains_term(profile_terms["all"], keyword))
    return round((present / len(keywords)) * 100)


def _experience_score(job: dict[str, Any], profile: dict[str, Any]) -> int:
    experiences = profile.get("experience", [])
    if not experiences:
        return 35
    text = _normalize_text(job.get("description", "") + " " + job.get("role", ""))
    if any(term in text for term in GRADUATE_TERMS | JUNIOR_TERMS | INTERNSHIP_TERMS):
        return 75
    return 60


def _education_score(job: dict[str, Any], profile: dict[str, Any]) -> int:
    education = profile.get("education", [])
    if not education:
        return 30
    text = _normalize_text(job.get("description", "") + " " + job.get("role", ""))
    degree_text = _normalize_text(json.dumps(education, ensure_ascii=False))
    if "computer science" in text and "software engineering" in degree_text:
        return 85
    if "software" in text and "software engineering" in degree_text:
        return 90
    return 70


def _contains_term(text: str, term: str) -> bool:
    return _normalize_text(term) in text


def _role_terms(role: str) -> set[str]:
    role = _normalize_text(role)
    terms = {role}
    terms.update(part for part in role.split() if len(part) > 3)
    if "software" in role:
        terms.update({"software engineer", "software developer", "backend", "frontend", "full stack"})
    return terms


def _extract_experience_required(text: str) -> str:
    matches = re.findall(r"(\d+\+?\s*(?:-|to)?\s*\d*\+?\s*years?)", text)
    return matches[0] if matches else ""


def _fingerprint_job(job: dict[str, Any]) -> str:
    normalized = "|".join(
        [
            _normalize_key(job.get("company")),
            _normalize_key(job.get("role")),
            _normalize_key(job.get("location") or job.get("country")),
        ]
    )
    if normalized == "||":
        normalized = _normalize_key(job.get("apply_url"))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _strip_html(str(value or "")).lower()).strip()


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    return unescape(re.sub(r"\s+", " ", text)).replace("\xa0", " ").strip()


def _infer_country(location: str) -> str:
    text = _normalize_text(location)
    for country, hints in COUNTRY_HINTS.items():
        if country in text or any(hint in text for hint in hints):
            return "UAE" if country == "uae" else country.title()
    if "remote" in text:
        return "Remote"
    return ""


def _infer_city(location: str) -> str:
    text = _normalize_text(location)
    for city in sorted(COUNTRY_HINTS["pakistan"] | COUNTRY_HINTS["uae"], key=len, reverse=True):
        if city in text and city not in {"pakistan", "uae", "united arab emirates"}:
            return city.title()
    return ""


def _robots_allows(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        return False
    return parser.can_fetch(USER_AGENT, url)


def _extract_job_links(html: str, base_url: str, role: str) -> list[tuple[str, str]]:
    links = []
    role_terms = _role_terms(role)
    for href, text in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, flags=re.I | re.S):
        clean_text = _strip_html(text)
        text_norm = _normalize_text(clean_text)
        href_norm = _normalize_text(href)
        if not clean_text or len(clean_text) > 120:
            continue
        if any(term in text_norm or term in href_norm for term in role_terms | GRADUATE_TERMS | JUNIOR_TERMS):
            links.append((clean_text, urljoin(base_url, href)))
    deduped: dict[str, str] = {}
    for title, url in links:
        deduped[url] = title
    return [(title, url) for url, title in deduped.items()]


def _decode_job_row(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("missing_skills", "missing_keywords", "recommended_projects"):
        try:
            row[key] = json.loads(row.get(key) or "[]")
        except json.JSONDecodeError:
            row[key] = []
    for key in (
        "sponsorship_available",
        "remote_available",
        "hybrid_available",
        "graduate",
        "junior",
        "internship",
    ):
        row[key] = bool(row.get(key))
    return row


def _flatten_job_for_export(job: dict[str, Any]) -> dict[str, Any]:
    flattened = dict(job)
    for key in ("missing_skills", "missing_keywords", "recommended_projects"):
        flattened[key] = json.dumps(job.get(key, []), ensure_ascii=False)
    return flattened


def _export_fieldnames() -> list[str]:
    return [
        "company",
        "role",
        "location",
        "country",
        "city",
        "salary",
        "source",
        "apply_url",
        "date_found",
        "date_posted",
        "sponsorship_available",
        "remote_available",
        "hybrid_available",
        "graduate",
        "junior",
        "internship",
        "experience_required",
        "overall_match_score",
        "ats_match_estimate",
        "missing_skills",
        "missing_keywords",
        "recommended_projects",
        "apply_recommendation",
        "rank_score",
        "status",
    ]
