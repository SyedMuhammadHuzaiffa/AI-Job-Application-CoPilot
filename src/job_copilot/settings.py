import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_OPTIONS = (
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4o-mini",
    "gpt-4o",
)


@dataclass(frozen=True)
class EnvironmentIssue:
    name: str
    message: str
    severity: str = "warning"


@dataclass(frozen=True)
class AppSettings:
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    export_dir: Path = PROJECT_ROOT / "exports"
    template_dir: Path = PROJECT_ROOT / "templates"
    default_profile_path: Path = PROJECT_ROOT / "profile.json"
    sample_profile_path: Path = PROJECT_ROOT / "sample_profile.json"
    sample_advanced_profile_path: Path = PROJECT_ROOT / "sample_profile_advanced.json"
    tracker_db_path: Path = PROJECT_ROOT / "data" / "applications.db"
    job_discovery_db_path: Path = PROJECT_ROOT / "data" / "job_discovery.db"
    job_source_config_path: Path = PROJECT_ROOT / "data" / "job_sources.json"
    default_model: str = "gpt-4.1-mini"
    model_options: tuple[str, ...] = DEFAULT_MODEL_OPTIONS
    openai_api_key: str | None = None
    request_timeout_seconds: int = 30
    retry_attempts: int = 3
    retry_backoff_seconds: float = 0.75
    cache_enabled: bool = True
    cache_path: Path = PROJECT_ROOT / "data" / "cache" / "llm_responses.json"
    log_level: str = "INFO"

    @property
    def openai_api_key_present(self) -> bool:
        return bool(self.openai_api_key)

    def environment_issues(self) -> list[EnvironmentIssue]:
        issues: list[EnvironmentIssue] = []
        if not self.openai_api_key:
            issues.append(
                EnvironmentIssue(
                    name="OPENAI_API_KEY",
                    message="OpenAI generation is disabled until OPENAI_API_KEY is set.",
                    severity="warning",
                )
            )
        if self.retry_attempts < 1:
            issues.append(
                EnvironmentIssue(
                    name="JOB_COPILOT_RETRY_ATTEMPTS",
                    message="Retry attempts must be at least 1.",
                    severity="error",
                )
            )
        if self.request_timeout_seconds < 5:
            issues.append(
                EnvironmentIssue(
                    name="JOB_COPILOT_REQUEST_TIMEOUT_SECONDS",
                    message="Request timeout should be at least 5 seconds.",
                    severity="warning",
                )
            )
        for label, path in (
            ("DATA_DIR", self.data_dir),
            ("EXPORT_DIR", self.export_dir),
            ("TEMPLATE_DIR", self.template_dir),
        ):
            if label == "TEMPLATE_DIR" and not path.exists():
                issues.append(
                    EnvironmentIssue(
                        name=label,
                        message=f"Required template directory does not exist: {path}",
                        severity="error",
                    )
                )
        return issues

    def as_display_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "data_dir": str(self.data_dir),
            "export_dir": str(self.export_dir),
            "template_dir": str(self.template_dir),
            "tracker_db_path": str(self.tracker_db_path),
            "job_discovery_db_path": str(self.job_discovery_db_path),
            "job_source_config_path": str(self.job_source_config_path),
            "default_model": self.default_model,
            "model_options": ", ".join(self.model_options),
            "request_timeout_seconds": self.request_timeout_seconds,
            "retry_attempts": self.retry_attempts,
            "cache_enabled": self.cache_enabled,
            "cache_path": str(self.cache_path),
            "log_level": self.log_level,
            "openai_api_key_present": self.openai_api_key_present,
        }


def load_settings(project_root: Path = PROJECT_ROOT) -> AppSettings:
    data_dir = _path_env("JOB_COPILOT_DATA_DIR", project_root / "data")
    export_dir = _path_env("JOB_COPILOT_EXPORT_DIR", project_root / "exports")
    template_dir = _path_env("JOB_COPILOT_TEMPLATE_DIR", project_root / "templates")
    default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    model_options = _model_options(default_model)
    return AppSettings(
        project_root=project_root,
        data_dir=data_dir,
        export_dir=export_dir,
        template_dir=template_dir,
        default_profile_path=_path_env("JOB_COPILOT_PROFILE_PATH", project_root / "profile.json"),
        sample_profile_path=project_root / "sample_profile.json",
        sample_advanced_profile_path=project_root / "sample_profile_advanced.json",
        tracker_db_path=_path_env("JOB_COPILOT_TRACKER_DB_PATH", data_dir / "applications.db"),
        job_discovery_db_path=_path_env("JOB_COPILOT_JOB_DISCOVERY_DB_PATH", data_dir / "job_discovery.db"),
        job_source_config_path=_path_env("JOB_COPILOT_JOB_SOURCE_CONFIG_PATH", data_dir / "job_sources.json"),
        default_model=default_model,
        model_options=model_options,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        request_timeout_seconds=_int_env("JOB_COPILOT_REQUEST_TIMEOUT_SECONDS", 30),
        retry_attempts=_int_env("JOB_COPILOT_RETRY_ATTEMPTS", 3),
        retry_backoff_seconds=_float_env("JOB_COPILOT_RETRY_BACKOFF_SECONDS", 0.75),
        cache_enabled=_bool_env("JOB_COPILOT_CACHE_RESPONSES", True),
        cache_path=_path_env("JOB_COPILOT_CACHE_PATH", data_dir / "cache" / "llm_responses.json"),
        log_level=os.getenv("JOB_COPILOT_LOG_LEVEL", "INFO"),
    )


def _path_env(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser() if value else default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _model_options(default_model: str) -> tuple[str, ...]:
    raw = os.getenv("JOB_COPILOT_MODEL_OPTIONS")
    options = [item.strip() for item in raw.split(",")] if raw else list(DEFAULT_MODEL_OPTIONS)
    if default_model and default_model not in options:
        options.insert(0, default_model)
    return tuple(dict.fromkeys(option for option in options if option))
