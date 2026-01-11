"""
System tray application for ActivityMonitor.
Provides a minimal, non-intrusive presence in the system tray.
"""

import threading
from typing import Optional, Callable, Dict, Any
import logging

logger = logging.getLogger(__name__)

try:
    import pystray
    from pystray import MenuItem as Item
    from PIL import Image, ImageDraw, ImageFont
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    logger.warning("pystray or Pillow not available. System tray will be disabled.")


class TrayApp:
    """
    System tray application.

    Shows current project and provides quick access to timeline, reports, and settings.
    """

    ICON_SIZE = 64
    COLORS = {
        'active': '#4CAF50',      # Green when actively tracking
        'idle': '#FFC107',        # Yellow when idle
        'paused': '#9E9E9E',      # Gray when paused
        'background': '#2196F3',  # Blue background
    }

    def __init__(self):
        self._icon: Optional[pystray.Icon] = None
        self._running = False
        self._current_project = "No Project"
        self._is_active = True
        self._is_paused = False

        # Callbacks for menu actions
        self._on_show_timeline: Optional[Callable] = None
        self._on_show_reports: Optional[Callable] = None
        self._on_show_settings: Optional[Callable] = None
        self._on_show_mappings: Optional[Callable] = None
        self._on_toggle_pause: Optional[Callable] = None
        self._on_exit: Optional[Callable] = None

    @property
    def is_available(self) -> bool:
        """Check if tray is available."""
        return TRAY_AVAILABLE

    def set_callbacks(
        self,
        on_show_timeline: Optional[Callable] = None,
        on_show_reports: Optional[Callable] = None,
        on_show_settings: Optional[Callable] = None,
        on_show_mappings: Optional[Callable] = None,
        on_toggle_pause: Optional[Callable] = None,
        on_exit: Optional[Callable] = None
    ):
        """Set callback functions for menu actions."""
        self._on_show_timeline = on_show_timeline
        self._on_show_reports = on_show_reports
        self._on_show_settings = on_show_settings
        self._on_show_mappings = on_show_mappings
        self._on_toggle_pause = on_toggle_pause
        self._on_exit = on_exit

    def _create_icon_image(self, status: str = 'active') -> 'Image':
        """
        Create the tray icon image.

        Args:
            status: 'active', 'idle', or 'paused'
        """
        # Create image with transparency
        image = Image.new('RGBA', (self.ICON_SIZE, self.ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Draw circular background
        color = self.COLORS.get(status, self.COLORS['active'])
        padding = 4
        draw.ellipse(
            [padding, padding, self.ICON_SIZE - padding, self.ICON_SIZE - padding],
            fill=color
        )

        # Draw a simple clock/timer icon in the center
        center = self.ICON_SIZE // 2
        radius = (self.ICON_SIZE - padding * 2) // 2 - 8

        # Clock circle outline
        draw.ellipse(
            [center - radius, center - radius, center + radius, center + radius],
            outline='white',
            width=3
        )

        # Clock hands
        # Hour hand (shorter)
        draw.line(
            [center, center, center, center - radius + 8],
            fill='white',
            width=3
        )
        # Minute hand (longer)
        draw.line(
            [center, center, center + radius - 8, center],
            fill='white',
            width=2
        )

        return image

    def _create_menu(self) -> pystray.Menu:
        """Create the tray context menu."""
        pause_text = "Resume Tracking" if self._is_paused else "Pause Tracking"

        # Status indicator
        if self._is_paused:
            status = "PAUSED (gray icon)"
        elif self._is_active:
            status = "ACTIVE (green icon)"
        else:
            status = "IDLE (yellow icon)"

        return pystray.Menu(
            Item(
                f"Project: {self._current_project}",
                None,
                enabled=False
            ),
            Item(
                f"Status: {status}",
                None,
                enabled=False
            ),
            Item("─" * 20, None, enabled=False),
            Item(
                "Today's Timeline",
                self._handle_show_timeline
            ),
            Item(
                "Reports",
                self._handle_show_reports
            ),
            Item("─" * 20, None, enabled=False),
            Item(
                pause_text,
                self._handle_toggle_pause
            ),
            Item(
                "Settings",
                self._handle_show_settings
            ),
            Item(
                "Project Mappings",
                self._handle_show_mappings
            ),
            Item("─" * 20, None, enabled=False),
            Item(
                "Exit",
                self._handle_exit
            )
        )

    def _handle_show_timeline(self, icon, item):
        """Handle timeline menu click."""
        if self._on_show_timeline:
            self._on_show_timeline()

    def _handle_show_reports(self, icon, item):
        """Handle reports menu click."""
        if self._on_show_reports:
            self._on_show_reports()

    def _handle_show_settings(self, icon, item):
        """Handle settings menu click."""
        if self._on_show_settings:
            self._on_show_settings()

    def _handle_show_mappings(self, icon, item):
        """Handle project mappings menu click."""
        if self._on_show_mappings:
            self._on_show_mappings()

    def _handle_toggle_pause(self, icon, item):
        """Handle pause/resume menu click."""
        self._is_paused = not self._is_paused
        self._update_icon()
        if self._on_toggle_pause:
            self._on_toggle_pause(self._is_paused)

    def _handle_exit(self, icon, item):
        """Handle exit menu click."""
        self.stop()
        if self._on_exit:
            self._on_exit()

    def _update_icon(self):
        """Update the tray icon based on current state."""
        if self._icon is None:
            return

        if self._is_paused:
            status = 'paused'
        elif self._is_active:
            status = 'active'
        else:
            status = 'idle'

        self._icon.icon = self._create_icon_image(status)
        self._icon.menu = self._create_menu()

    def update_project(self, project_name: str):
        """Update the current project display."""
        self._current_project = project_name or "No Project"
        if self._icon:
            self._icon.menu = self._create_menu()

    def update_activity_state(self, is_active: bool):
        """Update the activity state (active vs idle)."""
        if self._is_active != is_active:
            self._is_active = is_active
            self._update_icon()

    def update_pause_state(self, is_paused: bool):
        """Update the pause state."""
        if self._is_paused != is_paused:
            self._is_paused = is_paused
            self._update_icon()

    def show_notification(self, title: str, message: str):
        """Show a notification balloon."""
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception as e:
                logger.error(f"Failed to show notification: {e}")

    def start(self, blocking: bool = False):
        """
        Start the tray application.

        Args:
            blocking: If True, run in the current thread (blocks).
                      If False, run in a background thread.
        """
        if not self.is_available:
            logger.warning("Tray not available, cannot start")
            return

        if self._running:
            return

        self._icon = pystray.Icon(
            name="ActivityMonitor",
            icon=self._create_icon_image('active'),
            title="ActivityMonitor - Tracking",
            menu=self._create_menu()
        )

        self._running = True

        if blocking:
            self._icon.run()
        else:
            thread = threading.Thread(target=self._icon.run, daemon=True)
            thread.start()

    def stop(self):
        """Stop the tray application."""
        self._running = False
        if self._icon:
            self._icon.stop()
            self._icon = None


if __name__ == "__main__":
    # Test the tray app
    print("Tray App Test")
    print("-" * 50)

    if not TRAY_AVAILABLE:
        print("pystray or Pillow not available")
        exit(1)

    def on_timeline():
        print("Timeline clicked!")

    def on_reports():
        print("Reports clicked!")

    def on_settings():
        print("Settings clicked!")

    def on_pause(is_paused):
        print(f"Pause toggled: {is_paused}")

    def on_exit():
        print("Exit clicked!")

    tray = TrayApp()
    tray.set_callbacks(
        on_show_timeline=on_timeline,
        on_show_reports=on_reports,
        on_show_settings=on_settings,
        on_toggle_pause=on_pause,
        on_exit=on_exit
    )

    print("Starting tray app...")
    print("Look for the icon in your system tray.")
    print("Right-click to see the menu.")

    # Simulate project changes
    import time

    tray.start(blocking=False)
    time.sleep(2)

    projects = ["ActivityMonitor", "ClientProject", "InternalTool", None]
    for i, project in enumerate(projects):
        print(f"Setting project: {project}")
        tray.update_project(project)
        tray.update_activity_state(i % 2 == 0)
        time.sleep(3)

    print("\nTray will keep running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tray.stop()
        print("Stopped.")
