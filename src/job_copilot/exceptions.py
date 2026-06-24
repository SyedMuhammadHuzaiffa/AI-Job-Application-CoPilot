class JobCopilotError(RuntimeError):
    """Base exception for expected application failures."""


class ConfigurationError(JobCopilotError):
    """Raised when runtime configuration is incomplete or invalid."""


class OpenAIConfigError(ConfigurationError):
    """Raised when the OpenAI client cannot be configured."""


class OpenAIRequestError(JobCopilotError):
    """Raised when an OpenAI request fails after retries."""


class ValidationError(JobCopilotError, ValueError):
    """Raised when user-provided data fails validation."""
