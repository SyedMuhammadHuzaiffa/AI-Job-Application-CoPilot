# Job Application Co-Pilot

A local Streamlit app for a fresh software engineering graduate who wants truthful, ATS-aware job application drafts. Paste a job description, load your profile from JSON or YAML, generate a fit score and ATS match, draft tailored CV bullets, draft a cover letter, prepare LinkedIn outreach, generate interview prep, export LaTeX files, and save the opportunity to a SQLite tracker.

The app does not submit applications. A human approval checklist is required before anything can be marked `Ready to Apply`.

The codebase is organized as a production-ready local app: typed settings, service-style modules, dependency-injected LLM clients, response caching, retries, logging, SQLite repositories, and pytest coverage.

## Features

- Paste a job description and generate a fit score plus ATS match percentage.
- Load candidate facts from `sample_profile.json` or your own `profile.json` / `profile.yaml`.
- Get strengths, skill gaps, recommended learning topics, and application strategy.
- Generate tailored CV bullets with a source field for each claim.
- Generate a concise tailored cover letter.
- Generate concise answers for common application questions.
- Generate LinkedIn connection notes, recruiter messages, and follow-ups.
- Generate likely technical and behavioral interview questions.
- Run Resume Intelligence analysis before applying:
  - overall, ATS, technical, experience, and education match scores
  - keyword gap categories
  - ranked project prioritization
  - skill prioritization
  - truthful summary rewrite
  - apply recommendation
- Export Resume Intelligence analysis as Markdown or PDF.
- Export CV and cover letter as `.tex` files in `exports/`.
- Track job title, company, location, apply link, status, date, fit score, ATS match, and export paths in SQLite.
- Use dashboard counters for `Applied`, `Interviewing`, `Rejected`, `Offer`, and `Awaiting response`.
- Use application analytics for response, interview, and offer rates with breakdowns by country, company, role, source, and month.
- Review analytics charts for applications over time, interview conversion, and offer conversion.
- Get analytics insights for best-performing sources, interview-producing roles, and ATS score patterns.
- Search application history by company and status.
- Use dark mode by default, with a sidebar toggle.
- Use a Settings tab for environment validation, model selection, cache status, retry settings, and resolved paths.
- Migrate simple profiles into the advanced schema from the `Profile` tab.
- Show profile completeness, missing fields, recommended additions, and factual enrichment suggestions.
- Discover jobs from public feeds, configured Greenhouse/Lever boards, robots-allowed career pages, and official search links.
- Rank discovered jobs with `Huzaifa Mode`: UAE sponsorship, remote software roles, Pakistan software roles, then Europe sponsorship.
- Save searches and show local job alerts when newly cached jobs match.
- Export discovered jobs as CSV, Excel, or JSON.
- Send discovered jobs to the application tracker as Saved, Applied, Interviewing, Rejected, or Offer.
- Require human approval before marking an application `Ready to Apply`.

## Project Structure

```text
.
├── app.py
├── requirements.txt
├── pyproject.toml
├── profile.json
├── sample_profile.json
├── sample_profile_advanced.json
├── .env.example
├── .streamlit/
│   └── config.toml
├── data/
│   ├── .gitkeep
│   └── job_sources.json
├── docs/
│   ├── api.md
│   ├── architecture.md
│   ├── developer_guide.md
│   └── user_guide.md
├── exports/
│   └── .gitkeep
├── templates/
│   ├── cv_template.tex
│   └── cover_letter_template.tex
└── src/
    └── job_copilot/
        ├── __init__.py
        ├── application_analytics.py
        ├── cache.py
        ├── config.py
        ├── exceptions.py
        ├── job_discovery.py
        ├── latex.py
        ├── llm.py
        ├── llm_client.py
        ├── logging_config.py
        ├── models.py
        ├── profile.py
        ├── prompts.py
        ├── resume_intelligence.py
        ├── settings.py
        └── tracker.py
└── tests/
    └── ...
```

## Setup

Use Python 3.10 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set:

```bash
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Optional configuration:

```bash
JOB_COPILOT_MODEL_OPTIONS=gpt-4.1-mini,gpt-4.1,gpt-4o-mini
JOB_COPILOT_CACHE_RESPONSES=true
JOB_COPILOT_RETRY_ATTEMPTS=3
JOB_COPILOT_REQUEST_TIMEOUT_SECONDS=30
JOB_COPILOT_LOG_LEVEL=INFO
```

Run the app:

```bash
streamlit run app.py
```

Run tests with coverage:

```bash
pytest
```

The project enforces 80% coverage through `pyproject.toml`.

## Documentation

- [Architecture](docs/architecture.md)
- [API Documentation](docs/api.md)
- [Developer Guide](docs/developer_guide.md)
- [User Guide](docs/user_guide.md)

## Production Readiness

- `AppSettings` validates environment, paths, cache behavior, retry settings, and model options.
- `OpenAIChatClient` centralizes OpenAI calls with response caching, retry backoff, JSON-mode fallback, logging, and dependency injection for tests.
- `TrackerRepository` validates tracker input and keeps compatibility wrappers for existing UI code.
- SQLite indexes improve dashboard, analytics, history, and job discovery queries.
- Job discovery handles source failures gracefully and uses concurrent company-page fetching where safe.
- Tests mock OpenAI and network fetches; no live API calls are required for the suite.

## Profile

The app supports both `profile.json` and `profile.yaml`. It now normalizes profiles into an enhanced schema with:

- personal information
- education
- categorized skills
- experience
- projects
- certifications
- career preferences
- career goals
- additional factual constraints
- profile enrichment suggestions

Start from `sample_profile_advanced.json` for the full schema, or use the existing `profile.json` and open the `Profile` tab. Click `Generate Enhanced Profile` to migrate the selected profile file automatically.

The migration preserves existing facts and leaves missing fields as `null` or empty lists. It does not invent experience, certifications, CGPA, work authorization, passport status, or employment history.

Keep the profile factual. If GPA, passport status, work authorization, internships, certifications, or salary expectations are not known or should not be used, leave them as `null` or an empty list.

### Profile Completeness

The `Profile` tab shows:

- completeness percentage
- missing fields
- recommended additions
- strength areas
- project-derived skill inferences
- experience-derived technology inferences
- suggested keywords and ATS improvements

Inferred skills are derived only from technologies already listed in your projects or experience. Treat them as review suggestions, not automatic claims.

The model prompt is strict, but you should still review every output. The app is designed for strong wording, not invented experience.

## Resume Intelligence

Use the `Resume Intelligence` tab before applying. Paste the job description and review the profile-derived CV text, or replace it with your actual CV text.

The engine compares:

- enhanced profile facts
- current CV text
- job description

It returns:

- Overall Match Score
- ATS Match Score
- Technical Match Score
- Experience Match Score
- Education Match Score
- missing keyword categories
- ranked project recommendations
- skill focus recommendations
- original and optimized summary
- apply recommendation: `Strong Apply`, `Apply`, `Stretch Apply`, or `Low Probability`

Exports are available as `.md` and `.pdf`. The PDF export is generated locally from the Markdown analysis.

## Job Discovery

Use the `Job Discovery` tab to find and rank graduate, junior, trainee, entry-level, internship, remote, Pakistan, UAE, and sponsorship-friendly software roles.

The engine stores a local cache in `data/job_discovery.db` with:

- company
- role
- location
- salary, when available
- source
- apply URL
- date found
- sponsorship availability
- remote and hybrid availability
- profile match scores
- missing skills and keywords
- recommended projects to highlight
- apply recommendation
- tracker status

Supported source strategy:

- RemoteOK is queried through its public API.
- Greenhouse and Lever are supported through public job-board APIs when company board tokens/slugs are configured in `data/job_sources.json`.
- Company career pages are fetched only when `robots.txt` allows the local job-discovery user agent.
- Wellfound, Y Combinator Jobs, Welcome to the Jungle, LinkedIn, Indeed, Glassdoor, Rozee.pk, Mustakbil, BrightSpyre, CareerOkay, Jobee, HiringCafe, Bayt, GulfTalent, Naukrigulf, Dubizzle Jobs, Indeed UAE, and LinkedIn UAE are exposed as official search links unless a safe public feed is configured.

This keeps the app policy-aware: it does not store credentials, does not auto-apply, and gracefully reports source failures.

### Huzaifa Mode

`Huzaifa Mode` boosts jobs in this priority order:

1. UAE roles with visa sponsorship
2. Remote software jobs
3. Pakistan software jobs
4. Europe roles with sponsorship

It does not hide other jobs; it changes ranking so the best-fit personal opportunities rise to the top.

## Application Analytics

Use the `Analytics` tab after logging applications and outcomes in the tracker. The analytics module counts only submitted/outcome statuses as sent applications: `Applied`, `Awaiting response`, `Interviewing`, `Rejected`, and `Offer`.

It tracks:

- applications sent
- interviews received
- rejections
- offers
- response rate
- interview rate
- offer rate

Breakdowns are available by country, company, role, source, and month. The tab also shows applications over time, interview conversion, and offer conversion charts.

When tracker rows came from Job Discovery, analytics enriches them with source, country, match, and ATS data from `data/job_discovery.db`. For manually entered rows, it infers source from notes or apply links where possible.

Insights highlight which sources perform best, which roles produce interviews, and whether higher ATS scores are correlating with interviews. Treat the correlation note as directional until you have enough tracked applications for a reliable pattern.

## LaTeX Exports

Exported files are written to `exports/`. You can compile them with any LaTeX distribution, for example:

```bash
pdflatex exports/company-role-date-cv.tex
pdflatex exports/company-role-date-cover-letter.tex
```

## Tracker

The tracker database is created automatically at `data/applications.db`. It stores:

- job title
- company
- location
- apply link
- status
- date
- fit score
- ATS match percent
- notes
- exported CV and cover letter paths

Use `Needs Review` or `Draft` while editing. Use `Applied`, `Awaiting response`, `Interviewing`, `Rejected`, or `Offer` after submission. The app blocks `Ready to Apply` until you confirm the human approval checklist.

## Safety Rules Built In

- No invented internships, GPA, certifications, passport status, or work authorization.
- No auto-submission.
- Concise professional outputs.
- ATS keyword optimization only where truthful.
- Human approval before final readiness.
