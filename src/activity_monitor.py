"""
ActivityMonitor - Automatic Time Tracking Tool

Main entry point that coordinates all components:
- Window tracking
- Idle detection
- Camera presence detection
- Project mapping
- System tray interface
"""

import sys
import time
import logging
import threading
import re
from datetime import datetime, timedelta
from typing import Optional

import tkinter as tk

try:
    import ttkbootstrap as ttk
    from ttkbootstrap import Window as TtkWindow
    TTKBOOTSTRAP_AVAILABLE = True
except ImportError:
    from tkinter import ttk
    TtkWindow = None
    TTKBOOTSTRAP_AVAILABLE = False

from database import Database
from config import Config, ConfigManager
from window_tracker import WindowTracker
from idle_detector import IdleMonitor
from camera_detector import CameraDetector
from project_mapper import ProjectMapper
from ui.tray_app import TrayApp
from ui.timeline_view import TimelineView
from ui.report_view import ReportView
from ui.settings_view import SettingsView
from ui.project_mappings_view import ProjectMappingsView

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('activity_monitor.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class ActivityMonitor:
    """
    Main application class that coordinates all components.
    """

    def __init__(self):
        logger.info("Initializing ActivityMonitor...")

        # Initialize core components
        self.db = Database()
        self.config_manager = ConfigManager(self.db)
        self.config = self.config_manager.config

        # Initialize trackers
        self.window_tracker = WindowTracker()
        self.idle_monitor = IdleMonitor(
            idle_threshold_seconds=self.config.idle_timeout_minutes * 60
        )
        self.project_mapper = ProjectMapper(self.db)

        # Camera detector (optional)
        self.camera_detector = CameraDetector(
            check_interval_seconds=self.config.camera_check_interval_seconds,
            away_threshold_seconds=self.config.camera_away_threshold_seconds,
            camera_index=self.config.camera_device_index
        )

        # UI components
        self._root = None  # Will be TtkWindow or tk.Tk
        self.tray_app = TrayApp()
        self.timeline_view: Optional[TimelineView] = None
        self.report_view: Optional[ReportView] = None
        self.settings_view: Optional[SettingsView] = None
        self.mappings_view: Optional[ProjectMappingsView] = None

        # State
        self._running = False
        self._paused = False
        self._tracking_thread: Optional[threading.Thread] = None
        self._current_project: Optional[str] = None
        self._is_active = True

        # Break reminder state
        self._last_break_time = datetime.now()
        self._break_reminder_shown = False
        self._continuous_work_start: Optional[datetime] = None

        # Daily summary state
        self._daily_summary_shown_today = False
        self._last_summary_date: Optional[datetime] = None

        # Set up tray callbacks
        self._setup_tray()

        logger.info("ActivityMonitor initialized")

    def _setup_tray(self):
        """Configure system tray callbacks."""
        self.tray_app.set_callbacks(
            on_show_timeline=self._show_timeline,
            on_show_reports=self._show_reports,
            on_show_settings=self._show_settings,
            on_show_mappings=self._show_mappings,
            on_toggle_pause=self._toggle_pause,
            on_exit=self._exit
        )

        # Set up camera presence callback
        if self.camera_detector.is_available:
            self.camera_detector.set_presence_callback(self._on_presence_change)

    def _get_root(self):
        """Get or create the tkinter root window."""
        if self._root is None or not self._root.winfo_exists():
            if TTKBOOTSTRAP_AVAILABLE:
                self._root = TtkWindow(themename=self.config.theme)
            else:
                import tkinter as tk
                self._root = tk.Tk()
            self._root.withdraw()  # Hide the main window
        return self._root

    def _show_timeline(self):
        """Show the timeline view (called from tray thread)."""
        logger.info("Opening timeline view")
        self._schedule_ui_action(self._do_show_timeline)

    def _do_show_timeline(self):
        """Actually show timeline (runs on main thread)."""
        try:
            root = self._get_root()
            if self.timeline_view is None:
                self.timeline_view = TimelineView(self.db, root)
            self.timeline_view.show()
        except Exception as e:
            logger.error(f"Error showing timeline: {e}", exc_info=True)

    def _show_reports(self):
        """Show the reports view (called from tray thread)."""
        logger.info("Opening reports view")
        self._schedule_ui_action(self._do_show_reports)

    def _do_show_reports(self):
        """Actually show reports (runs on main thread)."""
        try:
            root = self._get_root()
            if self.report_view is None:
                self.report_view = ReportView(self.db, root)
            self.report_view.show()
        except Exception as e:
            logger.error(f"Error showing reports: {e}", exc_info=True)

    def _show_settings(self):
        """Show the settings view (called from tray thread)."""
        logger.info("Opening settings view")
        self._schedule_ui_action(self._do_show_settings)

    def _do_show_settings(self):
        """Actually show settings (runs on main thread)."""
        print(">>> DEBUG: _do_show_settings called")
        try:
            root = self._get_root()
            print(f">>> DEBUG: Got root window: {root}")
            if self.settings_view is None:
                print(">>> DEBUG: Creating new SettingsView")
                self.settings_view = SettingsView(
                    self.config_manager,
                    root,
                    on_save=self._on_settings_saved,
                    camera_detector=self.camera_detector
                )
            print(">>> DEBUG: Calling settings_view.show()")
            self.settings_view.show()
            print(">>> DEBUG: settings_view.show() completed")
        except Exception as e:
            print(f">>> DEBUG ERROR: {e}")
            logger.error(f"Error showing settings: {e}", exc_info=True)

    def _show_mappings(self):
        """Show the project mappings view (called from tray thread)."""
        logger.info("Opening project mappings view")
        self._schedule_ui_action(self._do_show_mappings)

    def _do_show_mappings(self):
        """Actually show project mappings (runs on main thread)."""
        try:
            root = self._get_root()
            if self.mappings_view is None:
                self.mappings_view = ProjectMappingsView(
                    self.db,
                    self.project_mapper,
                    root
                )
            self.mappings_view.show()
        except Exception as e:
            logger.error(f"Error showing project mappings: {e}", exc_info=True)

    def _schedule_ui_action(self, action):
        """Schedule a UI action to run on the main thread."""
        print(f">>> DEBUG: _schedule_ui_action called for {action.__name__}")
        print(f">>> DEBUG: _root={self._root}, _running={self._running}")
        if self._root and self._running:
            try:
                print(">>> DEBUG: Scheduling with after(10, ...)")
                # Use after() with small delay instead of after_idle()
                self._root.after(10, action)
            except Exception as e:
                print(f">>> DEBUG: Schedule error: {e}")
                logger.error(f"Error scheduling UI action: {e}")
        else:
            print(">>> DEBUG: Cannot schedule - root or running is None/False")

    def _on_settings_saved(self):
        """Handle settings being saved."""
        logger.info("Settings saved, applying changes...")
        self.config = self.config_manager.config

        # Update idle threshold
        self.idle_monitor.set_threshold(self.config.idle_timeout_minutes * 60)

        # Update camera settings
        if self.config.camera_enabled and not self.camera_detector.is_enabled:
            self.camera_detector.check_interval = self.config.camera_check_interval_seconds
            self.camera_detector.away_threshold = self.config.camera_away_threshold_seconds
            if self.camera_detector.is_available:
                self.camera_detector.start()
        elif not self.config.camera_enabled and self.camera_detector.is_enabled:
            self.camera_detector.stop()

    def _toggle_pause(self, is_paused: bool):
        """Toggle pause state."""
        self._paused = is_paused
        logger.info(f"Tracking {'paused' if is_paused else 'resumed'}")

        if self.config.show_notifications:
            status = "paused" if is_paused else "resumed"
            self.tray_app.show_notification("ActivityMonitor", f"Tracking {status}")

    def _on_presence_change(self, is_present: bool):
        """Handle camera presence state change."""
        logger.info(f"Presence changed: {'present' if is_present else 'away'}")

        if self.config.show_notifications:
            status = "detected" if is_present else "not detected"
            self.tray_app.show_notification("ActivityMonitor", f"User {status}")

    def _exit(self):
        """Exit the application."""
        logger.info("Exiting ActivityMonitor...")
        self.stop()

    def start(self):
        """Start the activity monitor."""
        if self._running:
            return

        logger.info("Starting ActivityMonitor...")
        self._running = True

        # Start camera detection if enabled
        if self.config.camera_enabled and self.camera_detector.is_available:
            logger.info("Starting camera detection...")
            self.camera_detector.start()

        # Start tracking thread
        self._tracking_thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._tracking_thread.start()

        # Start system tray
        logger.info("Starting system tray...")
        self.tray_app.start(blocking=False)

        # Show notification
        if self.config.show_notifications:
            self.tray_app.show_notification("ActivityMonitor", "Tracking started")

        logger.info("ActivityMonitor started")

        # Run tkinter mainloop
        try:
            root = self._get_root()
            self._schedule_ui_updates(root)
            root.mainloop()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()

    def _schedule_ui_updates(self, root: tk.Tk):
        """Schedule periodic UI updates."""
        def update():
            if self._running:
                # Update tray with current state
                self.tray_app.update_project(self._current_project)
                self.tray_app.update_activity_state(self._is_active)
                root.after(1000, update)

        root.after(1000, update)

    def _tracking_loop(self):
        """Main tracking loop running in background thread."""
        logger.info("Tracking loop started")

        while self._running:
            try:
                if not self._paused:
                    self._track_activity()
            except Exception as e:
                logger.error(f"Error in tracking loop: {e}", exc_info=True)

            # Wait for next poll
            time.sleep(self.config.polling_interval_seconds)

        logger.info("Tracking loop stopped")

    def _clean_window_title(self, title: str) -> str:
        """Clean window title by removing noise like 'and X more pages'."""
        if not title:
            return title

        # Remove "and X more pages" from browser titles
        title = re.sub(r'\s+and\s+\d+\s+more\s+pages?\s*', ' ', title, flags=re.IGNORECASE)

        # Remove browser name suffixes for cleaner display
        browser_suffixes = [
            ' - Microsoft Edge', ' - Microsoft​ Edge',
            ' - Google Chrome', ' - Mozilla Firefox',
            ' - Brave', ' - Opera',
        ]
        for suffix in browser_suffixes:
            if title.endswith(suffix):
                title = title[:-len(suffix)]
                break

        # Clean up extra whitespace
        title = ' '.join(title.split())

        return title.strip()

    def _track_activity(self):
        """Track current activity and log it."""
        # Get current window
        window = self.window_tracker.get_active_window()

        # Handle case when no window is focused (desktop, etc.)
        if window is None:
            # Create a placeholder for desktop/no focus
            from window_tracker import WindowInfo
            window = WindowInfo(
                handle=0,
                title="Desktop",
                process_name="explorer.exe",
                process_id=0,
                cursor_in_window=True
            )

        # Check idle state
        idle_state = self.idle_monitor.update()
        is_idle = idle_state['is_idle']

        # Check camera presence (if enabled)
        camera_away = False
        if self.config.camera_enabled and self.camera_detector.is_enabled:
            camera_away = not self.camera_detector.is_present

        # Determine if actively working (keyboard/mouse activity)
        # Camera away overrides everything - if you're not at desk, you're not active
        is_active = not is_idle and not camera_away
        self._is_active = is_active

        # Clean window title before storing
        clean_title = self._clean_window_title(window.title)

        # Handle empty titles (desktop, etc.)
        if not clean_title or clean_title.lower() in ['program manager', '']:
            clean_title = "Desktop"

        # Always map to project
        project = None
        if self.config.visual_studio_solution_detection:
            project = self.project_mapper.map_activity(
                window.process_name,
                window.title  # Use original title for mapping (has more context)
            )

        # Apply custom display name mappings
        if project:
            project = self.project_mapper.apply_display_mappings(
                project,
                window.process_name,
                window.title
            )

        self._current_project = project

        # Log activity with cleaned title
        self.db.log_activity(
            window_title=clean_title,
            process_name=window.process_name,
            project_name=project,
            is_active=is_active,
            duration_seconds=self.config.polling_interval_seconds
        )

        # Console output for visibility
        status = "ACTIVE" if is_active else "IDLE"
        project_display = project or "Uncategorized"
        print(f"[{status}] {project_display}: {window.process_name} - {clean_title[:50]}...")

        # Log state changes
        if idle_state['became_idle']:
            logger.info(f"User became idle (was active for {idle_state['active_duration']:.0f}s)")
            print(f">>> STATUS: Now IDLE (yellow icon)")
            # Reset break timer when going idle (user took a break)
            self._last_break_time = datetime.now()
            self._break_reminder_shown = False
            self._continuous_work_start = None
        elif idle_state['became_active']:
            logger.info(f"User became active (was idle for {idle_state['idle_duration']:.0f}s)")
            print(f">>> STATUS: Now ACTIVE (green icon)")
            # Start tracking continuous work time
            if self._continuous_work_start is None:
                self._continuous_work_start = datetime.now()

        # Check break reminder
        if is_active:
            self._check_break_reminder()

        # Check daily summary
        self._check_daily_summary()

    def _check_break_reminder(self):
        """Check if it's time to remind user to take a break."""
        if not self.config.break_reminder_enabled:
            return

        if self._continuous_work_start is None:
            self._continuous_work_start = datetime.now()
            return

        # Calculate continuous work time
        work_duration = datetime.now() - self._continuous_work_start
        reminder_threshold = timedelta(minutes=self.config.break_reminder_interval_minutes)

        if work_duration >= reminder_threshold and not self._break_reminder_shown:
            # Show break reminder
            work_mins = int(work_duration.total_seconds() / 60)
            self.tray_app.show_notification(
                "Time for a Break!",
                f"You've been working for {work_mins} minutes. Take a short break to stay fresh!"
            )
            self._break_reminder_shown = True
            logger.info(f"Break reminder shown after {work_mins} minutes of work")

    def _check_daily_summary(self):
        """Check if it's time to show daily summary."""
        if not self.config.daily_summary_enabled:
            return

        now = datetime.now()

        # Reset flag if it's a new day
        if self._last_summary_date is None or self._last_summary_date.date() != now.date():
            self._daily_summary_shown_today = False

        # Check if it's the right hour and we haven't shown it today
        if now.hour == self.config.daily_summary_hour and not self._daily_summary_shown_today:
            self._show_daily_summary()
            self._daily_summary_shown_today = True
            self._last_summary_date = now

    def _show_daily_summary(self):
        """Show the daily summary notification."""
        try:
            summary = self.db.get_daily_summary(datetime.now())

            if not summary:
                return

            total_active = sum(s['active_seconds'] for s in summary)
            total_all = sum(s.get('total_seconds', s['active_seconds']) for s in summary)
            total_idle = total_all - total_active

            # Format time
            active_hours = total_active // 3600
            active_mins = (total_active % 3600) // 60
            idle_hours = total_idle // 3600
            idle_mins = (total_idle % 3600) // 60

            # Get top 3 projects
            top_projects = summary[:3]
            projects_text = ", ".join([p['project_name'] for p in top_projects])

            message = (
                f"Active: {active_hours}h {active_mins}m | Idle: {idle_hours}h {idle_mins}m\n"
                f"Top: {projects_text}"
            )

            self.tray_app.show_notification("Daily Summary", message)
            logger.info(f"Daily summary shown: {total_active}s active, {total_idle}s idle")

        except Exception as e:
            logger.error(f"Error showing daily summary: {e}")

    def stop(self):
        """Stop the activity monitor."""
        if not self._running:
            return

        logger.info("Stopping ActivityMonitor...")
        self._running = False

        # Stop camera detection
        if self.camera_detector.is_enabled:
            self.camera_detector.stop()

        # Stop tray
        self.tray_app.stop()

        # Wait for tracking thread
        if self._tracking_thread:
            self._tracking_thread.join(timeout=2.0)

        # Close UI windows
        if self.timeline_view:
            self.timeline_view.close()
        if self.report_view:
            self.report_view.close()
        if self.settings_view:
            self.settings_view.close()
        if self.mappings_view:
            self.mappings_view.close()

        # Destroy root window
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except Exception:
                pass

        logger.info("ActivityMonitor stopped")


def main():
    """Main entry point."""
    print("ActivityMonitor - Automatic Time Tracking")
    print("=" * 40)

    # Check for required dependencies
    try:
        import win32gui
    except ImportError:
        print("ERROR: pywin32 is required. Install it with:")
        print("  pip install pywin32")
        sys.exit(1)

    try:
        import pystray
    except ImportError:
        print("ERROR: pystray is required. Install it with:")
        print("  pip install pystray Pillow")
        sys.exit(1)

    # Start the monitor
    monitor = ActivityMonitor()

    try:
        monitor.start()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
