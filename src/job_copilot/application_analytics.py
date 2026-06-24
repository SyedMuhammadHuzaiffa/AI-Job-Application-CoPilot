from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .config import JOB_DISCOVERY_DB_PATH, TRACKER_DB_PATH
from .job_discovery import init_job_db, list_discovered_jobs
from .tracker import init_db, list_applications


SENT_STATUSES = {"Applied", "Awaiting response", "Interviewing", "Rejected", "Offer"}
INTERVIEW_STATUSES = {"Interviewing", "Offer"}
REJECTION_STATUSES = {"Rejected"}
OFFER_STATUSES = {"Offer"}
RESPONSE_STATUSES = {"Interviewing", "Rejected", "Offer"}

COUNTRY_HINTS = {
    "Pakistan": {"pakistan", "karachi", "lahore", "islamabad", "rawalpindi"},
    "UAE": {"uae", "united arab emirates", "dubai", "abu dhabi", "sharjah"},
    "Remote": {"remote", "worldwide", "anywhere"},
    "Europe": {"germany", "netherlands", "sweden", "uk", "united kingdom", "ireland", "poland", "portugal", "spain"},
}


def load_analytics_rows(
    tracker_db_path: Path = TRACKER_DB_PATH,
    discovery_db_path: Path = JOB_DISCOVERY_DB_PATH,
) -> list[dict[str, Any]]:
    init_db(tracker_db_path)
    apps = list_applications(tracker_db_path)
    discovered = _discovered_lookup(discovery_db_path)
    rows = []

    for app in apps:
        discovery = _lookup_discovered(app, discovered)
        location = app.get("location") or discovery.get("location") or ""
        source = discovery.get("source") or _source_from_notes_or_link(app)
        country = discovery.get("country") or _infer_country(location)
        ats = app.get("ats_match_percent")
        if ats is None:
            ats = discovery.get("ats_match_estimate")

        row = {
            "id": app.get("id"),
            "company": app.get("company") or discovery.get("company") or "Unknown",
            "role": app.get("job_title") or discovery.get("role") or "Unknown",
            "location": location,
            "country": country or "Unknown",
            "source": source or "Unknown",
            "status": app.get("status") or "Unknown",
            "application_date": app.get("application_date") or app.get("created_at"),
            "month": _month(app.get("application_date") or app.get("created_at")),
            "fit_score": _to_int(app.get("fit_score") if app.get("fit_score") is not None else discovery.get("overall_match_score")),
            "ats_match_percent": _to_int(ats),
            "apply_link": app.get("apply_link") or discovery.get("apply_url") or "",
        }
        rows.append(row)

    return rows


def compute_application_analytics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sent_rows = [row for row in rows if row.get("status") in SENT_STATUSES]
    applications_sent = len(sent_rows)
    interviews = sum(1 for row in sent_rows if row.get("status") in INTERVIEW_STATUSES)
    rejections = sum(1 for row in sent_rows if row.get("status") in REJECTION_STATUSES)
    offers = sum(1 for row in sent_rows if row.get("status") in OFFER_STATUSES)
    responses = sum(1 for row in sent_rows if row.get("status") in RESPONSE_STATUSES)

    metrics = {
        "applications_sent": applications_sent,
        "interviews_received": interviews,
        "rejections": rejections,
        "offers": offers,
        "response_rate": _rate(responses, applications_sent),
        "interview_rate": _rate(interviews, applications_sent),
        "offer_rate": _rate(offers, applications_sent),
    }

    breakdowns = {
        "by_country": _breakdown(sent_rows, "country"),
        "by_company": _breakdown(sent_rows, "company"),
        "by_role": _breakdown(sent_rows, "role"),
        "by_source": _breakdown(sent_rows, "source"),
        "by_month": _breakdown(sent_rows, "month"),
    }

    charts = {
        "applications_over_time": _applications_over_time(sent_rows),
        "interview_funnel": [
            {"stage": "Applications", "count": applications_sent},
            {"stage": "Interviews", "count": interviews},
        ],
        "offer_funnel": [
            {"stage": "Applications", "count": applications_sent},
            {"stage": "Interviews", "count": interviews},
            {"stage": "Offers", "count": offers},
        ],
    }

    insights = _build_insights(sent_rows, breakdowns)

    return {
        "metrics": metrics,
        "breakdowns": breakdowns,
        "charts": charts,
        "insights": insights,
        "rows": sent_rows,
    }


def analytics_to_dataframes(analytics: dict[str, Any]) -> dict[str, pd.DataFrame]:
    frames = {
        "applications": pd.DataFrame(analytics.get("rows", [])),
        "applications_over_time": pd.DataFrame(analytics.get("charts", {}).get("applications_over_time", [])),
        "interview_funnel": pd.DataFrame(analytics.get("charts", {}).get("interview_funnel", [])),
        "offer_funnel": pd.DataFrame(analytics.get("charts", {}).get("offer_funnel", [])),
    }
    for key, rows in analytics.get("breakdowns", {}).items():
        frames[key] = pd.DataFrame(rows)
    return frames


def _discovered_lookup(db_path: Path) -> dict[str, dict[str, Any]]:
    if not db_path.exists():
        return {}
    init_job_db(db_path)
    jobs = list_discovered_jobs(db_path)
    lookup: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if job.get("apply_url"):
            lookup[f"url:{job['apply_url']}"] = job
        key = _company_role_key(job.get("company"), job.get("role"))
        if key:
            lookup[f"key:{key}"] = job
    return lookup


def _lookup_discovered(app: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    apply_link = app.get("apply_link")
    if apply_link and f"url:{apply_link}" in lookup:
        return lookup[f"url:{apply_link}"]
    key = _company_role_key(app.get("company"), app.get("job_title"))
    if key and f"key:{key}" in lookup:
        return lookup[f"key:{key}"]
    return {}


def _company_role_key(company: Any, role: Any) -> str:
    company_text = str(company or "").strip().lower()
    role_text = str(role or "").strip().lower()
    if not company_text or not role_text:
        return ""
    return f"{company_text}|{role_text}"


def _source_from_notes_or_link(app: dict[str, Any]) -> str:
    notes = str(app.get("notes") or "")
    if "Source:" in notes:
        return notes.split("Source:", 1)[1].split(".", 1)[0].strip()
    link = str(app.get("apply_link") or "").lower()
    if "linkedin" in link:
        return "LinkedIn"
    if "indeed" in link:
        return "Indeed"
    if "greenhouse" in link:
        return "Greenhouse"
    if "lever" in link:
        return "Lever"
    if "remoteok" in link:
        return "RemoteOK"
    return "Manual"


def _infer_country(location: str) -> str:
    text = str(location or "").lower()
    for country, hints in COUNTRY_HINTS.items():
        if any(hint in text for hint in hints):
            return country
    return "Unknown"


def _month(value: Any) -> str:
    text = str(value or "")
    return text[:7] if len(text) >= 7 else "Unknown"


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _breakdown(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(field) or "Unknown")
        groups.setdefault(key, []).append(row)

    breakdown = []
    for key, group in groups.items():
        sent = len(group)
        interviews = sum(1 for row in group if row.get("status") in INTERVIEW_STATUSES)
        rejections = sum(1 for row in group if row.get("status") in REJECTION_STATUSES)
        offers = sum(1 for row in group if row.get("status") in OFFER_STATUSES)
        responses = sum(1 for row in group if row.get("status") in RESPONSE_STATUSES)
        ats_values = [row["ats_match_percent"] for row in group if row.get("ats_match_percent") is not None]
        breakdown.append(
            {
                field: key,
                "applications": sent,
                "responses": responses,
                "interviews": interviews,
                "rejections": rejections,
                "offers": offers,
                "response_rate": _rate(responses, sent),
                "interview_rate": _rate(interviews, sent),
                "offer_rate": _rate(offers, sent),
                "avg_ats": round(sum(ats_values) / len(ats_values), 1) if ats_values else None,
            }
        )
    return sorted(breakdown, key=lambda item: (item["interviews"], item["offers"], item["applications"]), reverse=True)


def _applications_over_time(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter = Counter(row.get("month") or "Unknown" for row in rows)
    return [{"month": month, "applications": counter[month]} for month in sorted(counter)]


def _build_insights(rows: list[dict[str, Any]], breakdowns: dict[str, list[dict[str, Any]]]) -> list[str]:
    insights: list[str] = []
    source_rows = [row for row in breakdowns.get("by_source", []) if row["applications"] > 0]
    if source_rows:
        best_source = max(source_rows, key=lambda row: (row["interview_rate"], row["offer_rate"], row["applications"]))
        insights.append(
            f"Best performing source so far: {best_source['source']} with {best_source['interview_rate']}% interview rate across {best_source['applications']} applications."
        )

    role_rows = [row for row in breakdowns.get("by_role", []) if row["interviews"] > 0]
    if role_rows:
        best_role = max(role_rows, key=lambda row: (row["interviews"], row["interview_rate"]))
        insights.append(
            f"Role producing interviews: {best_role['role']} has {best_role['interviews']} interview(s) from {best_role['applications']} application(s)."
        )
    else:
        insights.append("No role has produced interviews yet. Keep tracking outcomes after each application.")

    ats_insight = _ats_interview_insight(rows)
    if ats_insight:
        insights.append(ats_insight)

    if not rows:
        insights.append("No sent applications yet. Mark jobs as Applied, Interviewing, Rejected, or Offer to activate analytics.")

    return insights


def _ats_interview_insight(rows: list[dict[str, Any]]) -> str:
    with_ats = [row for row in rows if row.get("ats_match_percent") is not None]
    if len(with_ats) < 2:
        return "Not enough ATS data yet to compare ATS scores with interviews."

    interviewed = [row["ats_match_percent"] for row in with_ats if row.get("status") in INTERVIEW_STATUSES]
    not_interviewed = [row["ats_match_percent"] for row in with_ats if row.get("status") not in INTERVIEW_STATUSES]
    if not interviewed:
        return "ATS scores are being tracked, but no interviews have been recorded yet."
    if not not_interviewed:
        return "All ATS-scored applications with outcomes have interviews so far; keep collecting data."

    avg_interviewed = round(sum(interviewed) / len(interviewed), 1)
    avg_other = round(sum(not_interviewed) / len(not_interviewed), 1)
    direction = "higher" if avg_interviewed > avg_other else "not higher"
    return (
        f"ATS scores for interview outcomes average {avg_interviewed}, versus {avg_other} for non-interview outcomes. "
        f"So far, ATS score is {direction} for interview-producing applications."
    )
