import json
from pathlib import Path
from typing import Any

import pytest

from job_copilot.application_assistant import (
    ApplicationPacket,
    apply_packet_status,
    build_application_packet,
    build_copy_fields,
    saved_job_to_prompt,
)
from job_copilot.profile import enhance_profile
from job_copilot.tracker import list_applications


class StaticChatClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def create_json_chat(self, **kwargs: Any) -> str:
        return json.dumps(self.payload)


def _profile() -> dict[str, Any]:
    return enhance_profile(
        {
            "name": "Aisha Khan",
            "email": "aisha@example.com",
            "phone": "+92 300 0000000",
            "location": "Karachi, Pakistan",
            "github": "https://github.com/aisha",
            "linkedin": "https://linkedin.com/in/aisha",
            "skills": {"languages": ["Python"], "ai_tools": ["OpenAI API"], "tools": ["Git"]},
            "projects": [
                {
                    "name": "API Tracker",
                    "description": "A Streamlit job tracker",
                    "technologies": ["Python", "Streamlit"],
                    "highlights": ["Built truthful application packet generation."],
                }
            ],
            "experience": [
                {
                    "title": "Freelance Web Developer",
                    "achievements": ["Built responsive websites."],
                }
            ],
            "application_preferences": {"availability": "Available after graduation"},
        }
    )


def test_build_application_packet_and_copy_fields(tmp_path: Path) -> None:
    payload = {
        "job": {"title": "Junior Engineer", "company": "Acme", "apply_link": "https://example.com/apply"},
        "fit": {"score": 80, "ats_match_percent": 76},
        "cv": {"bullets": [{"source": "Project", "tailored": "Built Python tooling."}]},
        "cover_letter": {"body": ["I am interested in this role."]},
        "application_answers": [{"question": "Why this role?", "answer": "It matches my Python projects."}],
        "linkedin_outreach": {"recruiter_message": "Hello, I am interested in the junior role."},
        "approval_checklist": ["Review generated claims."],
    }
    saved_job = {
        "id": 12,
        "role": "Junior Engineer",
        "company": "Acme",
        "location": "Remote",
        "apply_url": "https://example.com/apply",
        "description": "Python junior role",
        "source": "Lever",
        "missing_skills": ["AWS"],
        "missing_keywords": ["Docker"],
    }
    packet = build_application_packet(
        _profile(),
        saved_job,
        export_dir=tmp_path / "exports",
        tracker_db_path=tmp_path / "tracker.db",
        chat_client=StaticChatClient(payload),
    )

    assert packet.job_title == "Junior Engineer"
    assert packet.company == "Acme"
    assert packet.tracker_id == 1
    assert packet.discovered_job_id == 12
    assert Path(packet.cv_tex_path).exists()
    assert packet.answers[0]["answer"] == "It matches my Python projects."
    assert "First name" in packet.copy_fields
    assert packet.copy_fields["First name"] == "Aisha"
    assert "OpenAI API" in packet.copy_fields["AI tools answer"]
    assert "Review generated claims." in packet.checklist
    assert list_applications(tmp_path / "tracker.db")[0]["status"] == "Draft"

    prompt = saved_job_to_prompt(saved_job)
    assert "Missing skills" in prompt
    roundtrip = ApplicationPacket.from_dict(packet.as_dict())
    assert roundtrip.company == packet.company


def test_packet_status_requires_approval(tmp_path: Path) -> None:
    packet = build_application_packet(
        _profile(),
        {"role": "Engineer", "company": "Acme", "apply_url": "https://example.com"},
        export_dir=tmp_path / "exports",
        tracker_db_path=tmp_path / "tracker.db",
        chat_client=StaticChatClient(
            {
                "job": {"title": "Engineer", "company": "Acme", "apply_link": "https://example.com"},
                "fit": {"score": 50, "ats_match_percent": 50},
                "cover_letter": {"body": ["Hello"]},
            }
        ),
    )

    ready = apply_packet_status(packet, "Ready to Apply", tracker_db_path=tmp_path / "tracker.db")
    assert ready.status == "Ready to Apply"
    assert list_applications(tmp_path / "tracker.db")[0]["status"] == "Ready to Apply"

    with pytest.raises(ValueError):
        apply_packet_status(ready, "Applied", approved=False, tracker_db_path=tmp_path / "tracker.db")

    applied = apply_packet_status(ready, "Applied", approved=True, tracker_db_path=tmp_path / "tracker.db")
    assert applied.status == "Applied"
    assert list_applications(tmp_path / "tracker.db")[0]["status"] == "Applied"


def test_copy_fields_use_not_specified_for_missing_facts() -> None:
    fields = build_copy_fields(enhance_profile({"name": "Aisha"}))
    assert fields["Email"] == "Not specified in profile."
    assert fields["English proficiency"] == "Not specified in profile."
    assert fields["Track record answer"] == "Not specified in profile."
