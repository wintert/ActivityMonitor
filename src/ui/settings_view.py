"""
Settings view UI for ActivityMonitor.
Allows users to configure application settings.
"""

from typing import Optional, Callable
import logging

import tkinter as tk
from tkinter import messagebox

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    from ttkbootstrap import Toplevel
    from ttkbootstrap.dialogs import Messagebox
    TTKBOOTSTRAP_AVAILABLE = True
except ImportError:
    from tkinter import ttk
    Toplevel = tk.Toplevel
    Messagebox = None
    TTKBOOTSTRAP_AVAILABLE = False

logger = logging.getLogger(__name__)


class SettingsView:
    """
    Settings dialog for configuring ActivityMonitor.

    Settings include:
    - Idle detection threshold
    - Camera presence detection toggle and settings
    - Polling interval
    - Startup options
    """

    def __init__(self, config_manager, parent: Optional[tk.Tk] = None,
                 on_save: Optional[Callable] = None, camera_detector=None):
        self.config_manager = config_manager
        self.parent = parent
        self.on_save = on_save
        self.camera_detector = camera_detector
        self.window: Optional[tk.Toplevel] = None

        # Tkinter variables for form fields
        self._vars = {}

    def show(self):
        """Show the settings window."""
        print(">>> DEBUG: SettingsView.show() called")
        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    print(">>> DEBUG: Window exists, lifting")
                    self.window.deiconify()
                    self.window.lift()
                    self.window.focus_force()
                    return
            except Exception:
                self.window = None

        print(">>> DEBUG: Creating new settings window")
        self._create_window()
        self._load_current_settings()

        # Force window to be visible and on top
        print(">>> DEBUG: Making window visible")
        print(f">>> DEBUG: Window state before: {self.window.state()}")
        print(f">>> DEBUG: Window geometry: {self.window.geometry()}")
        self.window.deiconify()
        self.window.attributes('-topmost', True)  # Force on top
        self.window.lift()
        self.window.focus_force()
        self.window.update_idletasks()
        self.window.update()
        self.window.attributes('-topmost', False)  # Allow other windows on top later
        print(f">>> DEBUG: Window state after: {self.window.state()}")
        print(f">>> DEBUG: Window winfo_viewable: {self.window.winfo_viewable()}")
        print(">>> DEBUG: Window should now be visible")

    def _create_window(self):
        """Create the settings window."""
        # Always create as Toplevel - works better with tray app
        if self.parent:
            self.window = Toplevel(self.parent)
        else:
            if TTKBOOTSTRAP_AVAILABLE:
                from ttkbootstrap import Window
                self.window = Window(themename="darkly")
            else:
                self.window = tk.Toplevel()

        self.window.title("ActivityMonitor - Settings")
        self.window.geometry("520x750")
        self.window.resizable(True, True)

        # Handle window close button (X)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        # Main container with scrollbar
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Create sections
        self._create_idle_section(main_frame)
        self._create_camera_section(main_frame)
        self._create_tracking_section(main_frame)
        self._create_theme_section(main_frame)
        self._create_break_reminder_section(main_frame)
        self._create_daily_summary_section(main_frame)
        self._create_startup_section(main_frame)

        # Buttons
        self._create_buttons(main_frame)

    def _create_idle_section(self, parent):
        """Create idle detection settings section."""
        frame = ttk.LabelFrame(parent, text="Idle Detection")
        frame.pack(fill=tk.X, pady=(0, 10))

        # Idle timeout
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=2)

        ttk.Label(row, text="Idle timeout:", width=20, anchor='w').pack(side=tk.LEFT)

        self._vars['idle_timeout'] = tk.StringVar()
        timeout_combo = ttk.Combobox(
            row,
            textvariable=self._vars['idle_timeout'],
            values=['1 minute', '2 minutes', '3 minutes', '5 minutes', '10 minutes'],
            state='readonly',
            width=15
        )
        timeout_combo.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(
            frame,
            text="Time without keyboard/mouse activity before marking as idle.",
            font=('Segoe UI', 8),
            foreground='#666'
        ).pack(anchor='w', pady=(5, 0))

    def _create_camera_section(self, parent):
        """Create camera presence detection settings section."""
        frame = ttk.LabelFrame(parent, text="Camera Presence Detection")
        frame.pack(fill=tk.X, pady=(0, 10))

        # Enable camera
        self._vars['camera_enabled'] = tk.BooleanVar()
        ttk.Checkbutton(
            frame,
            text="Enable camera presence detection",
            variable=self._vars['camera_enabled'],
            command=self._toggle_camera_options
        ).pack(anchor='w')

        ttk.Label(
            frame,
            text="Uses your webcam to detect when you're away from your desk.",
            font=('Segoe UI', 8),
            foreground='#666'
        ).pack(anchor='w', pady=(0, 10))

        # Camera options (sub-frame)
        self._camera_options_frame = ttk.Frame(frame)
        self._camera_options_frame.pack(fill=tk.X)

        # Check interval
        row1 = ttk.Frame(self._camera_options_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="Check interval:", width=20, anchor='w').pack(side=tk.LEFT)

        self._vars['camera_interval'] = tk.StringVar()
        interval_combo = ttk.Combobox(
            row1,
            textvariable=self._vars['camera_interval'],
            values=['5 seconds', '10 seconds', '15 seconds', '30 seconds'],
            state='readonly',
            width=15
        )
        interval_combo.pack(side=tk.LEFT, padx=(5, 0))

        # Away threshold
        row2 = ttk.Frame(self._camera_options_frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="Away threshold:", width=20, anchor='w').pack(side=tk.LEFT)

        self._vars['camera_threshold'] = tk.StringVar()
        threshold_combo = ttk.Combobox(
            row2,
            textvariable=self._vars['camera_threshold'],
            values=['15 seconds', '30 seconds', '45 seconds', '60 seconds'],
            state='readonly',
            width=15
        )
        threshold_combo.pack(side=tk.LEFT, padx=(5, 0))

        # Camera device
        row3 = ttk.Frame(self._camera_options_frame)
        row3.pack(fill=tk.X, pady=2)

        ttk.Label(row3, text="Camera device:", width=20, anchor='w').pack(side=tk.LEFT)

        self._vars['camera_device'] = tk.StringVar()
        device_combo = ttk.Combobox(
            row3,
            textvariable=self._vars['camera_device'],
            values=['Camera 0 (Default)', 'Camera 1', 'Camera 2'],
            state='readonly',
            width=15
        )
        device_combo.pack(side=tk.LEFT, padx=(5, 0))

        # Test camera button
        row4 = ttk.Frame(self._camera_options_frame)
        row4.pack(fill=tk.X, pady=(10, 2))

        self._test_camera_btn = ttk.Button(
            row4,
            text="Test Camera Preview",
            command=self._test_camera
        )
        self._test_camera_btn.pack(side=tk.LEFT)

        ttk.Label(
            row4,
            text="Opens a 10-second preview window",
            font=('Segoe UI', 8),
            foreground='#666'
        ).pack(side=tk.LEFT, padx=(10, 0))

    def _test_camera(self):
        """Open camera preview window."""
        if self.camera_detector is None:
            messagebox.showwarning("Camera", "Camera detector not available.")
            return

        if not self.camera_detector.is_available:
            messagebox.showwarning("Camera", "OpenCV not installed. Install with:\npip install opencv-python")
            return

        # Get selected camera index
        device_map = {'Camera 0 (Default)': 0, 'Camera 1': 1, 'Camera 2': 2}
        camera_index = device_map.get(self._vars['camera_device'].get(), 0)

        # Temporarily set camera index for preview
        old_index = self.camera_detector.camera_index
        self.camera_detector.camera_index = camera_index

        messagebox.showinfo("Camera Preview",
                           "A preview window will open for 10 seconds.\n"
                           "Press 'Q' to close it early.\n\n"
                           "Green rectangle = Face detected\n"
                           "Click OK to start.")

        success = self.camera_detector.show_preview(duration_seconds=10)

        # Restore camera index
        self.camera_detector.camera_index = old_index

        if not success:
            messagebox.showerror("Camera Error", "Could not open camera. Check if it's connected and not in use.")

    def _create_tracking_section(self, parent):
        """Create tracking settings section."""
        frame = ttk.LabelFrame(parent, text="Activity Tracking")
        frame.pack(fill=tk.X, pady=(0, 10))

        # Polling interval
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=2)

        ttk.Label(row, text="Polling interval:", width=20, anchor='w').pack(side=tk.LEFT)

        self._vars['polling_interval'] = tk.StringVar()
        interval_combo = ttk.Combobox(
            row,
            textvariable=self._vars['polling_interval'],
            values=['3 seconds', '5 seconds', '10 seconds', '15 seconds'],
            state='readonly',
            width=15
        )
        interval_combo.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(
            frame,
            text="How often to check the active window. Lower = more precise, higher = less CPU.",
            font=('Segoe UI', 8),
            foreground='#666'
        ).pack(anchor='w', pady=(5, 0))

        # Visual Studio detection
        self._vars['vs_detection'] = tk.BooleanVar()
        ttk.Checkbutton(
            frame,
            text="Detect project from Visual Studio solution name",
            variable=self._vars['vs_detection']
        ).pack(anchor='w', pady=(10, 0))

    def _create_theme_section(self, parent):
        """Create theme settings section."""
        frame = ttk.LabelFrame(parent, text="Appearance")
        frame.pack(fill=tk.X, pady=(0, 10))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=2)

        ttk.Label(row, text="Theme:", width=20, anchor='w').pack(side=tk.LEFT)

        self._vars['theme'] = tk.StringVar()
        theme_combo = ttk.Combobox(
            row,
            textvariable=self._vars['theme'],
            values=['darkly', 'superhero', 'cyborg', 'vapor', 'solar',
                    'litera', 'flatly', 'minty', 'cosmo', 'journal'],
            state='readonly',
            width=15
        )
        theme_combo.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(
            frame,
            text="Requires restart to apply. Dark themes: darkly, superhero, cyborg, vapor, solar.",
            font=('Segoe UI', 8),
            foreground='#888'
        ).pack(anchor='w', pady=(5, 0))

    def _create_break_reminder_section(self, parent):
        """Create break reminder settings section."""
        frame = ttk.LabelFrame(parent, text="Break Reminders")
        frame.pack(fill=tk.X, pady=(0, 10))

        # Enable break reminders
        self._vars['break_reminder_enabled'] = tk.BooleanVar()
        ttk.Checkbutton(
            frame,
            text="Enable break reminders",
            variable=self._vars['break_reminder_enabled']
        ).pack(anchor='w')

        # Interval
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=(5, 2))

        ttk.Label(row, text="Remind after:", width=20, anchor='w').pack(side=tk.LEFT)

        self._vars['break_interval'] = tk.StringVar()
        interval_combo = ttk.Combobox(
            row,
            textvariable=self._vars['break_interval'],
            values=['25 minutes', '30 minutes', '45 minutes', '50 minutes', '60 minutes'],
            state='readonly',
            width=15
        )
        interval_combo.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(
            frame,
            text="Get reminded to take a break after continuous work. Resets when idle.",
            font=('Segoe UI', 8),
            foreground='#888'
        ).pack(anchor='w', pady=(5, 0))

    def _create_daily_summary_section(self, parent):
        """Create daily summary settings section."""
        frame = ttk.LabelFrame(parent, text="Daily Summary")
        frame.pack(fill=tk.X, pady=(0, 10))

        # Enable daily summary
        self._vars['daily_summary_enabled'] = tk.BooleanVar()
        ttk.Checkbutton(
            frame,
            text="Show daily summary notification",
            variable=self._vars['daily_summary_enabled']
        ).pack(anchor='w')

        # Time
        row = ttk.Frame(frame)
        row.pack(fill=tk.X, pady=(5, 2))

        ttk.Label(row, text="Summary time:", width=20, anchor='w').pack(side=tk.LEFT)

        self._vars['daily_summary_hour'] = tk.StringVar()
        hour_combo = ttk.Combobox(
            row,
            textvariable=self._vars['daily_summary_hour'],
            values=['5 PM', '6 PM', '7 PM', '8 PM', '9 PM'],
            state='readonly',
            width=15
        )
        hour_combo.pack(side=tk.LEFT, padx=(5, 0))

        ttk.Label(
            frame,
            text="Shows total active time, idle time, and top projects for the day.",
            font=('Segoe UI', 8),
            foreground='#888'
        ).pack(anchor='w', pady=(5, 0))

    def _create_startup_section(self, parent):
        """Create startup settings section."""
        frame = ttk.LabelFrame(parent, text="Startup")
        frame.pack(fill=tk.X, pady=(0, 10))

        self._vars['start_minimized'] = tk.BooleanVar()
        ttk.Checkbutton(
            frame,
            text="Start minimized to system tray",
            variable=self._vars['start_minimized']
        ).pack(anchor='w')

        self._vars['start_with_windows'] = tk.BooleanVar()
        ttk.Checkbutton(
            frame,
            text="Start with Windows (coming soon)",
            variable=self._vars['start_with_windows'],
            state='disabled'
        ).pack(anchor='w')

        self._vars['show_notifications'] = tk.BooleanVar()
        ttk.Checkbutton(
            frame,
            text="Show notifications for state changes",
            variable=self._vars['show_notifications']
        ).pack(anchor='w')

    def _create_buttons(self, parent):
        """Create action buttons."""
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(
            button_frame,
            text="Reset to Defaults",
            command=self._reset_to_defaults
        ).pack(side=tk.LEFT)

        ttk.Button(
            button_frame,
            text="Cancel",
            command=self.close
        ).pack(side=tk.RIGHT, padx=(5, 0))

        ttk.Button(
            button_frame,
            text="Save",
            command=self._save_settings
        ).pack(side=tk.RIGHT)

    def _toggle_camera_options(self):
        """Enable/disable camera options based on checkbox."""
        enabled = self._vars['camera_enabled'].get()
        state = 'normal' if enabled else 'disabled'

        for child in self._camera_options_frame.winfo_children():
            for widget in child.winfo_children():
                if isinstance(widget, (ttk.Combobox, ttk.Entry)):
                    widget.configure(state='readonly' if enabled else 'disabled')

    def _load_current_settings(self):
        """Load current settings into form."""
        config = self.config_manager.config

        # Idle timeout
        timeout_map = {1: '1 minute', 2: '2 minutes', 3: '3 minutes', 5: '5 minutes', 10: '10 minutes'}
        self._vars['idle_timeout'].set(timeout_map.get(config.idle_timeout_minutes, '3 minutes'))

        # Camera settings
        self._vars['camera_enabled'].set(config.camera_enabled)

        interval_map = {5: '5 seconds', 10: '10 seconds', 15: '15 seconds', 30: '30 seconds'}
        self._vars['camera_interval'].set(interval_map.get(config.camera_check_interval_seconds, '10 seconds'))

        threshold_map = {15: '15 seconds', 30: '30 seconds', 45: '45 seconds', 60: '60 seconds'}
        self._vars['camera_threshold'].set(threshold_map.get(config.camera_away_threshold_seconds, '30 seconds'))

        device_map = {0: 'Camera 0 (Default)', 1: 'Camera 1', 2: 'Camera 2'}
        self._vars['camera_device'].set(device_map.get(config.camera_device_index, 'Camera 0 (Default)'))

        # Tracking settings
        polling_map = {3: '3 seconds', 5: '5 seconds', 10: '10 seconds', 15: '15 seconds'}
        self._vars['polling_interval'].set(polling_map.get(config.polling_interval_seconds, '5 seconds'))

        self._vars['vs_detection'].set(config.visual_studio_solution_detection)

        # Theme settings
        self._vars['theme'].set(config.theme)

        # Break reminder settings
        self._vars['break_reminder_enabled'].set(config.break_reminder_enabled)
        break_map = {25: '25 minutes', 30: '30 minutes', 45: '45 minutes', 50: '50 minutes', 60: '60 minutes'}
        self._vars['break_interval'].set(break_map.get(config.break_reminder_interval_minutes, '50 minutes'))

        # Daily summary settings
        self._vars['daily_summary_enabled'].set(config.daily_summary_enabled)
        hour_map = {17: '5 PM', 18: '6 PM', 19: '7 PM', 20: '8 PM', 21: '9 PM'}
        self._vars['daily_summary_hour'].set(hour_map.get(config.daily_summary_hour, '6 PM'))

        # Startup settings
        self._vars['start_minimized'].set(config.start_minimized)
        self._vars['start_with_windows'].set(config.start_with_windows)
        self._vars['show_notifications'].set(config.show_notifications)

        # Toggle camera options
        self._toggle_camera_options()

    def _save_settings(self):
        """Save settings to config."""
        try:
            # Parse values
            idle_map = {'1 minute': 1, '2 minutes': 2, '3 minutes': 3, '5 minutes': 5, '10 minutes': 10}
            interval_map = {'5 seconds': 5, '10 seconds': 10, '15 seconds': 15, '30 seconds': 30}
            threshold_map = {'15 seconds': 15, '30 seconds': 30, '45 seconds': 45, '60 seconds': 60}
            polling_map = {'3 seconds': 3, '5 seconds': 5, '10 seconds': 10, '15 seconds': 15}
            device_map = {'Camera 0 (Default)': 0, 'Camera 1': 1, 'Camera 2': 2}
            break_map = {'25 minutes': 25, '30 minutes': 30, '45 minutes': 45, '50 minutes': 50, '60 minutes': 60}
            hour_map = {'5 PM': 17, '6 PM': 18, '7 PM': 19, '8 PM': 20, '9 PM': 21}

            self.config_manager.update(
                idle_timeout_minutes=idle_map.get(self._vars['idle_timeout'].get(), 3),
                camera_enabled=self._vars['camera_enabled'].get(),
                camera_check_interval_seconds=interval_map.get(self._vars['camera_interval'].get(), 10),
                camera_away_threshold_seconds=threshold_map.get(self._vars['camera_threshold'].get(), 30),
                camera_device_index=device_map.get(self._vars['camera_device'].get(), 0),
                polling_interval_seconds=polling_map.get(self._vars['polling_interval'].get(), 5),
                visual_studio_solution_detection=self._vars['vs_detection'].get(),
                theme=self._vars['theme'].get(),
                break_reminder_enabled=self._vars['break_reminder_enabled'].get(),
                break_reminder_interval_minutes=break_map.get(self._vars['break_interval'].get(), 50),
                daily_summary_enabled=self._vars['daily_summary_enabled'].get(),
                daily_summary_hour=hour_map.get(self._vars['daily_summary_hour'].get(), 18),
                start_minimized=self._vars['start_minimized'].get(),
                start_with_windows=self._vars['start_with_windows'].get(),
                show_notifications=self._vars['show_notifications'].get()
            )

            if self.on_save:
                self.on_save()

            self._show_info("Settings Saved", "Your settings have been saved.")
            self.close()

        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            self._show_error("Error", f"Failed to save settings: {e}")

    def _reset_to_defaults(self):
        """Reset all settings to defaults."""
        if self._show_yesno("Reset Settings", "Reset all settings to defaults?"):
            self.config_manager.reset_to_defaults()
            self._load_current_settings()

    def _show_info(self, title: str, message: str):
        """Show info message using appropriate dialog."""
        if TTKBOOTSTRAP_AVAILABLE and Messagebox:
            Messagebox.show_info(message, title=title, parent=self.window)
        else:
            messagebox.showinfo(title, message)

    def _show_error(self, title: str, message: str):
        """Show error message using appropriate dialog."""
        if TTKBOOTSTRAP_AVAILABLE and Messagebox:
            Messagebox.show_error(message, title=title, parent=self.window)
        else:
            messagebox.showerror(title, message)

    def _show_yesno(self, title: str, message: str) -> bool:
        """Show yes/no dialog using appropriate dialog."""
        if TTKBOOTSTRAP_AVAILABLE and Messagebox:
            return Messagebox.yesno(message, title=title, parent=self.window) == "Yes"
        else:
            return messagebox.askyesno(title, message)

    def close(self):
        """Close the settings window."""
        if self.window:
            self.window.destroy()
            self.window = None


if __name__ == "__main__":
    # Test settings view
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])

    from database import Database
    from config import ConfigManager

    db = Database(':memory:')
    config_manager = ConfigManager(db)

    def on_save():
        print("Settings saved!")
        print(f"New config: {config_manager.config}")

    settings = SettingsView(config_manager, on_save=on_save)
    settings.show()

    if settings.window:
        settings.window.mainloop()
