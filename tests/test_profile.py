from pathlib import Path

from job_copilot.profile import enhance_profile, load_profile, validate_profile, write_profile_file


def test_legacy_profile_migrates_without_inventing_facts() -> None:
    legacy = {
        "basics": {"name": "Aisha Khan", "email": "aisha@example.com"},
        "degree": "BS Software Engineering",
        "university": "Example University",
        "skills": {"frameworks": ["React", "Node.js"], "tools": ["Git"]},
        "projects": [
            {
                "name": "Campus Marketplace",
                "technologies": ["React", "Node.js", "MongoDB"],
                "bullets": ["Built listing and saved-item APIs."],
            }
        ],
        "certifications": [],
    }

    profile = enhance_profile(legacy)
    assert profile["personal_information"]["name"] == "Aisha Khan"
    assert profile["education"][0]["degree"] == "BS Software Engineering"
    assert profile["education"][0]["cgpa"] is None
    assert profile["certifications"] == []
    assert "Node.js" in profile["skills"]["backend"]
    assert profile["profile_enrichment"]["inferred_skills_from_projects"]


def test_profile_validation_completeness_and_warnings() -> None:
    profile = enhance_profile({"name": "Aisha Khan", "projects": []})
    validation = validate_profile(profile)
    assert validation["completeness_percent"] < 100
    assert "projects" in validation["missing_fields"]
    assert any("No experience" in warning for warning in validation["warnings"])


def test_profile_json_and_yaml_roundtrip(tmp_path: Path) -> None:
    profile = enhance_profile({"name": "Aisha Khan"})
    json_path = tmp_path / "profile.json"
    yaml_path = tmp_path / "profile.yaml"

    write_profile_file(json_path, profile)
    write_profile_file(yaml_path, profile)

    assert load_profile(json_path)["personal_information"]["name"] == "Aisha Khan"
    assert load_profile(yaml_path)["personal_information"]["name"] == "Aisha Khan"
