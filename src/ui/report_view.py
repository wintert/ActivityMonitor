"""
Reports view UI for ActivityMonitor.
Shows daily and weekly summaries with export functionality.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    from ttkbootstrap import Toplevel
    from ttkbootstrap.dialogs import Messagebox
    import tkinter as tk
    from tkinter import filedialog
    TTKBOOTSTRAP_AVAILABLE = True
except ImportError:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    Toplevel = tk.Toplevel
    Messagebox = None
    TTKBOOTSTRAP_AVAILABLE = False

logger = logging.getLogger(__name__)


# Same color palette as timeline
PROJECT_COLORS = [
    '#4A90D9', '#50C878', '#FF6B6B', '#9B59B6', '#F39C12',
    '#1ABC9C', '#E74C3C', '#3498DB', '#2ECC71', '#E67E22',
]


class ReportView:
    """
    Report view showing daily and weekly summaries.

    Features:
    - Daily summary with project breakdown
    - Weekly summary with daily totals
    - CSV export functionality
    """

    def __init__(self, database, parent: Optional[tk.Tk] = None):
        self.db = database
        self.parent = parent
        self.window: Optional[tk.Toplevel] = None
        self._selected_date = datetime.now()
        self._view_mode = 'daily'  # 'daily' or 'weekly'
        self._color_map: Dict[str, str] = {}
        self._color_index = 0

    def _get_project_color(self, project_name: str) -> str:
        """Get a consistent color for a project."""
        if project_name not in self._color_map:
            self._color_map[project_name] = PROJECT_COLORS[self._color_index % len(PROJECT_COLORS)]
            self._color_index += 1
        return self._color_map[project_name]

    def show(self):
        """Show the report window."""
        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    self.window.deiconify()
                    self.window.lift()
                    self.window.focus_force()
                    self._refresh()
                    return
            except Exception:
                self.window = None

        self._create_window()
        self._refresh()

        # Force window to be visible and on top
        self.window.deiconify()
        self.window.attributes('-topmost', True)
        self.window.lift()
        self.window.focus_force()
        self.window.update()
        self.window.attributes('-topmost', False)

    def _create_window(self):
        """Create the report window."""
        if self.parent:
            self.window = Toplevel(self.parent)
        else:
            if TTKBOOTSTRAP_AVAILABLE:
                from ttkbootstrap import Window
                self.window = Window(themename="darkly")
            else:
                self.window = tk.Tk()

        self.window.title("ActivityMonitor - Reports")
        self.window.geometry("700x550")

        # Handle window close button (X)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        # Main container
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header with view toggle and date navigation
        self._create_header(main_frame)

        # Report content area
        self._create_report_area(main_frame)

        # Export buttons
        self._create_export_buttons(main_frame)

    def _create_header(self, parent):
        """Create the header with view toggle and date navigation."""
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 10))

        # View mode toggle
        mode_frame = ttk.Frame(header)
        mode_frame.pack(side=tk.LEFT)

        self._daily_btn = ttk.Button(
            mode_frame, text="Daily",
            command=lambda: self._set_view_mode('daily')
        )
        self._daily_btn.pack(side=tk.LEFT, padx=(0, 5))

        self._weekly_btn = ttk.Button(
            mode_frame, text="Weekly",
            command=lambda: self._set_view_mode('weekly')
        )
        self._weekly_btn.pack(side=tk.LEFT)

        # Navigation buttons
        nav_frame = ttk.Frame(header)
        nav_frame.pack(side=tk.RIGHT)

        ttk.Button(nav_frame, text="<", command=self._prev_period, width=3).pack(side=tk.LEFT)

        self._date_label = ttk.Label(
            nav_frame,
            text="",
            font=('Segoe UI', 11, 'bold'),
            width=25,
            anchor='center'
        )
        self._date_label.pack(side=tk.LEFT, padx=10)

        ttk.Button(nav_frame, text=">", command=self._next_period, width=3).pack(side=tk.LEFT)
        ttk.Button(nav_frame, text="Today", command=self._go_today).pack(side=tk.LEFT, padx=(10, 0))

    def _create_report_area(self, parent):
        """Create the main report display area."""
        report_frame = ttk.LabelFrame(parent, text="Report", padding="10")
        report_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Summary stats at top
        stats_frame = ttk.Frame(report_frame)
        stats_frame.pack(fill=tk.X, pady=(0, 10))

        self._total_label = ttk.Label(
            stats_frame,
            text="Total Active Time: --",
            font=('Segoe UI', 12, 'bold')
        )
        self._total_label.pack(side=tk.LEFT)

        self._idle_label = ttk.Label(
            stats_frame,
            text="Idle Time: --",
            font=('Segoe UI', 10),
            foreground='#666'
        )
        self._idle_label.pack(side=tk.LEFT, padx=(20, 0))

        # Project breakdown table
        columns = ('project', 'time', 'percentage')
        self._report_tree = ttk.Treeview(
            report_frame,
            columns=columns,
            show='headings',
            height=12
        )

        self._report_tree.heading('project', text='Project')
        self._report_tree.heading('time', text='Time')
        self._report_tree.heading('percentage', text='%')

        self._report_tree.column('project', width=300, minwidth=150)
        self._report_tree.column('time', width=120, minwidth=80, anchor='center')
        self._report_tree.column('percentage', width=80, minwidth=60, anchor='center')

        scrollbar = ttk.Scrollbar(report_frame, orient=tk.VERTICAL, command=self._report_tree.yview)
        self._report_tree.configure(yscrollcommand=scrollbar.set)

        self._report_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _create_export_buttons(self, parent):
        """Create export buttons."""
        export_frame = ttk.Frame(parent)
        export_frame.pack(fill=tk.X)

        ttk.Button(
            export_frame,
            text="Export Summary to CSV",
            command=self._export_summary
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            export_frame,
            text="Export Detailed Timeline to CSV",
            command=self._export_timeline
        ).pack(side=tk.LEFT)

        ttk.Button(
            export_frame,
            text="Copy to Clipboard",
            command=self._copy_to_clipboard
        ).pack(side=tk.RIGHT)

    def _set_view_mode(self, mode: str):
        """Set the view mode (daily or weekly)."""
        self._view_mode = mode
        self._refresh()

    def _refresh(self):
        """Refresh the report display."""
        if self.window is None:
            return

        # Update date label
        if self._view_mode == 'daily':
            self._date_label.config(text=self._selected_date.strftime("%A, %B %d, %Y"))
            data = self.db.get_daily_summary(self._selected_date)
        else:
            # Weekly view - start from Monday
            start = self._selected_date - timedelta(days=self._selected_date.weekday())
            end = start + timedelta(days=6)
            self._date_label.config(
                text=f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"
            )
            data = self._get_weekly_data(start)

        # Update totals (active and idle)
        total_active = sum(item.get('active_seconds', 0) for item in data)
        total_all = sum(item.get('total_seconds', item.get('active_seconds', 0)) for item in data)
        total_idle = total_all - total_active

        self._total_label.config(text=f"Total Active Time: {self._format_duration(total_active)}")
        self._idle_label.config(text=f"Idle Time: {self._format_duration(total_idle)}")

        # Update table
        for item in self._report_tree.get_children():
            self._report_tree.delete(item)

        for item in data:
            project = item['project_name']
            seconds = item.get('active_seconds', 0)
            time_str = self._format_duration(seconds)
            pct = (seconds / total_active * 100) if total_active > 0 else 0

            self._report_tree.insert(
                '', tk.END,
                values=(project, time_str, f"{pct:.1f}%")
            )

    def _get_weekly_data(self, start_date: datetime) -> List[Dict]:
        """Get aggregated weekly data."""
        # Get raw weekly data
        raw_data = self.db.get_weekly_summary(start_date)

        # Aggregate by project
        project_totals = {}
        for item in raw_data:
            project = item['project_name']
            seconds = item.get('active_seconds', 0)
            project_totals[project] = project_totals.get(project, 0) + seconds

        # Convert to list format
        return [
            {'project_name': project, 'active_seconds': seconds}
            for project, seconds in sorted(
                project_totals.items(),
                key=lambda x: x[1],
                reverse=True
            )
        ]

    def _format_duration(self, seconds: int) -> str:
        """Format seconds as human-readable duration."""
        if seconds < 60:
            return f"{seconds}s"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _prev_period(self):
        """Go to previous period."""
        if self._view_mode == 'daily':
            self._selected_date -= timedelta(days=1)
        else:
            self._selected_date -= timedelta(weeks=1)
        self._refresh()

    def _next_period(self):
        """Go to next period."""
        if self._view_mode == 'daily':
            self._selected_date += timedelta(days=1)
        else:
            self._selected_date += timedelta(weeks=1)
        self._refresh()

    def _go_today(self):
        """Go to today/this week."""
        self._selected_date = datetime.now()
        self._refresh()

    def _export_summary(self):
        """Export summary to CSV."""
        if self._view_mode == 'daily':
            default_name = f"activity_summary_{self._selected_date.strftime('%Y-%m-%d')}.csv"
        else:
            start = self._selected_date - timedelta(days=self._selected_date.weekday())
            default_name = f"activity_summary_week_{start.strftime('%Y-%m-%d')}.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name
        )

        if filepath:
            try:
                self.db.export_to_csv(self._selected_date, filepath)
                self._show_info("Export Complete", f"Summary exported to:\n{filepath}")
            except Exception as e:
                self._show_error("Export Error", f"Failed to export: {e}")

    def _export_timeline(self):
        """Export detailed timeline to CSV."""
        default_name = f"activity_timeline_{self._selected_date.strftime('%Y-%m-%d')}.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_name
        )

        if filepath:
            try:
                self.db.export_timeline_to_csv(self._selected_date, filepath)
                self._show_info("Export Complete", f"Timeline exported to:\n{filepath}")
            except Exception as e:
                self._show_error("Export Error", f"Failed to export: {e}")

    def _copy_to_clipboard(self):
        """Copy summary to clipboard as text."""
        if self._view_mode == 'daily':
            data = self.db.get_daily_summary(self._selected_date)
            header = f"Activity Report - {self._selected_date.strftime('%Y-%m-%d')}\n"
        else:
            start = self._selected_date - timedelta(days=self._selected_date.weekday())
            data = self._get_weekly_data(start)
            header = f"Activity Report - Week of {start.strftime('%Y-%m-%d')}\n"

        lines = [header, "-" * 40 + "\n"]
        total_active = 0
        total_all = 0

        for item in data:
            project = item['project_name']
            seconds = item.get('active_seconds', 0)
            total_active += seconds
            total_all += item.get('total_seconds', seconds)
            time_str = self._format_duration(seconds)
            lines.append(f"{project}: {time_str}\n")

        total_idle = total_all - total_active
        lines.append("-" * 40 + "\n")
        lines.append(f"Total Active: {self._format_duration(total_active)}\n")
        lines.append(f"Total Idle: {self._format_duration(total_idle)}\n")

        text = ''.join(lines)

        self.window.clipboard_clear()
        self.window.clipboard_append(text)
        self._show_info("Copied", "Report copied to clipboard!")

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

    def close(self):
        """Close the report window."""
        if self.window:
            self.window.destroy()
            self.window = None


if __name__ == "__main__":
    # Test with mock data
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])

    from database import Database

    db = Database(':memory:')

    # Add some test data
    now = datetime.now()
    for i in range(200):
        minutes_ago = 200 - i
        timestamp = now - timedelta(minutes=minutes_ago)

        if i < 60:
            project = "ProjectA"
        elif i < 120:
            project = "ProjectB"
        elif i < 160:
            project = "ProjectC"
        else:
            project = "ProjectA"

        db.log_activity(
            window_title=f"test.py - {project}",
            process_name="Code.exe",
            project_name=project,
            is_active=i % 10 != 0,
            duration_seconds=60
        )

    report = ReportView(db)
    report.show()

    if report.window:
        report.window.mainloop()
