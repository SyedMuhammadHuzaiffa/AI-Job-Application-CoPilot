import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml


PROFILE_VERSION = "2.0"

PERSONAL_FIELDS = ["name", "email", "phone", "location", "github", "linkedin"]
EDUCATION_FIELDS = [
    "degree",
    "university",
    "campus",
    "graduation_year",
    "cgpa",
    "relevant_coursework",
]
SKILL_CATEGORIES = [
    "languages",
    "frontend",
    "backend",
    "databases",
    "cloud",
    "devops",
    "blockchain",
    "ai_tools",
    "testing",
    "tools",
]
EXPERIENCE_FIELDS = [
    "title",
    "company",
    "start_date",
    "end_date",
    "location",
    "achievements",
    "technologies_used",
]
PROJECT_FIELDS = [
    "name",
    "type",
    "description",
    "technologies",
    "highlights",
    "github_link",
    "live_link",
    "complexity_level",
]
CERTIFICATION_FIELDS = ["name", "issuer", "year", "status"]
CAREER_PREFERENCE_FIELDS = [
    "preferred_roles",
    "preferred_locations",
    "remote_preference",
    "relocation_willingness",
    "industries_of_interest",
]
CAREER_GOAL_FIELDS = ["short_term_goals", "long_term_goals"]

MISSING_SENTINELS = {"", "none", "not specified", "n/a", "na", "unknown", "null"}

TECH_CATEGORY_HINTS = {
    "ai_tools": {
        "openai",
        "chatgpt",
        "langchain",
        "llm",
        "machine learning",
        "pandas",
        "matplotlib",
        "scikit",
        "tensorflow",
        "pytorch",
    },
    "backend": {
        "node",
        "node.js",
        "express",
        "express.js",
        "fastapi",
        "django",
        "flask",
        "rest",
        "rest api",
        "rest apis",
        "api",
        "apis",
        "spring",
        "graphql",
    },
    "blockchain": {
        "solidity",
        "ethereum",
        "web3",
        "ipfs",
        "smart contract",
        "smart contracts",
        "merkle",
        "merkle trees",
        "blockchain",
    },
    "cloud": {
        "aws",
        "azure",
        "gcp",
        "firebase",
        "vercel",
        "netlify",
        "cloudflare",
        "s3",
    },
    "databases": {
        "sql",
        "sqlite",
        "postgres",
        "postgresql",
        "mysql",
        "mongodb",
        "mongo",
        "redis",
        "supabase",
    },
    "devops": {
        "docker",
        "kubernetes",
        "linux",
        "ci",
        "ci/cd",
        "github actions",
        "hosting",
        "domains",
        "nginx",
    },
    "frontend": {
        "react",
        "next",
        "next.js",
        "vue",
        "angular",
        "html",
        "css",
        "tailwind",
        "bootstrap",
        "streamlit",
        "responsive ui",
        "responsive",
        "ui/ux",
    },
    "languages": {
        "python",
        "javascript",
        "typescript",
        "java",
        "c++",
        "c#",
        "c",
        "go",
        "rust",
        "solidity",
        "sql",
    },
    "testing": {
        "pytest",
        "jest",
        "unit testing",
        "integration testing",
        "testing",
        "selenium",
        "playwright",
    },
    "tools": {
        "git",
        "github",
        "docker",
        "linux",
        "postman",
        "figma",
        "rest apis",
        "ipfs",
        "seo",
    },
}

CANONICAL_TERM_LABELS = {
    "ci": "CI",
    "ci/cd": "CI/CD",
    "domains": "Domain management",
    "hosting": "Hosting",
    "ipfs": "IPFS",
    "merkle": "Merkle Trees",
    "node": "Node.js",
    "postgres": "PostgreSQL",
    "rest": "REST APIs",
    "rest api": "REST APIs",
    "rest apis": "REST APIs",
    "responsive": "Responsive UI",
    "seo": "SEO",
    "ui/ux": "UI/UX",
}


class ProfileError(ValueError):
    """Raised when the candidate profile cannot be loaded safely."""


def empty_enhanced_profile() -> dict[str, Any]:
    return {
        "profile_version": PROFILE_VERSION,
        "personal_information": {field: None for field in PERSONAL_FIELDS},
        "education": [],
        "skills": {category: [] for category in SKILL_CATEGORIES},
        "experience": [],
        "projects": [],
        "certifications": [],
        "career_preferences": {
            field: [] if field in {"preferred_roles", "preferred_locations", "industries_of_interest"} else None
            for field in CAREER_PREFERENCE_FIELDS
        },
        "career_goals": {
            "short_term_goals": [],
            "long_term_goals": [],
        },
        "additional_information": {
            "summary": None,
            "portfolio": None,
            "work_authorization": None,
            "passport_status": None,
            "availability": None,
            "salary_expectations": None,
            "awards": [],
            "truthfulness_constraints": [],
            "unmapped_legacy_fields": {},
        },
        "profile_enrichment": {
            "inferred_skills_from_projects": [],
            "inferred_technologies_from_experience": [],
            "suggested_missing_keywords": [],
            "ats_improvements": [],
            "factual_accuracy_notes": [
                "Generated enrichment is advisory. Do not present suggestions as facts unless the candidate confirms them."
            ],
        },
    }


def read_profile_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ProfileError(f"Profile file not found: {path}")

    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")

    if suffix == ".json":
        data = json.loads(raw)
    elif suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(raw)
    else:
        raise ProfileError("Profile must be a .json, .yaml, or .yml file.")

    if not isinstance(data, dict):
        raise ProfileError("Profile root must be an object.")
    return data


def write_profile_file(path: Path, profile: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".json":
        path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif suffix in {".yaml", ".yml"}:
        path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True), encoding="utf-8")
    else:
        raise ProfileError("Profile must be saved as .json, .yaml, or .yml.")


def load_profile(path: Path) -> dict[str, Any]:
    """Load a JSON or YAML candidate profile and normalize it to the enhanced schema."""
    data = read_profile_file(path)
    profile = enhance_profile(data)

    name = profile.get("personal_information", {}).get("name")
    if _is_missing(name):
        raise ProfileError("Profile must include a candidate name.")

    return profile


def generate_enhanced_profile_file(path: Path) -> dict[str, Any]:
    """Read, enhance, and save a profile file while preserving existing factual data."""
    raw = read_profile_file(path)
    enhanced = enhance_profile(raw)
    write_profile_file(path, enhanced)
    return enhanced


def profile_display_name(profile: dict[str, Any]) -> str:
    return str(profile.get("personal_information", {}).get("name") or "Unnamed candidate")


def profile_to_prompt_text(profile: dict[str, Any]) -> str:
    """Serialize the profile for model input while keeping all facts explicit."""
    return json.dumps(enhance_profile(profile), indent=2, ensure_ascii=False)


def enhance_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Return an enhanced profile without inventing unprovided facts."""
    if _looks_enhanced(data):
        profile = _merge_enhanced_profile(data)
    else:
        profile = _migrate_legacy_profile(data)

    _apply_profile_enrichment(profile)
    return profile


def validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    enhanced = enhance_profile(profile)
    missing_fields: list[str] = []
    warnings: list[str] = []
    completed = 0
    total = 0

    def check(label: str, value: Any) -> None:
        nonlocal completed, total
        total += 1
        if _is_missing(value):
            missing_fields.append(label)
        else:
            completed += 1

    personal = enhanced.get("personal_information", {})
    for field in PERSONAL_FIELDS:
        check(f"personal_information.{field}", personal.get(field))

    education = enhanced.get("education", [])
    if education:
        first_education = education[0] if isinstance(education[0], dict) else {}
    else:
        first_education = {}
        warnings.append("Add education details so CV and cover letter drafts can cite your degree accurately.")
    for field in EDUCATION_FIELDS:
        check(f"education[0].{field}", first_education.get(field))

    skills = enhanced.get("skills", {})
    for category in SKILL_CATEGORIES:
        check(f"skills.{category}", skills.get(category))

    projects = enhanced.get("projects", [])
    if not projects:
        missing_fields.append("projects")
        warnings.append("Add at least one project with technologies and measurable highlights.")
    else:
        for index, project in enumerate(projects, start=1):
            if not isinstance(project, dict):
                continue
            for field in PROJECT_FIELDS:
                if _is_missing(project.get(field)):
                    missing_fields.append(f"projects[{index}].{field}")

    for index, experience in enumerate(enhanced.get("experience", []), start=1):
        if not isinstance(experience, dict):
            continue
        for field in EXPERIENCE_FIELDS:
            if _is_missing(experience.get(field)):
                missing_fields.append(f"experience[{index}].{field}")

    for index, certification in enumerate(enhanced.get("certifications", []), start=1):
        if not isinstance(certification, dict):
            continue
        for field in CERTIFICATION_FIELDS:
            if _is_missing(certification.get(field)):
                missing_fields.append(f"certifications[{index}].{field}")

    career_preferences = enhanced.get("career_preferences", {})
    for field in CAREER_PREFERENCE_FIELDS:
        check(f"career_preferences.{field}", career_preferences.get(field))

    career_goals = enhanced.get("career_goals", {})
    for field in CAREER_GOAL_FIELDS:
        check(f"career_goals.{field}", career_goals.get(field))

    if not enhanced.get("experience"):
        warnings.append("No experience is listed. That is okay for a fresh graduate; do not invent internships or employment.")
    if not enhanced.get("certifications"):
        warnings.append("No certifications are listed. Leave this empty unless you have real certifications.")
    if _is_missing(first_education.get("cgpa")):
        warnings.append("CGPA is missing. Leave it null unless you want it used in applications.")

    recommended_additions = _recommended_additions(enhanced, missing_fields)
    strength_areas = _strength_areas(enhanced)
    completeness = round((completed / total) * 100) if total else 0

    return {
        "profile": enhanced,
        "completeness_percent": completeness,
        "missing_fields": _dedupe(missing_fields),
        "warnings": _dedupe(warnings),
        "recommended_additions": recommended_additions,
        "strength_areas": strength_areas,
        "enrichment": enhanced.get("profile_enrichment", {}),
    }


def _looks_enhanced(data: dict[str, Any]) -> bool:
    return "personal_information" in data or data.get("profile_version") == PROFILE_VERSION


def _merge_enhanced_profile(data: dict[str, Any]) -> dict[str, Any]:
    profile = empty_enhanced_profile()
    for key, value in data.items():
        if key in profile and isinstance(profile[key], dict) and isinstance(value, dict):
            merged = copy.deepcopy(profile[key])
            merged.update(value)
            profile[key] = merged
        else:
            profile[key] = copy.deepcopy(value)

    profile["profile_version"] = PROFILE_VERSION
    profile["personal_information"] = _merge_dict_fields(
        profile.get("personal_information", {}), PERSONAL_FIELDS
    )
    profile["skills"] = _merge_skill_categories(profile.get("skills", {}))
    profile["education"] = [_normalize_education(item) for item in _as_list(profile.get("education"))]
    profile["experience"] = [_normalize_experience(item) for item in _as_list(profile.get("experience"))]
    profile["projects"] = [_normalize_project(item) for item in _as_list(profile.get("projects"))]
    profile["certifications"] = [
        _normalize_certification(item) for item in _as_list(profile.get("certifications"))
    ]
    profile["career_preferences"] = _normalize_career_preferences(profile.get("career_preferences", {}))
    profile["career_goals"] = _normalize_career_goals(profile.get("career_goals", {}))

    additional = empty_enhanced_profile()["additional_information"]
    if isinstance(profile.get("additional_information"), dict):
        additional.update(profile["additional_information"])
    profile["additional_information"] = additional

    enrichment = empty_enhanced_profile()["profile_enrichment"]
    if isinstance(profile.get("profile_enrichment"), dict):
        enrichment.update(profile["profile_enrichment"])
    profile["profile_enrichment"] = enrichment
    return profile


def _migrate_legacy_profile(data: dict[str, Any]) -> dict[str, Any]:
    profile = empty_enhanced_profile()
    basics = data.get("basics", {}) if isinstance(data.get("basics"), dict) else {}

    profile["personal_information"] = {
        "name": _first_present(data.get("name"), basics.get("name")),
        "email": _first_present(data.get("email"), basics.get("email")),
        "phone": _first_present(data.get("phone"), basics.get("phone")),
        "location": _first_present(data.get("location"), basics.get("location")),
        "github": _first_present(data.get("github"), basics.get("github")),
        "linkedin": _first_present(data.get("linkedin"), basics.get("linkedin")),
    }

    profile["education"] = _migrate_education(data)
    profile["skills"] = _migrate_skills(data.get("skills", {}))
    profile["experience"] = [_normalize_experience(item) for item in _as_list(data.get("experience"))]
    profile["projects"] = [_normalize_project(item) for item in _as_list(data.get("projects"))]
    profile["certifications"] = [
        _normalize_certification(item) for item in _as_list(data.get("certifications"))
    ]
    profile["career_preferences"] = _migrate_career_preferences(data)
    profile["career_goals"] = _migrate_career_goals(data)
    profile["additional_information"] = _migrate_additional_information(data, basics)

    unmapped = _unmapped_legacy_fields(
        data,
        {
            "name",
            "email",
            "phone",
            "location",
            "github",
            "linkedin",
            "degree",
            "university",
            "campus",
            "graduation_year",
            "cgpa",
            "gpa",
            "relevant_coursework",
            "basics",
            "education",
            "skills",
            "experience",
            "projects",
            "certifications",
            "application_preferences",
            "career_preferences",
            "career_goals",
            "summary",
            "awards",
            "truthfulness_constraints",
        },
    )
    profile["additional_information"]["unmapped_legacy_fields"] = unmapped
    return profile


def _migrate_education(data: dict[str, Any]) -> list[dict[str, Any]]:
    legacy_education = data.get("education")
    if isinstance(legacy_education, list) and legacy_education:
        return [_normalize_education(item) for item in legacy_education if isinstance(item, dict)]
    if isinstance(legacy_education, dict):
        return [_normalize_education(legacy_education)]

    if any(data.get(field) is not None for field in ("degree", "university", "graduation_year", "cgpa", "gpa")):
        return [
            {
                "degree": data.get("degree"),
                "university": data.get("university"),
                "campus": data.get("campus"),
                "graduation_year": data.get("graduation_year"),
                "cgpa": _first_present(data.get("cgpa"), data.get("gpa")),
                "relevant_coursework": _as_list(data.get("relevant_coursework")),
            }
        ]
    return []


def _migrate_skills(raw_skills: Any) -> dict[str, list[str]]:
    skills = {category: [] for category in SKILL_CATEGORIES}
    if isinstance(raw_skills, list):
        for skill in raw_skills:
            _add_skill(skills, skill)
        return skills

    if not isinstance(raw_skills, dict):
        return skills

    direct_keys = {
        "languages": "languages",
        "frontend": "frontend",
        "backend": "backend",
        "databases": "databases",
        "cloud": "cloud",
        "devops": "devops",
        "blockchain": "blockchain",
        "ai_tools": "ai_tools",
        "testing": "testing",
        "tools": "tools",
    }
    for raw_key, target_key in direct_keys.items():
        for item in _as_list(raw_skills.get(raw_key)):
            _append_unique(skills[target_key], item)

    for framework in _as_list(raw_skills.get("frameworks")):
        _add_skill(skills, framework)
    for practice in _as_list(raw_skills.get("practices")):
        _add_skill(skills, practice)

    return skills


def _migrate_career_preferences(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("career_preferences")
    if not isinstance(raw, dict):
        raw = data.get("application_preferences", {}) if isinstance(data.get("application_preferences"), dict) else {}

    legacy_goals = data.get("career_goals") if isinstance(data.get("career_goals"), list) else []

    return {
        "preferred_roles": _as_list(_first_present(raw.get("preferred_roles"), raw.get("target_roles"), legacy_goals)),
        "preferred_locations": _as_list(raw.get("preferred_locations")),
        "remote_preference": raw.get("remote_preference"),
        "relocation_willingness": raw.get("relocation_willingness"),
        "industries_of_interest": _as_list(raw.get("industries_of_interest")),
    }


def _migrate_career_goals(data: dict[str, Any]) -> dict[str, list[str]]:
    raw = data.get("career_goals", {})
    if isinstance(raw, dict):
        return _normalize_career_goals(raw)
    if isinstance(raw, list):
        return {
            "short_term_goals": _as_list(raw),
            "long_term_goals": [],
        }
    return {"short_term_goals": [], "long_term_goals": []}


def _migrate_additional_information(data: dict[str, Any], basics: dict[str, Any]) -> dict[str, Any]:
    raw_preferences = data.get("application_preferences", {})
    if not isinstance(raw_preferences, dict):
        raw_preferences = {}
    return {
        "summary": data.get("summary"),
        "portfolio": _first_present(data.get("portfolio"), basics.get("portfolio")),
        "work_authorization": _first_present(data.get("work_authorization"), basics.get("work_authorization")),
        "passport_status": _first_present(data.get("passport_status"), basics.get("passport_status")),
        "availability": _first_present(data.get("availability"), raw_preferences.get("availability")),
        "salary_expectations": _first_present(
            data.get("salary_expectations"), raw_preferences.get("salary_expectations")
        ),
        "awards": _as_list(data.get("awards")),
        "truthfulness_constraints": _as_list(data.get("truthfulness_constraints")),
        "unmapped_legacy_fields": {},
    }


def _normalize_education(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    dates = item.get("dates")
    return {
        "degree": item.get("degree"),
        "university": _first_present(item.get("university"), item.get("school")),
        "campus": _first_present(item.get("campus"), item.get("location")),
        "graduation_year": _first_present(item.get("graduation_year"), _extract_last_year(dates)),
        "cgpa": _first_present(item.get("cgpa"), item.get("gpa")),
        "relevant_coursework": _as_list(_first_present(item.get("relevant_coursework"), item.get("details"))),
    }


def _normalize_experience(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    return {
        "title": item.get("title"),
        "company": item.get("company"),
        "start_date": _first_present(item.get("start_date"), item.get("start")),
        "end_date": _first_present(item.get("end_date"), item.get("end")),
        "location": item.get("location"),
        "achievements": _as_list(_first_present(item.get("achievements"), item.get("bullets"))),
        "technologies_used": _as_list(_first_present(item.get("technologies_used"), item.get("technologies"), item.get("tech"))),
    }


def _normalize_project(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    return {
        "name": item.get("name"),
        "type": item.get("type"),
        "description": item.get("description"),
        "technologies": _as_list(_first_present(item.get("technologies"), item.get("tech"))),
        "highlights": _as_list(_first_present(item.get("highlights"), item.get("bullets"))),
        "github_link": _first_present(item.get("github_link"), item.get("github"), item.get("link")),
        "live_link": item.get("live_link"),
        "complexity_level": item.get("complexity_level"),
    }


def _normalize_certification(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {"name": item}
    return {
        "name": item.get("name"),
        "issuer": item.get("issuer"),
        "year": item.get("year"),
        "status": item.get("status"),
    }


def _normalize_career_preferences(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    return {
        "preferred_roles": _as_list(item.get("preferred_roles")),
        "preferred_locations": _as_list(item.get("preferred_locations")),
        "remote_preference": item.get("remote_preference"),
        "relocation_willingness": item.get("relocation_willingness"),
        "industries_of_interest": _as_list(item.get("industries_of_interest")),
    }


def _normalize_career_goals(item: Any) -> dict[str, list[str]]:
    if not isinstance(item, dict):
        item = {}
    return {
        "short_term_goals": _as_list(item.get("short_term_goals")),
        "long_term_goals": _as_list(item.get("long_term_goals")),
    }


def _merge_dict_fields(raw: Any, fields: list[str]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    return {field: raw.get(field) for field in fields}


def _merge_skill_categories(raw: Any) -> dict[str, list[str]]:
    skills = {category: [] for category in SKILL_CATEGORIES}
    if not isinstance(raw, dict):
        return skills
    for category in SKILL_CATEGORIES:
        skills[category] = _dedupe([str(item).strip() for item in _as_list(raw.get(category)) if str(item).strip()])
    return skills


def _apply_profile_enrichment(profile: dict[str, Any]) -> None:
    skills = profile.get("skills", {})
    enrichment = profile.get("profile_enrichment", {})
    project_inferences: list[dict[str, str]] = []

    for project in profile.get("projects", []):
        if not isinstance(project, dict):
            continue
        source = f"Project: {project.get('name') or 'Unnamed project'}"
        for tech in project.get("technologies", []):
            category = _category_for_technology(tech)
            if category:
                before = list(skills.get(category, []))
                _append_unique(skills[category], tech)
                if before != skills.get(category, []):
                    project_inferences.append(
                        {"skill": str(tech), "category": category, "source": source}
                    )

    experience_inferences: list[dict[str, str]] = []
    for experience in profile.get("experience", []):
        if not isinstance(experience, dict):
            continue
        source = f"Experience: {experience.get('title') or 'Unnamed role'}"
        experience_terms = _dedupe(
            _as_list(experience.get("technologies_used")) + _explicit_terms_from_experience(experience)
        )
        for tech in experience_terms:
            category = _category_for_technology(tech)
            if category:
                before = list(skills.get(category, []))
                _append_unique(skills[category], tech)
                if before != skills.get(category, []):
                    experience_inferences.append(
                        {"technology": str(tech), "category": category, "source": source}
                    )

    enrichment["inferred_skills_from_projects"] = _dedupe_dicts(
        _as_list(enrichment.get("inferred_skills_from_projects")) + project_inferences
    )
    enrichment["inferred_technologies_from_experience"] = _dedupe_dicts(
        _as_list(enrichment.get("inferred_technologies_from_experience")) + experience_inferences
    )
    enrichment["suggested_missing_keywords"] = _suggest_keywords(profile)
    enrichment["ats_improvements"] = _suggest_ats_improvements(profile)
    enrichment["factual_accuracy_notes"] = _dedupe(
        _as_list(enrichment.get("factual_accuracy_notes"))
        + [
            "Do not add GPA, certifications, work authorization, or employment history unless the candidate provides them.",
            "Treat inferred skills as review suggestions derived from listed projects or experience.",
        ]
    )
    profile["skills"] = skills
    profile["profile_enrichment"] = enrichment


def _suggest_keywords(profile: dict[str, Any]) -> list[str]:
    technologies = _all_technologies(profile)
    lowered = {str(item).lower() for item in technologies}
    suggestions: list[str] = []

    if {"node.js", "node", "express", "express.js"} & lowered:
        suggestions.append("Backend API development, if supported by project details.")
    if {"rest apis", "rest api", "api", "apis"} & lowered:
        suggestions.append("REST API design, if you can explain endpoints you built.")
    if {"solidity", "ethereum", "blockchain"} & lowered:
        suggestions.append("Smart contracts, only if your Solidity work included contracts.")
    if {"ipfs"} & lowered:
        suggestions.append("Decentralized storage, if you can describe your IPFS usage.")
    if {"docker"} & lowered:
        suggestions.append("Containerization with Docker, if you used Docker directly.")
    if {"react", "next.js", "next"} & lowered:
        suggestions.append("Component-based frontend development.")
    if {"sqlite", "postgresql", "postgres", "mysql", "mongodb"} & lowered:
        suggestions.append("Database design and query optimization, if supported by your work.")

    return _dedupe(suggestions)


def _suggest_ats_improvements(profile: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    personal = profile.get("personal_information", {})
    skills = profile.get("skills", {})

    if _is_missing(personal.get("github")):
        suggestions.append("Add a GitHub URL so recruiters can inspect projects.")
    if _is_missing(personal.get("linkedin")):
        suggestions.append("Add a LinkedIn URL for outreach and recruiter screening.")
    if not profile.get("projects"):
        suggestions.append("Add 2-4 software projects with technologies, outcomes, and links.")
    for project in profile.get("projects", []):
        if isinstance(project, dict) and _is_missing(project.get("description")):
            suggestions.append(f"Add a one-sentence description for project: {project.get('name') or 'Unnamed project'}.")
        if isinstance(project, dict) and _is_missing(project.get("complexity_level")):
            suggestions.append(f"Add a complexity level for project: {project.get('name') or 'Unnamed project'}.")
    if not skills.get("testing"):
        suggestions.append("Add testing tools or practices only if you have actually used them.")
    if not skills.get("cloud") and not skills.get("devops"):
        suggestions.append("Add cloud or DevOps tools only if they are part of your real project work.")
    if _is_missing(profile.get("career_goals", {}).get("long_term_goals")):
        suggestions.append("Add long-term career goals to improve cover letter and interview prep personalization.")

    return _dedupe(suggestions)


def _recommended_additions(profile: dict[str, Any], missing_fields: list[str]) -> list[str]:
    additions: list[str] = []
    missing = set(missing_fields)
    if {"personal_information.email", "personal_information.phone", "personal_information.location"} & missing:
        additions.append("Complete contact details so generated CV headers are usable.")
    if {"personal_information.github", "personal_information.linkedin"} & missing:
        additions.append("Add GitHub and LinkedIn links for recruiter screening and outreach drafts.")
    if any(field.startswith("education[0]") for field in missing):
        additions.append("Fill education fields from your transcript or university record; keep CGPA null if you do not want it used.")
    if any(field.startswith("skills.") for field in missing):
        additions.append("Add only skills you can defend in an interview, grouped by category.")
    if any(field.startswith("projects[") for field in missing):
        additions.append("Add project descriptions, technologies, highlights, links, and complexity levels where available.")
    if any(field.startswith("career_preferences.") for field in missing):
        additions.append("Add role, location, remote, relocation, and industry preferences to improve recommendations.")
    if any(field.startswith("career_goals.") for field in missing):
        additions.append("Add short-term and long-term goals for stronger cover letters and interview answers.")
    if not profile.get("certifications"):
        additions.append("Leave certifications empty unless you have real certification details to add.")
    return _dedupe(additions)


def _strength_areas(profile: dict[str, Any]) -> list[str]:
    strengths: list[str] = []
    personal = profile.get("personal_information", {})
    if sum(not _is_missing(personal.get(field)) for field in PERSONAL_FIELDS) >= 4:
        strengths.append("Contact profile has enough detail for recruiter-facing materials.")
    if profile.get("education") and not _is_missing(profile["education"][0].get("degree")):
        strengths.append("Education is available for graduate-role positioning.")
    populated_skill_categories = [
        category for category, values in profile.get("skills", {}).items() if not _is_missing(values)
    ]
    if len(populated_skill_categories) >= 4:
        strengths.append("Skills are spread across multiple ATS categories.")
    if profile.get("projects"):
        strengths.append("Projects are available for CV bullets and interview examples.")
    if any(not _is_missing(item.get("achievements")) for item in profile.get("experience", []) if isinstance(item, dict)):
        strengths.append("Experience achievements are available for tailored evidence.")
    return strengths or ["Profile has a factual foundation; add missing details before aggressive tailoring."]


def _all_technologies(profile: dict[str, Any]) -> list[str]:
    technologies: list[str] = []
    for project in profile.get("projects", []):
        if isinstance(project, dict):
            technologies.extend(_as_list(project.get("technologies")))
    for experience in profile.get("experience", []):
        if isinstance(experience, dict):
            technologies.extend(_as_list(experience.get("technologies_used")))
    for values in profile.get("skills", {}).values():
        technologies.extend(_as_list(values))
    return _dedupe([str(item).strip() for item in technologies if str(item).strip()])


def _explicit_terms_from_experience(experience: dict[str, Any]) -> list[str]:
    text_parts = [experience.get("title"), experience.get("company"), experience.get("location")]
    text_parts.extend(_as_list(experience.get("achievements")))
    text = " ".join(str(part or "") for part in text_parts).lower()
    terms: list[str] = []
    for hints in TECH_CATEGORY_HINTS.values():
        for hint in hints:
            if len(hint) < 3:
                continue
            if hint in text:
                terms.append(CANONICAL_TERM_LABELS.get(hint, hint.title()))
    return _dedupe(terms)


def _category_for_technology(technology: Any) -> str | None:
    text = str(technology or "").lower().strip()
    if not text:
        return None
    for category, hints in TECH_CATEGORY_HINTS.items():
        if text in hints or any(hint in text for hint in hints if len(hint) > 3):
            return category
    return None


def _add_skill(skills: dict[str, list[str]], skill: Any) -> None:
    category = _category_for_technology(skill) or "tools"
    _append_unique(skills[category], skill)


def _append_unique(items: list[Any], value: Any) -> None:
    if _is_missing(value):
        return
    text = str(value).strip()
    if text.lower() not in {str(item).lower() for item in items}:
        items.append(text)


def _first_present(*values: Any) -> Any:
    for value in values:
        if not _is_missing(value):
            return value
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in MISSING_SENTINELS
    if isinstance(value, (list, tuple, set)):
        return all(_is_missing(item) for item in value)
    if isinstance(value, dict):
        return all(_is_missing(item) for item in value.values())
    return False


def _extract_last_year(value: Any) -> int | None:
    matches = re.findall(r"(19|20)\d{2}", str(value or ""))
    if not matches:
        year_matches = re.findall(r"\d{4}", str(value or ""))
        return int(year_matches[-1]) if year_matches else None
    year_matches = re.findall(r"(?:19|20)\d{2}", str(value or ""))
    return int(year_matches[-1]) if year_matches else None


def _unmapped_legacy_fields(data: dict[str, Any], mapped_keys: set[str]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in data.items() if key not in mapped_keys}


def _dedupe(items: list[Any]) -> list[Any]:
    seen: set[str] = set()
    deduped: list[Any] = []
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str).lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _dedupe_dicts(items: list[Any]) -> list[dict[str, Any]]:
    dicts = [item for item in items if isinstance(item, dict)]
    return _dedupe(dicts)
