"""
Configuration module for ActivityMonitor.
Manages application settings with defaults and persistence.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json


@dataclass
class Config:
    """Application configuration with sensible defaults."""

    # Idle detection
    idle_timeout_minutes: int = 3
    polling_interval_seconds: int = 5

    # Camera settings
    camera_enabled: bool = False
    camera_check_interval_seconds: int = 10
    camera_away_threshold_seconds: int = 30
    camera_device_index: int = 0

    # UI settings
    show_notifications: bool = True
    start_minimized: bool = False
    start_with_windows: bool = False

    # Theme settings
    theme: str = "darkly"  # ttkbootstrap theme: darkly, superhero, litera, flatly, etc.

    # Daily summary notification
    daily_summary_enabled: bool = True
    daily_summary_hour: int = 18  # 6 PM

    # Break reminders
    break_reminder_enabled: bool = True
    break_reminder_interval_minutes: int = 50  # Pomodoro-style
    break_reminder_snooze_minutes: int = 10

    # Project detection
    visual_studio_solution_detection: bool = True
    default_project: str = "Uncategorized"

    # Data retention
    keep_data_days: int = 90

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        # Filter out any unknown keys
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ConfigManager:
    """Manages loading and saving configuration to database."""

    CONFIG_KEY = 'app_config'

    def __init__(self, database):
        self.db = database
        self._config: Optional[Config] = None

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self) -> Config:
        """Load configuration from database."""
        stored = self.db.get_setting(self.CONFIG_KEY)
        if stored is None:
            return Config()

        if isinstance(stored, str):
            stored = json.loads(stored)

        return Config.from_dict(stored)

    def save(self, config: Optional[Config] = None):
        """Save configuration to database."""
        if config is not None:
            self._config = config

        if self._config is not None:
            self.db.set_setting(self.CONFIG_KEY, self._config.to_dict())

    def update(self, **kwargs):
        """Update specific configuration values."""
        config = self.config
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self.save()

    def reset_to_defaults(self):
        """Reset configuration to defaults."""
        self._config = Config()
        self.save()
