"""
Configuration module for ActivityMonitor.
Manages application settings with defaults and persistence.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List
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
    auto_create_project_tags: bool = True  # Automatically create tags for new VS/VSCode projects

    # Hidden categories (not shown in reports by default)
    # Available: Development, Browser, Communication, Remote Desktop, Office,
    #            Email, Terminal, Editor, Media, System, Security, Other
    hidden_categories: List[str] = field(default_factory=lambda: ["System"])

    # Hidden apps (specific apps to hide from reports/timeline)
    # Uses case-insensitive partial matching against activity names
    # Examples: ["spotify", "apple music", "vlc", "discord"]
    hidden_apps: List[str] = field(default_factory=list)

    # Claude Code tracking (WSL)
    claude_code_tracking_enabled: bool = True
    wsl_username: str = "talwinter"
    wsl_distro: str = "Ubuntu"
    claude_code_stale_threshold_seconds: int = 60  # Consider inactive if no update for this long

    # Teams meeting tracking
    teams_background_tracking_enabled: bool = True  # Track Teams meetings when not focused

    # Admiral time reporting automation
    admiral_enabled: bool = True
    admiral_url: str = "https://admiral.co.il/AdmiralPro_ssl2//Main/Frame_Main.aspx?C=F1308D9B"
    admiral_default_comment: str = "פיתוח"  # Default comment for time entries

    # Report settings
    minimum_activity_seconds: int = 30  # Filter out activities shorter than this from reports
    time_rounding_minutes: int = 0  # Round times to nearest X minutes (0 = no rounding, 15 or 30 common)

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
