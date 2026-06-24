from pathlib import Path

import pytest

from job_copilot.profile import (
    ProfileError,
    enhance_profile,
    load_profile,
    profile_display_name,
    profile_to_prompt_text,
    read_profile_file,
    validate_profile,
    write_profile_file,
)


def test_enhanced_profile_merge_and_enrichment_branches() -> None:
    raw = {
        "profile_version": "2.0",
        "personal_information": {
            "name": "Bilal",
            "email": "bilal@example.com",
            "phone": "123",
            "location": "Karachi",
            "github": "https://github.com/bilal",
            "linkedin": "https://linkedin.com/in/bilal",
        },
        "education": {"degree": "BS Software Engineering", "school": "FAST", "dates": "2022-2026"},
        "skills": {"languages": ("Python", "SQL"), "testing": {"pytest"}},
        "experience": [
            {
                "title": "Freelance Developer",
                "achievements": ["Built React UI and Docker hosting workflow."],
                "technologies": ["Docker"],
            }
        ],
        "projects": [
            {
                "name": "AI API",
                "description": "OpenAI REST API app",
                "tech": ["OpenAI", "SQLite", "React"],
                "bullets": ["Built responsive frontend"],
                "github": "https://github.com/bilal/ai-api",
                "complexity_level": "Intermediate",
            }
        ],
        "career_preferences": {
            "preferred_roles": "Backend Engineer",
            "preferred_locations": "Remote",
            "industries_of_interest": "SaaS",
        },
        "career_goals": {"short_term_goals": "Get a graduate role", "long_term_goals": "Lead backend systems"},
    }
    profile = enhance_profile(raw)
    assert profile["education"][0]["graduation_year"] == 2026
    assert "OpenAI" in profile["skills"]["ai_tools"]
    assert "SQLite" in profile["skills"]["databases"]
    assert "Docker" in profile["skills"]["devops"]
    assert profile_display_name(profile) == "Bilal"
    assert "Bilal" in profile_to_prompt_text(profile)

    validation = validate_profile(profile)
    assert validation["strength_areas"]
    assert validation["completeness_percent"] > 50


def test_profile_file_errors_and_unsupported_suffix(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(ProfileError):
        read_profile_file(missing)

    txt = tmp_path / "profile.txt"
    txt.write_text("{}", encoding="utf-8")
    with pytest.raises(ProfileError):
        read_profile_file(txt)
    with pytest.raises(ProfileError):
        write_profile_file(txt, {"name": "Aisha"})

    invalid_json = tmp_path / "bad.json"
    invalid_json.write_text("[]", encoding="utf-8")
    with pytest.raises(ProfileError):
        read_profile_file(invalid_json)

    no_name = tmp_path / "no-name.json"
    write_profile_file(no_name, {"skills": ["Python"]})
    with pytest.raises(ProfileError):
        load_profile(no_name)
