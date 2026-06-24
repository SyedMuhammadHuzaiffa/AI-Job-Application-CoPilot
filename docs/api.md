# API Documentation

This project exposes Python module APIs rather than an HTTP API.

## Settings

`job_copilot.settings.load_settings() -> AppSettings`

Resolves environment variables, paths, model options, retry settings, and cache settings.

Common environment variables:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `JOB_COPILOT_MODEL_OPTIONS`
- `JOB_COPILOT_DATA_DIR`
- `JOB_COPILOT_EXPORT_DIR`
- `JOB_COPILOT_TRACKER_DB_PATH`
- `JOB_COPILOT_JOB_DISCOVERY_DB_PATH`
- `JOB_COPILOT_CACHE_RESPONSES`
- `JOB_COPILOT_RETRY_ATTEMPTS`
- `JOB_COPILOT_REQUEST_TIMEOUT_SECONDS`
- `JOB_COPILOT_LOG_LEVEL`

## LLM Generation

`job_copilot.llm.generate_tailoring(profile, job_description, model=None, temperature=0.2, chat_client=None)`

Returns normalized tailored application output:

- job metadata
- fit score and ATS match
- strengths, gaps, learning topics, and strategy
- tailored CV bullets
- cover letter body
- application answers
- LinkedIn outreach
- interview prep
- approval checklist

Pass a test double through `chat_client` to mock OpenAI responses.

`job_copilot.resume_intelligence.generate_resume_intelligence(profile, cv_text, job_description, model=None, temperature=0.1, chat_client=None)`

Returns normalized resume intelligence analysis with match scores, keyword categories, project prioritization, skill prioritization, summary rewrite, and apply recommendation.

## Tracker

`TrackerRepository(db_path).save(ApplicationCreate(...)) -> int`

Validates and inserts one tracker row.

`TrackerRepository(db_path).list() -> list[ApplicationRecord]`

Returns typed tracker records ordered by newest update.

Compatibility wrappers remain available:

- `init_db(db_path)`
- `save_application(...)`
- `list_applications(db_path)`

## Job Discovery

`search_jobs(filters, profile, db_path, config_path) -> dict`

Searches configured safe feeds, ranks jobs, deduplicates by fingerprint, writes to SQLite, and returns jobs, failures, search links, and new job count.

`match_job_to_profile(job, profile) -> dict`

Returns match scores, missing skills, missing keywords, recommended projects, and apply recommendation.

`set_discovered_job_status(job_id, status, db_path, also_save_tracker=True)`

Updates discovered job status and optionally imports it into the tracker.

## Analytics

`load_analytics_rows(tracker_db_path, discovery_db_path) -> list[dict]`

Loads tracker rows and enriches them with discovery source, country, fit, and ATS data where possible.

`compute_application_analytics(rows) -> dict`

Returns metrics, breakdowns, charts, insights, and rows.

`analytics_to_dataframes(analytics) -> dict[str, pandas.DataFrame]`

Returns Streamlit-ready chart and table frames.
