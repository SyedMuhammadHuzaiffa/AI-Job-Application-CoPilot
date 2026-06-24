from pathlib import Path

from job_copilot.latex import latex_escape, render_cover_letter_tex, render_cv_tex, write_exports
from job_copilot.profile import enhance_profile


def test_latex_rendering_and_exports(tmp_path: Path) -> None:
    profile = enhance_profile(
        {
            "name": "Aisha & Khan",
            "email": "aisha@example.com",
            "projects": [{"name": "API Tracker", "technologies": ["Python"], "bullets": ["Built APIs"]}],
        }
    )
    result = {
        "cv": {
            "summary": "Backend-focused graduate",
            "skills_to_highlight": ["Python"],
            "bullets": [{"source": "Project", "tailored": "Built REST APIs & dashboards."}],
        },
        "cover_letter": {"recipient": "Hiring Manager", "body": ["I am interested in this role."]},
        "job": {"company": "Acme", "title": "Engineer"},
    }
    cv = render_cv_tex(profile, result)
    letter = render_cover_letter_tex(profile, result, {"company": "Acme", "title": "Engineer"})
    assert r"Aisha \& Khan" in cv
    assert "Backend-focused graduate" in cv
    assert "I am interested" in letter
    assert latex_escape("A&B_") == r"A\&B\_"

    paths = write_exports(profile, result, {"company": "Acme", "title": "Engineer"}, tmp_path)
    assert paths["cv"].exists()
    assert paths["cover_letter"].exists()
