"""Configuration manager for automatic features.

Provides AutoConfig dataclass with load/save methods for ./data/config.json.
Singleton access via get_config().
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

CONFIG_PATH = "./data/config.json"


@dataclass
class AutoConfig:
    """Configuration for automatic save, retrieve, and track features.

    Attributes:
        auto_save: Enable automatic tool call/response saving.
        auto_retrieve: Enable automatic context injection.
        auto_track: Enable background file watching.
        auto_context_tokens: Token budget for auto-injected context.
        watch_dirs: Directories to monitor for file changes.
        watch_ignore_dirs: Directory names to ignore during file watching.
        flush_interval_seconds: Interval for buffered flushes (unused in sync mode).
    """

    auto_save: bool = True
    auto_retrieve: bool = True
    auto_track: bool = True
    auto_context_tokens: int = 300
    watch_dirs: list[str] = field(default_factory=lambda: ["./src"])
    watch_ignore_dirs: list[str] = field(
        default_factory=lambda: [".git", "__pycache__", ".venv", "node_modules", "data"]
    )
    flush_interval_seconds: int = 30

    def __post_init__(self) -> None:
        """Validate and clamp configuration values."""
        self.auto_context_tokens = max(50, min(2000, self.auto_context_tokens))
        self.flush_interval_seconds = max(5, self.flush_interval_seconds)

    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "AutoConfig":
        """Load configuration from JSON file, merging with defaults.

        Creates the file if it doesn't exist. Unknown keys are silently ignored.
        Partial JSON preserves missing defaults.

        Args:
            path: Path to the configuration JSON file.

        Returns:
            AutoConfig instance with merged values.
        """
        defaults = asdict(cls())
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
            for k, v in data.items():
                if k in defaults:
                    defaults[k] = v
        return cls(**defaults)

    def save(self, path: str = CONFIG_PATH) -> None:
        """Serialize configuration to JSON file.

        Creates parent directories if they don't exist.

        Args:
            path: Output file path for the configuration.
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)


# Module-level singleton (follows get_store() pattern)
_config: AutoConfig | None = None


def get_config() -> AutoConfig:
    """Get or create the module-level AutoConfig singleton.

    Returns:
        AutoConfig instance, loaded from disk on first call.
    """
    global _config
    if _config is None:
        _config = AutoConfig.load()
    return _config


def reset_config() -> None:
    """Reset the global AutoConfig singleton (useful for testing)."""
    global _config
    _config = None
