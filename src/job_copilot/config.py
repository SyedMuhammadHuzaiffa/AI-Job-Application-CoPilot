from .settings import load_settings


SETTINGS = load_settings()

PROJECT_ROOT = SETTINGS.project_root
DATA_DIR = SETTINGS.data_dir
EXPORT_DIR = SETTINGS.export_dir
TEMPLATE_DIR = SETTINGS.template_dir
DEFAULT_PROFILE_PATH = SETTINGS.default_profile_path
SAMPLE_PROFILE_PATH = SETTINGS.sample_profile_path
SAMPLE_ADVANCED_PROFILE_PATH = SETTINGS.sample_advanced_profile_path
TRACKER_DB_PATH = SETTINGS.tracker_db_path
JOB_DISCOVERY_DB_PATH = SETTINGS.job_discovery_db_path
JOB_SOURCE_CONFIG_PATH = SETTINGS.job_source_config_path

DEFAULT_MODEL = SETTINGS.default_model
MODEL_OPTIONS = SETTINGS.model_options
