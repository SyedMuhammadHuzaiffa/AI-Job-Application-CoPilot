import json
from typing import Any

from job_copilot.llm import generate_tailoring
from job_copilot.resume_intelligence import (
    analysis_to_markdown,
    build_profile_cv_text,
    generate_resume_intelligence,
    markdown_to_pdf_bytes,
)


class StaticChatClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def create_json_chat(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return json.dumps(self.payload)


def test_generate_tailoring_with_mocked_openai_response() -> None:
    payload = {
        "job": {"title": "Junior Engineer", "company": "Acme"},
        "fit": {"score": 101, "ats_match_percent": "78", "strengths": "Python", "gaps": ["AWS"]},
        "ats_keywords": ["Python"],
        "cv": {"bullets": [{"source": "Project", "tailored": "Built Python APIs."}]},
        "cover_letter": {"body": ["Dear team."]},
        "application_answers": [{"question": "Why us?", "answer": "Strong fit."}],
    }
    client = StaticChatClient(payload)
    result = generate_tailoring({"personal_information": {"name": "Aisha"}}, "Python role", chat_client=client)
    assert result["fit"]["score"] == 100
    assert result["fit"]["ats_match_percent"] == 78
    assert result["fit"]["skill_gaps"] == ["AWS"]
    assert result["cv"]["bullets"][0]["tailored"] == "Built Python APIs."
    assert client.calls[0]["model"]


def test_generate_resume_intelligence_with_mocked_openai_response() -> None:
    payload = {
        "scores": {
            "overall_match_score": 80,
            "ats_match_score": 76,
            "technical_match_score": 82,
            "experience_match_score": 55,
            "education_match_score": 90,
        },
        "project_prioritization": [
            {"project_name": "API Tracker", "relevance_score": 88, "recommended_bullet_points": ["Built APIs"]}
        ],
        "apply_recommendation": {"label": "Apply", "reasoning": "Good overlap."},
    }
    client = StaticChatClient(payload)
    profile = {
        "personal_information": {"name": "Aisha"},
        "skills": {"languages": ["Python"]},
        "projects": [{"name": "API Tracker", "technologies": ["Python"], "highlights": ["Built APIs"]}],
    }
    cv_text = build_profile_cv_text(profile)
    analysis = generate_resume_intelligence(profile, cv_text, "Python job", chat_client=client)
    markdown = analysis_to_markdown(analysis)
    assert analysis["scores"]["overall_match_score"] == 80
    assert analysis["apply_recommendation"]["label"] == "Apply"
    assert "Resume Intelligence Analysis" in markdown
    assert markdown_to_pdf_bytes(markdown).startswith(b"%PDF")
