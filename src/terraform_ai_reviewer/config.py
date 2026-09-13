from pathlib import Path

import yaml

from terraform_ai_reviewer.models import ReviewerConfig


class ConfigurationError(ValueError):
    """Raised when reviewer configuration cannot be loaded."""


def load_config(path: Path) -> ReviewerConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ConfigurationError("configuration must contain a YAML object")
        return ReviewerConfig.model_validate(raw)
    except (OSError, yaml.YAMLError, ValueError) as error:
        if isinstance(error, ConfigurationError):
            raise
        message = f"invalid reviewer configuration: {type(error).__name__}"
        raise ConfigurationError(message) from error
