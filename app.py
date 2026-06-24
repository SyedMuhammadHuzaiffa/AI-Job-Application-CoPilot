import copy
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from job_copilot.config import (
    DEFAULT_MODEL,
    DEFAULT_PROFILE_PATH,
    EXPORT_DIR,
    JOB_DISCOVERY_DB_PATH,
    JOB_SOURCE_CONFIG_PATH,
    MODEL_OPTIONS,
    SAMPLE_PROFILE_PATH,
    SETTINGS,
    TRACKER_DB_PATH,
)
from job_copilot.application_analytics import (
    analytics_to_dataframes,
    compute_application_analytics,
    load_analytics_rows,
)
from job_copilot.job_discovery import (
    JOB_STATUSES,
    SearchFilters,
    build_search_links,
    ensure_source_config,
    export_jobs_csv,
    export_jobs_excel,
    export_jobs_json,
    job_dashboard_stats,
    list_alerts,
    list_discovered_jobs,
    list_saved_searches,
    save_search,
    search_jobs,
    set_discovered_job_status,
)
from job_copilot.latex import write_exports
from job_copilot.llm import OpenAIConfigError, generate_tailoring
from job_copilot.logging_config import configure_logging
from job_copilot.profile import (
    ProfileError,
    generate_enhanced_profile_file,
    load_profile,
    profile_display_name,
    validate_profile,
)
from job_copilot.resume_intelligence import (
    analysis_to_markdown,
    build_profile_cv_text,
    generate_resume_intelligence,
    markdown_to_pdf_bytes,
)
from job_copilot.tracker import DASHBOARD_STATUSES, STATUSES, init_db, list_applications, save_application


configure_logging(SETTINGS.log_level)

st.set_page_config(
    page_title="Job Application Co-Pilot",
    layout="wide",
)


def _apply_theme(dark_mode: bool) -> None:
    if dark_mode:
        st.markdown(
            """
            <style>
            .stApp {
                background: #0f172a;
                color: #e5e7eb;
            }
            [data-testid="stSidebar"] {
                background: #111827;
            }
            [data-testid="stMetric"] {
                background: #111827;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0.85rem;
            }
            div[data-testid="stDataFrame"] {
                border: 1px solid #334155;
                border-radius: 8px;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <style>
            [data-testid="stMetric"] {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 0.85rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


def _set_job_defaults(result: dict) -> None:
    job = result.get("job", {})
    mapping = {
        "job_title": "title",
        "company": "company",
        "location": "location",
        "apply_link": "apply_link",
    }
    for state_key, job_key in mapping.items():
        value = str(job.get(job_key, "") or "").strip()
        if value and not st.session_state.get(state_key):
            st.session_state[state_key] = value


def _edited_result(result: dict) -> dict:
    edited = copy.deepcopy(result)

    bullets = []
    for index, item in enumerate(result.get("cv", {}).get("bullets", []), start=1):
        source = item.get("source", f"Profile item {index}")
        text = st.text_area(
            f"CV bullet {index}: {source}",
            value=item.get("tailored", ""),
            height=90,
            key=f"cv_bullet_{index}",
        )
        if text.strip():
            bullets.append({"source": source, "tailored": text.strip()})
    edited.setdefault("cv", {})["bullets"] = bullets

    cover_body = "\n\n".join(result.get("cover_letter", {}).get("body", []))
    cover_text = st.text_area(
        "Cover letter",
        value=cover_body,
        height=230,
        key="cover_letter_body",
    )
    edited.setdefault("cover_letter", {})["body"] = [
        paragraph.strip() for paragraph in cover_text.split("\n\n") if paragraph.strip()
    ]

    answers = []
    for index, item in enumerate(result.get("application_answers", []), start=1):
        question = item.get("question", f"Question {index}")
        answer = st.text_area(
            question,
            value=item.get("answer", ""),
            height=95,
            key=f"answer_{index}",
        )
        answers.append({"question": question, "answer": answer.strip()})
    edited["application_answers"] = answers

    return edited


def _job_meta() -> dict[str, str]:
    return {
        "title": st.session_state.get("job_title", "").strip(),
        "company": st.session_state.get("company", "").strip(),
        "location": st.session_state.get("location", "").strip(),
        "apply_link": st.session_state.get("apply_link", "").strip(),
    }


def _fit_score(result: dict | None) -> int | None:
    if not result:
        return None
    return int(result.get("fit", {}).get("score", 0))


def _ats_match(result: dict | None) -> int | None:
    if not result:
        return None
    return int(result.get("fit", {}).get("ats_match_percent", 0))


def _render_bullets(items: list[str]) -> None:
    if not items:
        st.caption("None listed.")
        return
    for item in items:
        st.write(f"- {item}")


def _render_fit(result: dict) -> None:
    fit = result.get("fit", {})
    score = int(fit.get("score", 0))
    ats_match = int(fit.get("ats_match_percent", 0))

    score_col, ats_col, keyword_col = st.columns([0.24, 0.24, 0.52], gap="large")
    with score_col:
        st.metric("Fit score", f"{score}/100")
        st.progress(score / 100)
    with ats_col:
        st.metric("ATS match", f"{ats_match}%")
        st.progress(ats_match / 100)
    with keyword_col:
        st.markdown("**ATS keywords**")
        keywords = result.get("ats_keywords", [])
        st.write(", ".join(keywords) if keywords else "No keywords generated yet.")

    strengths_col, gaps_col, learning_col, strategy_col = st.columns(4)
    with strengths_col:
        st.markdown("**Strengths**")
        _render_bullets(fit.get("strengths", []))
    with gaps_col:
        st.markdown("**Skill gaps**")
        _render_bullets(fit.get("skill_gaps") or fit.get("gaps", []))
    with learning_col:
        st.markdown("**Learning topics**")
        _render_bullets(fit.get("recommended_learning_topics", []))
    with strategy_col:
        st.markdown("**Strategy**")
        _render_bullets(fit.get("strategy", []))


def _status_counts(rows: list[dict]) -> Counter:
    return Counter(row.get("status", "") for row in rows)


def _average(values: list[int]) -> int:
    if not values:
        return 0
    return round(sum(values) / len(values))


def _render_dashboard(rows: list[dict]) -> None:
    st.subheader("Application Dashboard")
    counts = _status_counts(rows)

    cols = st.columns(len(DASHBOARD_STATUSES))
    for col, status in zip(cols, DASHBOARD_STATUSES):
        with col:
            st.metric(status, counts.get(status, 0))

    fit_scores = [int(row["fit_score"]) for row in rows if row.get("fit_score") is not None]
    ats_scores = [
        int(row["ats_match_percent"])
        for row in rows
        if row.get("ats_match_percent") is not None
    ]

    total_col, fit_col, ats_col = st.columns(3)
    with total_col:
        st.metric("Total tracked", len(rows))
    with fit_col:
        st.metric("Average fit", f"{_average(fit_scores)}/100")
    with ats_col:
        st.metric("Average ATS", f"{_average(ats_scores)}%")

    st.markdown("**Recent applications**")
    if rows:
        st.dataframe(rows[:10], hide_index=True, width="stretch")
    else:
        st.caption("No applications saved yet.")


def _render_history(rows: list[dict]) -> None:
    st.subheader("Application History")
    search_col, status_col = st.columns([0.65, 0.35])
    with search_col:
        company_query = st.text_input("Search by company", key="history_company_search")
    with status_col:
        status_filter = st.selectbox("Search by status", ["All"] + STATUSES, key="history_status_search")

    filtered = []
    for row in rows:
        company_match = company_query.lower() in str(row.get("company", "")).lower()
        status_match = status_filter == "All" or row.get("status") == status_filter
        if company_match and status_match:
            filtered.append(row)

    if filtered:
        st.dataframe(filtered, hide_index=True, width="stretch")
    else:
        st.caption("No matching applications.")


def _render_profile_dashboard(profile: dict, profile_path: Path) -> None:
    st.subheader("Profile Completeness")
    validation = validate_profile(profile)
    enrichment = validation.get("enrichment", {})
    completeness = int(validation.get("completeness_percent", 0))

    inferred_project_skills = enrichment.get("inferred_skills_from_projects", [])
    inferred_experience_tech = enrichment.get("inferred_technologies_from_experience", [])

    metric_cols = st.columns(4)
    with metric_cols[0]:
        st.metric("Completeness", f"{completeness}%")
        st.progress(completeness / 100)
    with metric_cols[1]:
        st.metric("Missing fields", len(validation.get("missing_fields", [])))
    with metric_cols[2]:
        st.metric("Project skill inferences", len(inferred_project_skills))
    with metric_cols[3]:
        st.metric("Experience tech inferences", len(inferred_experience_tech))

    if st.button("Generate Enhanced Profile", type="primary"):
        try:
            generate_enhanced_profile_file(profile_path)
            st.success(f"Enhanced profile saved to {profile_path}. Missing information was left empty.")
        except (ProfileError, OSError, ValueError) as exc:
            st.error(f"Could not enhance profile: {exc}")

    st.caption("Enrichment is generated only from existing profile facts. It does not invent GPA, certifications, employment, or experience.")

    missing_col, additions_col = st.columns(2, gap="large")
    with missing_col:
        st.markdown("**Missing fields**")
        missing_fields = validation.get("missing_fields", [])
        if missing_fields:
            st.dataframe(
                [{"Missing field": field} for field in missing_fields],
                hide_index=True,
                width="stretch",
            )
        else:
            st.success("No required profile fields are missing.")

    with additions_col:
        st.markdown("**Recommended additions**")
        _render_bullets(validation.get("recommended_additions", []))

        st.markdown("**Strength areas**")
        _render_bullets(validation.get("strength_areas", []))

    warnings = validation.get("warnings", [])
    if warnings:
        st.markdown("**Accuracy warnings**")
        for warning in warnings:
            st.warning(warning)

    st.markdown("**Profile enrichment**")
    enrich_cols = st.columns(2, gap="large")
    with enrich_cols[0]:
        st.markdown("Project-derived skills")
        if inferred_project_skills:
            st.dataframe(inferred_project_skills, hide_index=True, width="stretch")
        else:
            st.caption("No project-derived skills inferred yet.")

        st.markdown("Suggested missing keywords")
        _render_bullets(enrichment.get("suggested_missing_keywords", []))

    with enrich_cols[1]:
        st.markdown("Experience-derived technologies")
        if inferred_experience_tech:
            st.dataframe(inferred_experience_tech, hide_index=True, width="stretch")
        else:
            st.caption("No experience-derived technologies inferred yet.")

        st.markdown("ATS improvements")
        _render_bullets(enrichment.get("ats_improvements", []))


def _render_outreach(result: dict | None) -> None:
    st.subheader("LinkedIn Outreach")
    if not result:
        st.caption("Generate a tailored draft first.")
        return

    outreach = result.get("linkedin_outreach", {})
    st.text_area(
        "Connection note",
        value=outreach.get("connection_note", ""),
        height=90,
        max_chars=300,
        key="linkedin_connection_note",
    )
    st.text_area(
        "Recruiter message",
        value=outreach.get("recruiter_message", ""),
        height=150,
        key="linkedin_recruiter_message",
    )
    st.text_area(
        "Follow-up message",
        value=outreach.get("follow_up_message", ""),
        height=130,
        key="linkedin_follow_up_message",
    )


def _render_interview_prep(result: dict | None) -> None:
    st.subheader("Interview Preparation")
    if not result:
        st.caption("Generate a tailored draft first.")
        return

    prep = result.get("interview_prep", {})
    technical_col, behavioral_col = st.columns(2, gap="large")
    with technical_col:
        st.markdown("**Likely technical questions**")
        _render_bullets(prep.get("technical_questions", []))
    with behavioral_col:
        st.markdown("**Likely behavioral questions**")
        _render_bullets(prep.get("behavioral_questions", []))


def _render_resume_intelligence(profile: dict, model: str) -> None:
    st.subheader("Resume Intelligence")
    st.caption("Compare your profile, current CV text, and the job description before deciding how strongly to apply.")

    if "resume_intelligence_cv_text" not in st.session_state:
        st.session_state["resume_intelligence_cv_text"] = build_profile_cv_text(profile)
    if "resume_intelligence_job_description" not in st.session_state:
        st.session_state["resume_intelligence_job_description"] = st.session_state.get("job_description", "")

    input_col, guidance_col = st.columns([0.62, 0.38], gap="large")
    with input_col:
        job_description = st.text_area(
            "Job description",
            height=260,
            key="resume_intelligence_job_description",
            placeholder="Paste the job description here, or use the same one from the Apply tab.",
        )
        cv_text = st.text_area(
            "Current CV text",
            height=260,
            key="resume_intelligence_cv_text",
            help="Defaults to a profile-derived CV snapshot. Replace with your actual CV text for better analysis.",
        )
        generate = st.button(
            "Generate Resume Intelligence",
            type="primary",
            disabled=not job_description.strip() or not cv_text.strip(),
        )

    with guidance_col:
        st.markdown("**Confidence rules**")
        _render_bullets(
            [
                "Never invent experience.",
                "Never add technologies not present in profile or CV.",
                "Never claim professional experience for academic projects.",
                "Always explain each recommendation.",
            ]
        )
        if st.button("Use Apply tab job description"):
            st.session_state["resume_intelligence_job_description"] = st.session_state.get("job_description", "")
            st.rerun()

    if generate:
        try:
            with st.spinner("Comparing profile, CV, and job description..."):
                analysis = generate_resume_intelligence(
                    profile,
                    cv_text=cv_text,
                    job_description=job_description,
                    model=model.strip() or None,
                )
            st.session_state["resume_intelligence_analysis"] = analysis
            st.success("Resume intelligence analysis generated.")
        except OpenAIConfigError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Resume intelligence failed: {exc}")

    analysis = st.session_state.get("resume_intelligence_analysis")
    if not analysis:
        return

    _render_resume_intelligence_result(analysis)

    markdown = analysis_to_markdown(analysis)
    export_col, pdf_col = st.columns(2)
    with export_col:
        st.download_button(
            "Download analysis as Markdown",
            data=markdown,
            file_name="resume-intelligence-analysis.md",
            mime="text/markdown",
        )
    with pdf_col:
        st.download_button(
            "Download analysis as PDF",
            data=markdown_to_pdf_bytes(markdown),
            file_name="resume-intelligence-analysis.pdf",
            mime="application/pdf",
        )


def _render_resume_intelligence_result(analysis: dict) -> None:
    scores = analysis.get("scores", {})
    recommendation = analysis.get("apply_recommendation", {})

    st.divider()
    st.markdown("**Match Scores**")
    score_cols = st.columns(5)
    score_labels = [
        ("Overall", "overall_match_score"),
        ("ATS", "ats_match_score"),
        ("Technical", "technical_match_score"),
        ("Experience", "experience_match_score"),
        ("Education", "education_match_score"),
    ]
    for col, (label, key) in zip(score_cols, score_labels):
        score = int(scores.get(key, 0))
        with col:
            st.metric(label, f"{score}/100")
            st.progress(score / 100)

    st.markdown("**Apply Recommendation**")
    st.info(f"{recommendation.get('label', 'Stretch Apply')}: {recommendation.get('reasoning', '')}")

    st.markdown("**Missing Keywords**")
    keyword_cols = st.columns(4)
    keyword_sections = [
        ("Present in profile", "present_in_profile"),
        ("Missing from profile", "missing_from_profile"),
        ("In projects, not CV", "mentioned_in_projects_but_not_cv"),
        ("In skills, not summary", "mentioned_in_skills_but_not_summary"),
    ]
    missing_keywords = analysis.get("missing_keywords", {})
    for col, (label, key) in zip(keyword_cols, keyword_sections):
        with col:
            st.markdown(f"**{label}**")
            _render_bullets(missing_keywords.get(key, []))

    st.markdown("**Project Prioritization**")
    projects = analysis.get("project_prioritization", [])
    if not projects:
        st.caption("No projects ranked yet.")
    for project in projects:
        with st.expander(f"{project.get('project_name', 'Project')} - {project.get('relevance_score', 0)}/100", expanded=True):
            st.write(project.get("why_it_matters", ""))
            st.markdown("Recommended bullet points")
            _render_bullets(project.get("recommended_bullet_points", []))

    st.markdown("**Skill Prioritization**")
    skill_cols = st.columns(3)
    skill_sections = [
        ("Skills to move higher", "skills_to_move_higher"),
        ("Skills to remove from focus", "skills_to_remove_from_focus"),
        ("Skills to emphasize", "skills_to_emphasize"),
    ]
    skill_prioritization = analysis.get("skill_prioritization", {})
    for col, (label, key) in zip(skill_cols, skill_sections):
        with col:
            st.markdown(f"**{label}**")
            items = skill_prioritization.get(key, [])
            if items:
                for item in items:
                    st.write(f"- **{item.get('skill', '')}:** {item.get('reason', '')}")
            else:
                st.caption("None listed.")

    summary = analysis.get("summary_rewriter", {})
    st.markdown("**Summary Rewriter**")
    summary_cols = st.columns(2, gap="large")
    with summary_cols[0]:
        st.text_area("Original summary", value=summary.get("original_summary", ""), height=140)
    with summary_cols[1]:
        st.text_area("Optimized summary", value=summary.get("optimized_summary", ""), height=140)
    st.markdown("**Summary reasoning**")
    st.write(summary.get("reasoning", ""))

    st.markdown("**Confidence Rules Applied**")
    _render_bullets(analysis.get("confidence_rules_applied", []))


def _render_job_discovery(profile: dict) -> None:
    st.subheader("Unified Job Discovery")
    st.caption("Find public graduate, junior, remote, Pakistan, UAE, and sponsorship-friendly software roles without storing credentials or auto-applying.")

    stats = job_dashboard_stats(JOB_DISCOVERY_DB_PATH)
    metric_cols = st.columns(6)
    metric_values = [
        ("Total Jobs Found", stats["total_jobs_found"]),
        ("New Today", stats["new_today"]),
        ("Applied", stats["applied"]),
        ("Interviews", stats["interviews"]),
        ("Offers", stats["offers"]),
        ("Highest Match", f"{stats['highest_match_score']}/100"),
    ]
    for col, (label, value) in zip(metric_cols, metric_values):
        with col:
            st.metric(label, value)

    with st.expander("Search Filters", expanded=True):
        row1 = st.columns(4)
        with row1[0]:
            role = st.text_input("Role", value=st.session_state.get("discovery_role", "software engineer"), key="discovery_role")
        with row1[1]:
            country = st.selectbox(
                "Country",
                ["Any", "UAE", "Pakistan", "Europe", "Remote", "United States", "United Kingdom", "Germany", "Canada"],
                key="discovery_country",
            )
        with row1[2]:
            city = st.text_input("City", key="discovery_city")
        with row1[3]:
            preset = st.selectbox("Ranking preset", ["Huzaifa Mode", "Default"], key="discovery_preset")

        row2 = st.columns(6)
        with row2[0]:
            remote = st.checkbox("Remote", key="discovery_remote")
        with row2[1]:
            hybrid = st.checkbox("Hybrid", key="discovery_hybrid")
        with row2[2]:
            visa = st.checkbox("Visa Sponsorship", key="discovery_visa")
        with row2[3]:
            graduate = st.checkbox("Graduate", value=True, key="discovery_graduate")
        with row2[4]:
            junior = st.checkbox("Junior", value=True, key="discovery_junior")
        with row2[5]:
            internship = st.checkbox("Internship", key="discovery_internship")

        max_exp = st.number_input("Maximum experience required", min_value=0, max_value=10, value=2, step=1)

        filters = SearchFilters(
            role=role,
            country=country,
            city=city,
            remote=remote,
            hybrid=hybrid,
            visa_sponsorship=visa,
            graduate=graduate,
            junior=junior,
            internship=internship,
            max_experience_years=int(max_exp),
            ranking_preset=preset,
        )

        action_cols = st.columns([0.28, 0.32, 0.4])
        with action_cols[0]:
            find_jobs = st.button("Find New Jobs", type="primary")
        with action_cols[1]:
            search_name = st.text_input("Saved search name", value="Huzaifa Mode Search")
        with action_cols[2]:
            if st.button("Save Search"):
                search_id = save_search(search_name, filters, JOB_DISCOVERY_DB_PATH)
                st.success(f"Saved search #{search_id}.")

    if find_jobs:
        with st.spinner("Searching public feeds and robots-allowed career pages..."):
            result = search_jobs(filters, profile, JOB_DISCOVERY_DB_PATH, JOB_SOURCE_CONFIG_PATH)
        st.session_state["job_discovery_last_result"] = result
        st.success(f"Found {len(result['jobs'])} matching jobs. New cached jobs: {result['new_count']}.")
        if result.get("failures"):
            with st.expander("Source failures handled gracefully"):
                _render_bullets(result["failures"])

    alerts = list_alerts(JOB_DISCOVERY_DB_PATH)
    if alerts:
        st.markdown("**Job Alerts**")
        for alert in alerts[:5]:
            st.info(alert["message"])

    jobs = list_discovered_jobs(JOB_DISCOVERY_DB_PATH, limit=300)
    st.markdown("**Unified Job Database**")
    export_cols = st.columns(3)
    with export_cols[0]:
        st.download_button("Export CSV", data=export_jobs_csv(jobs), file_name="job-discovery.csv", mime="text/csv")
    with export_cols[1]:
        st.download_button(
            "Export Excel",
            data=export_jobs_excel(jobs),
            file_name="job-discovery.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with export_cols[2]:
        st.download_button("Export JSON", data=export_jobs_json(jobs), file_name="job-discovery.json", mime="application/json")

    if jobs:
        table_rows = [
            {
                "ID": job["id"],
                "Company": job["company"],
                "Role": job["role"],
                "Location": job.get("location", ""),
                "Source": job["source"],
                "Overall": job.get("overall_match_score", 0),
                "ATS": job.get("ats_match_estimate", 0),
                "Rank": job.get("rank_score", 0),
                "Recommendation": job.get("apply_recommendation", ""),
                "Status": job.get("status", ""),
                "Apply URL": job.get("apply_url", ""),
            }
            for job in jobs
        ]
        st.dataframe(table_rows, hide_index=True, width="stretch")

        selected_label = st.selectbox(
            "Select job for actions",
            [
                f"#{job['id']} | {job['company']} | {job['role']} | rank {job.get('rank_score', 0)}"
                for job in jobs
            ],
        )
        selected_id = int(selected_label.split("|", 1)[0].replace("#", "").strip())
        selected_job = next(job for job in jobs if job["id"] == selected_id)

        detail_cols = st.columns([0.62, 0.38], gap="large")
        with detail_cols[0]:
            st.markdown(f"**{selected_job['role']}** at **{selected_job['company']}**")
            st.write(selected_job.get("location", ""))
            st.write(selected_job.get("apply_url", ""))
            st.markdown("**Missing skills**")
            _render_bullets(selected_job.get("missing_skills", []))
            st.markdown("**Missing keywords**")
            _render_bullets(selected_job.get("missing_keywords", []))
        with detail_cols[1]:
            st.metric("Overall Match", f"{selected_job.get('overall_match_score', 0)}/100")
            st.metric("ATS Estimate", f"{selected_job.get('ats_match_estimate', 0)}/100")
            st.metric("Smart Rank", f"{selected_job.get('rank_score', 0)}/100")
            st.info(f"Apply Recommendation: {selected_job.get('apply_recommendation', 'N/A')}")

        st.markdown("**Recommended projects to highlight**")
        projects = selected_job.get("recommended_projects", [])
        if projects:
            st.dataframe(projects, hide_index=True, width="stretch")
        else:
            st.caption("No project recommendations available.")

        action_cols = st.columns(len(JOB_STATUSES) - 1)
        action_statuses = ["Saved", "Applied", "Interviewing", "Rejected", "Offer"]
        for col, status in zip(action_cols, action_statuses):
            with col:
                if st.button(f"Mark {status}", key=f"job_status_{selected_id}_{status}"):
                    try:
                        tracker_id = set_discovered_job_status(selected_id, status, JOB_DISCOVERY_DB_PATH)
                        message = f"Job marked {status}."
                        if tracker_id:
                            message += f" Tracker row #{tracker_id} created."
                        st.success(message)
                    except ValueError as exc:
                        st.error(str(exc))
    else:
        st.caption("No jobs cached yet. Use Find New Jobs to refresh public feeds.")

    with st.expander("Official search links for sources without safe public feeds"):
        config = ensure_source_config(JOB_SOURCE_CONFIG_PATH)
        links = st.session_state.get("job_discovery_last_result", {}).get("search_links") or build_search_links(filters, config)
        for link in links:
            st.markdown(f"- [{link['source']}]({link['url']})")

    saved = list_saved_searches(JOB_DISCOVERY_DB_PATH)
    if saved:
        with st.expander("Saved searches"):
            st.dataframe(saved, hide_index=True, width="stretch")


def _render_analytics() -> None:
    st.subheader("Application Analytics")
    rows = load_analytics_rows(TRACKER_DB_PATH, JOB_DISCOVERY_DB_PATH)
    analytics = compute_application_analytics(rows)
    frames = analytics_to_dataframes(analytics)
    metrics = analytics["metrics"]

    metric_items = [
        ("Applications Sent", metrics["applications_sent"]),
        ("Interviews", metrics["interviews_received"]),
        ("Rejections", metrics["rejections"]),
        ("Offers", metrics["offers"]),
        ("Response Rate", f"{metrics['response_rate']}%"),
        ("Interview Rate", f"{metrics['interview_rate']}%"),
        ("Offer Rate", f"{metrics['offer_rate']}%"),
    ]
    for row_items in (metric_items[:4], metric_items[4:]):
        metric_cols = st.columns(len(row_items))
        for col, (label, value) in zip(metric_cols, row_items):
            with col:
                st.metric(label, value)

    chart_cols = st.columns(3, gap="large")
    with chart_cols[0]:
        st.markdown("**Applications over time**")
        over_time = frames["applications_over_time"]
        if not over_time.empty:
            st.bar_chart(over_time.set_index("month"))
        else:
            st.caption("No sent applications yet.")

    with chart_cols[1]:
        st.markdown("**Interview conversion funnel**")
        interview_funnel = frames["interview_funnel"]
        if not interview_funnel.empty:
            st.bar_chart(interview_funnel.set_index("stage"))
        else:
            st.caption("No funnel data yet.")

    with chart_cols[2]:
        st.markdown("**Offer conversion funnel**")
        offer_funnel = frames["offer_funnel"]
        if not offer_funnel.empty:
            st.bar_chart(offer_funnel.set_index("stage"))
        else:
            st.caption("No funnel data yet.")

    st.markdown("**Insights**")
    _render_bullets(analytics.get("insights", []))

    st.markdown("**Breakdowns**")
    country_tab, company_tab, role_tab, source_tab, month_tab = st.tabs(
        ["By country", "By company", "By role", "By source", "By month"]
    )
    breakdown_map = [
        (country_tab, "by_country"),
        (company_tab, "by_company"),
        (role_tab, "by_role"),
        (source_tab, "by_source"),
        (month_tab, "by_month"),
    ]
    for tab, frame_key in breakdown_map:
        with tab:
            frame = frames.get(frame_key)
            if frame is not None and not frame.empty:
                st.dataframe(frame, hide_index=True, width="stretch")
            else:
                st.caption("No data yet.")

    with st.expander("Application rows used for analytics"):
        applications = frames["applications"]
        if not applications.empty:
            st.dataframe(applications, hide_index=True, width="stretch")
        else:
            st.caption("No sent applications yet.")


def _render_settings(selected_model: str, profile_path_text: str, dark_mode: bool) -> None:
    st.subheader("Settings")
    st.caption("Runtime configuration, model selection, and environment validation.")

    issue_cols = st.columns(3)
    issues = SETTINGS.environment_issues()
    with issue_cols[0]:
        st.metric("OpenAI key", "Configured" if SETTINGS.openai_api_key_present else "Missing")
    with issue_cols[1]:
        st.metric("Response cache", "On" if SETTINGS.cache_enabled else "Off")
    with issue_cols[2]:
        st.metric("Retry attempts", SETTINGS.retry_attempts)

    st.markdown("**Current UI settings**")
    st.dataframe(
        [
            {"setting": "Selected model", "value": selected_model},
            {"setting": "Profile file", "value": profile_path_text},
            {"setting": "Dark mode", "value": str(dark_mode)},
        ],
        hide_index=True,
        width="stretch",
    )

    st.markdown("**Environment validation**")
    if issues:
        for issue in issues:
            message = f"{issue.name}: {issue.message}"
            if issue.severity == "error":
                st.error(message)
            else:
                st.warning(message)
    else:
        st.success("Environment looks ready.")

    st.markdown("**Resolved configuration**")
    st.dataframe(
        [{"setting": key, "value": str(value)} for key, value in SETTINGS.as_display_dict().items()],
        hide_index=True,
        width="stretch",
    )

    st.markdown("**Available models**")
    _render_bullets(list(SETTINGS.model_options))


def _save_current_application(
    result: dict | None,
    status: str,
    application_date: date,
    notes: str,
) -> int:
    meta = _job_meta()
    return save_application(
        job_title=meta["title"],
        company=meta["company"],
        location=meta["location"],
        apply_link=meta["apply_link"],
        status=status,
        application_date=application_date.isoformat(),
        fit_score=_fit_score(result),
        ats_match_percent=_ats_match(result),
        notes=notes,
        cv_tex_path=st.session_state.get("cv_tex_path", ""),
        cover_letter_tex_path=st.session_state.get("cover_letter_tex_path", ""),
    )


init_db(TRACKER_DB_PATH)

with st.sidebar:
    st.header("Setup")
    dark_mode = st.toggle("Dark mode", value=True)
    default_profile_path = DEFAULT_PROFILE_PATH if DEFAULT_PROFILE_PATH.exists() else SAMPLE_PROFILE_PATH
    profile_path_text = st.text_input("Profile file", value=str(default_profile_path))
    model_options = list(MODEL_OPTIONS)
    selected_index = model_options.index(DEFAULT_MODEL) if DEFAULT_MODEL in model_options else 0
    model_choice = st.selectbox("OpenAI model", model_options + ["Custom"], index=selected_index)
    if model_choice == "Custom":
        model = st.text_input("Custom OpenAI model", value=DEFAULT_MODEL)
    else:
        model = model_choice
    if not SETTINGS.openai_api_key_present:
        st.warning("OPENAI_API_KEY is missing. Generation tabs will show a graceful error until it is configured.")
    st.caption("Supports profile.json and profile.yaml. Set OPENAI_API_KEY in your environment or in a local .env file.")
    st.divider()
    st.caption("The app drafts materials only. It never submits applications.")

_apply_theme(dark_mode)

st.title("Job Application Co-Pilot")
st.caption("Tailor drafts from your own profile facts. Review everything before marking it ready.")

try:
    profile_path = Path(profile_path_text).expanduser()
    profile = load_profile(profile_path)
    st.sidebar.success(f"Loaded profile: {profile_display_name(profile)}")
except (ProfileError, ValueError, OSError) as exc:
    st.error(f"Profile error: {exc}")
    st.stop()

rows = list_applications(TRACKER_DB_PATH)
result = st.session_state.get("result")

apply_tab, profile_tab, discovery_tab, intelligence_tab, dashboard_tab, analytics_tab, outreach_tab, interview_tab, history_tab, settings_tab = st.tabs(
    [
        "Apply",
        "Profile",
        "Job Discovery",
        "Resume Intelligence",
        "Dashboard",
        "Analytics",
        "LinkedIn Outreach",
        "Interview Prep",
        "History",
        "Settings",
    ]
)

with apply_tab:
    left, right = st.columns([1.15, 0.85], gap="large")

    with left:
        st.subheader("1. Job Description")
        job_description = st.text_area(
            "Paste the job description",
            height=360,
            placeholder="Paste the full job post here, including title, company, requirements, and responsibilities.",
            key="job_description",
        )

        generate = st.button(
            "Generate tailored draft",
            type="primary",
            disabled=not job_description.strip(),
        )

        if generate:
            try:
                with st.spinner("Reading the job description and tailoring truthful drafts..."):
                    result = generate_tailoring(profile, job_description, model=model.strip() or None)
                st.session_state["result"] = result
                _set_job_defaults(result)
                st.success("Draft generated. Review the facts before exporting or marking ready.")
            except OpenAIConfigError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Generation failed: {exc}")

    with right:
        st.subheader("2. Job Details")
        st.text_input("Job title", key="job_title")
        st.text_input("Company", key="company")
        st.text_input("Location", key="location")
        st.text_input("Apply link", key="apply_link")
        application_date = st.date_input("Tracker date", value=date.today(), key="application_date")

    result = st.session_state.get("result")

    if result:
        st.divider()
        st.subheader("3. Fit and Strategy")
        _render_fit(result)

        st.divider()
        st.subheader("4. Review Generated Drafts")
        edited = _edited_result(result)

        checklist = result.get("approval_checklist", [])
        if checklist:
            st.markdown("**Model-suggested review checklist**")
            _render_bullets(checklist)

        st.divider()
        st.subheader("5. Export and Tracker")
        meta = _job_meta()

        export_col, tracker_col = st.columns(2, gap="large")
        with export_col:
            if st.button("Export CV and cover letter as .tex"):
                paths = write_exports(profile, edited, meta, EXPORT_DIR)
                st.session_state["cv_tex_path"] = str(paths["cv"])
                st.session_state["cover_letter_tex_path"] = str(paths["cover_letter"])
                st.success("Exported .tex files.")

            cv_path = st.session_state.get("cv_tex_path")
            cover_path = st.session_state.get("cover_letter_tex_path")
            if cv_path and Path(cv_path).exists():
                st.download_button(
                    "Download CV .tex",
                    data=Path(cv_path).read_text(encoding="utf-8"),
                    file_name=Path(cv_path).name,
                    mime="application/x-tex",
                )
            if cover_path and Path(cover_path).exists():
                st.download_button(
                    "Download cover letter .tex",
                    data=Path(cover_path).read_text(encoding="utf-8"),
                    file_name=Path(cover_path).name,
                    mime="application/x-tex",
                )

        with tracker_col:
            status = st.selectbox("Draft status", STATUSES, index=0)
            notes = st.text_area("Tracker notes", height=105)

            facts_ok = st.checkbox("I reviewed every generated claim against my profile.")
            no_inventions_ok = st.checkbox("I confirmed there are no invented internships, GPA, passport status, certifications, or authorization claims.")
            final_ok = st.checkbox("I approve this application package as ready to apply.")
            approval_ok = facts_ok and no_inventions_ok and final_ok

            if st.button("Save to tracker"):
                if status == "Ready to Apply" and not approval_ok:
                    st.error("Human approval is required before marking this ready to apply.")
                else:
                    try:
                        row_id = _save_current_application(result, status, application_date, notes)
                        st.success(f"Saved tracker row #{row_id}.")
                    except ValueError as exc:
                        st.error(str(exc))

            if st.button("Mark ready to apply", type="primary", disabled=not approval_ok):
                try:
                    row_id = _save_current_application(result, "Ready to Apply", application_date, notes)
                    st.success(f"Marked ready in tracker row #{row_id}.")
                except ValueError as exc:
                    st.error(str(exc))

with dashboard_tab:
    _render_dashboard(list_applications(TRACKER_DB_PATH))

with analytics_tab:
    _render_analytics()

with profile_tab:
    _render_profile_dashboard(profile, profile_path)

with discovery_tab:
    _render_job_discovery(profile)

with intelligence_tab:
    _render_resume_intelligence(profile, model)

with outreach_tab:
    _render_outreach(st.session_state.get("result"))

with interview_tab:
    _render_interview_prep(st.session_state.get("result"))

with history_tab:
    _render_history(list_applications(TRACKER_DB_PATH))

with settings_tab:
    _render_settings(model, profile_path_text, dark_mode)
