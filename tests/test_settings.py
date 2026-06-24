from pathlib import Path

from job_copilot.settings import load_settings


def test_settings_loads_environment_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "custom-model")
    monkeypatch.setenv("JOB_COPILOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JOB_COPILOT_CACHE_RESPONSES", "false")
    settings = load_settings(project_root=tmp_path)
    assert settings.openai_api_key_present is True
    assert settings.default_model == "custom-model"
    assert settings.default_model in settings.model_options
    assert settings.cache_enabled is False
    assert settings.data_dir == tmp_path / "data"
    assert not [issue for issue in settings.environment_issues() if issue.name == "OPENAI_API_KEY"]
