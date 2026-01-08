"""
Timeline view UI for ActivityMonitor.
Shows a visual breakdown of activities throughout the day.
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


# Color palette for projects
PROJECT_COLORS = [
    '#4A90D9',  # Blue
    '#50C878',  # Emerald
    '#FF6B6B',  # Coral
    '#9B59B6',  # Purple
    '#F39C12',  # Orange
    '#1ABC9C',  # Teal
    '#E74C3C',  # Red
    '#3498DB',  # Light Blue
    '#2ECC71',  # Green
    '#E67E22',  # Dark Orange
]


class TimelineView:
    """
    A visual timeline showing activities throughout the day.

    Displays a horizontal bar chart where each segment represents
    time spent on a project.
    """

    def __init__(self, database, parent: Optional[tk.Tk] = None):
        self.db = database
        self.parent = parent
        self.window: Optional[tk.Toplevel] = None
        self._color_map: Dict[str, str] = {}
        self._color_index = 0
        self._selected_date = datetime.now()

    def _get_project_color(self, project_name: str) -> str:
        """Get a consistent color for a project."""
        if project_name not in self._color_map:
            self._color_map[project_name] = PROJECT_COLORS[self._color_index % len(PROJECT_COLORS)]
            self._color_index += 1
        return self._color_map[project_name]

    def show(self, date: Optional[datetime] = None):
        """Show the timeline window."""
        print(">>> DEBUG: TimelineView.show() called")
        if date:
            self._selected_date = date

        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    print(">>> DEBUG: Timeline window exists, lifting")
                    self.window.deiconify()
                    self.window.lift()
                    self.window.focus_force()
                    self._refresh()
                    return
            except Exception:
                self.window = None

        print(">>> DEBUG: Creating new timeline window")
        self._create_window()
        self._refresh()

        # Force window to be visible and on top
        print(">>> DEBUG: Making timeline window visible")
        self.window.deiconify()
        self.window.attributes('-topmost', True)  # Force on top
        self.window.lift()
        self.window.focus_force()
        self.window.update()
        self.window.attributes('-topmost', False)  # Allow other windows on top later
        print(">>> DEBUG: Timeline window should now be visible")

    def _create_window(self):
        """Create the timeline window."""
        if self.parent:
            self.window = tk.Toplevel(self.parent)
        else:
            self.window = tk.Tk()

        self.window.title("ActivityMonitor - Timeline")
        self.window.geometry("900x600")
        self.window.configure(bg='#f0f0f0')

        # Handle window close button (X)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        # Main container
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header with date navigation
        self._create_header(main_frame)

        # Timeline canvas
        self._create_timeline_canvas(main_frame)

        # Paned window for resizable activity list and summary
        paned = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # Activity list
        activity_frame = ttk.Frame(paned)
        self._create_activity_list(activity_frame)
        paned.add(activity_frame, weight=3)

        # Summary panel
        summary_frame = ttk.Frame(paned)
        self._create_summary_panel(summary_frame)
        paned.add(summary_frame, weight=1)

    def _create_header(self, parent):
        """Create the header with date navigation."""
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 10))

        # Previous day button
        prev_btn = ttk.Button(header, text="< Previous", command=self._prev_day)
        prev_btn.pack(side=tk.LEFT)

        # Date label
        self._date_label = ttk.Label(
            header,
            text=self._selected_date.strftime("%A, %B %d, %Y"),
            font=('Segoe UI', 14, 'bold')
        )
        self._date_label.pack(side=tk.LEFT, expand=True)

        # Next day button
        next_btn = ttk.Button(header, text="Next >", command=self._next_day)
        next_btn.pack(side=tk.RIGHT)

        # Today button
        today_btn = ttk.Button(header, text="Today", command=self._go_today)
        today_btn.pack(side=tk.RIGHT, padx=5)

    def _create_timeline_canvas(self, parent):
        """Create the visual timeline canvas."""
        timeline_frame = ttk.LabelFrame(parent, text="Timeline", padding="5")
        timeline_frame.pack(fill=tk.X, pady=(0, 10))

        self._timeline_canvas = tk.Canvas(
            timeline_frame,
            height=80,
            bg='white',
            highlightthickness=1,
            highlightbackground='#ccc'
        )
        self._timeline_canvas.pack(fill=tk.X, padx=5, pady=5)

        # Bind resize event
        self._timeline_canvas.bind('<Configure>', lambda e: self._draw_timeline())

    def _create_activity_list(self, parent):
        """Create the scrollable activity list."""
        list_frame = ttk.LabelFrame(parent, text="Activities", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True)

        # Create treeview with scrollbar
        columns = ('time', 'duration', 'project', 'window')
        self._activity_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)

        self._activity_tree.heading('time', text='Time')
        self._activity_tree.heading('duration', text='Duration')
        self._activity_tree.heading('project', text='Project')
        self._activity_tree.heading('window', text='Window Title')

        self._activity_tree.column('time', width=80, minwidth=80)
        self._activity_tree.column('duration', width=80, minwidth=60)
        self._activity_tree.column('project', width=150, minwidth=100)
        self._activity_tree.column('window', width=400, minwidth=200)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._activity_tree.yview)
        self._activity_tree.configure(yscrollcommand=scrollbar.set)

        self._activity_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _create_summary_panel(self, parent):
        """Create the summary panel."""
        summary_frame = ttk.LabelFrame(parent, text="Summary", padding="5")
        summary_frame.pack(fill=tk.BOTH, expand=True)

        self._summary_text = tk.Text(
            summary_frame,
            wrap=tk.WORD,
            font=('Consolas', 10),
            bg='#fafafa'
        )
        self._summary_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _refresh(self):
        """Refresh the timeline with current date's data."""
        if self.window is None:
            return

        # Update date label
        self._date_label.config(text=self._selected_date.strftime("%A, %B %d, %Y"))

        # Get data from database
        print(f">>> DEBUG: Fetching activities for {self._selected_date.date()}")
        activities = self.db.get_activities_for_date(self._selected_date)
        summary = self.db.get_daily_summary(self._selected_date)
        print(f">>> DEBUG: Found {len(activities)} activities, {len(summary)} summary items")

        # Update timeline canvas
        self._draw_timeline(activities)

        # Update activity list
        self._update_activity_list(activities)

        # Update summary
        self._update_summary(summary)

    def _draw_timeline(self, activities: Optional[List[Dict]] = None):
        """Draw the timeline visualization."""
        canvas = self._timeline_canvas
        canvas.delete('all')

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 10:
            return

        # Draw time markers (hourly)
        bar_top = 30
        bar_height = height - 45
        margin = 30

        # Draw hour labels
        for hour in range(24):
            x = margin + (hour / 24) * (width - 2 * margin)
            if hour % 3 == 0:  # Every 3 hours
                canvas.create_text(x, 15, text=f"{hour:02d}:00", font=('Segoe UI', 8), fill='#666')
                canvas.create_line(x, bar_top, x, bar_top + bar_height, fill='#ddd', dash=(2, 2))

        # Draw background bar
        canvas.create_rectangle(
            margin, bar_top,
            width - margin, bar_top + bar_height,
            fill='#eee', outline='#ccc'
        )

        if not activities:
            canvas.create_text(
                width // 2, bar_top + bar_height // 2,
                text="No activities recorded",
                font=('Segoe UI', 10), fill='#999'
            )
            return

        # Group consecutive activities by project
        segments = self._group_activities_into_segments(activities)

        # Draw activity segments
        day_start = self._selected_date.replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_per_day = 24 * 60 * 60
        bar_width = width - 2 * margin

        for segment in segments:
            # Calculate position
            start_seconds = (segment['start'] - day_start).total_seconds()
            end_seconds = (segment['end'] - day_start).total_seconds()

            x1 = margin + (start_seconds / seconds_per_day) * bar_width
            x2 = margin + (end_seconds / seconds_per_day) * bar_width

            # Ensure minimum width
            if x2 - x1 < 2:
                x2 = x1 + 2

            # Use gray for idle periods, project color for active
            if segment['is_active']:
                color = self._get_project_color(segment['project'] or 'Uncategorized')
            else:
                color = '#CCCCCC'  # Gray for idle

            canvas.create_rectangle(
                x1, bar_top + 2,
                x2, bar_top + bar_height - 2,
                fill=color, outline='',
                tags=('segment',)
            )

    def _group_activities_into_segments(self, activities: List[Dict]) -> List[Dict]:
        """Group consecutive activities with same project into segments."""
        if not activities:
            return []

        segments = []
        current_segment = None

        for activity in activities:
            timestamp = datetime.fromisoformat(activity['timestamp'])
            project = activity['project_name'] or 'Uncategorized'
            is_active = activity['is_active']
            duration = activity['duration_seconds']

            if current_segment is None:
                current_segment = {
                    'project': project,
                    'start': timestamp,
                    'end': timestamp + timedelta(seconds=duration),
                    'is_active': is_active
                }
            elif current_segment['project'] == project and current_segment['is_active'] == is_active:
                # Extend current segment
                current_segment['end'] = timestamp + timedelta(seconds=duration)
            else:
                # Start new segment
                segments.append(current_segment)
                current_segment = {
                    'project': project,
                    'start': timestamp,
                    'end': timestamp + timedelta(seconds=duration),
                    'is_active': is_active
                }

        if current_segment:
            segments.append(current_segment)

        return segments

    def _update_activity_list(self, activities: List[Dict]):
        """Update the activity list treeview."""
        # Clear existing items
        for item in self._activity_tree.get_children():
            self._activity_tree.delete(item)

        # Group activities to reduce noise
        grouped = self._group_activities_for_list(activities)

        for activity in grouped:
            time_str = activity['start_time'].strftime('%H:%M')
            duration_str = self._format_duration(activity['duration'])
            project = activity['project'] or 'Uncategorized'
            window = activity['window_title'][:80] + '...' if len(activity['window_title']) > 80 else activity['window_title']

            # Add IDLE indicator to project name
            if not activity['is_active']:
                project = f"[IDLE] {project}"

            self._activity_tree.insert('', tk.END, values=(time_str, duration_str, project, window))

    def _group_activities_for_list(self, activities: List[Dict]) -> List[Dict]:
        """Group activities for display in list (merge consecutive same-project activities)."""
        if not activities:
            return []

        grouped = []
        current = None

        for activity in activities:
            # Show ALL activities, not just active ones
            timestamp = datetime.fromisoformat(activity['timestamp'])
            project = activity['project_name']
            window = activity['window_title']
            duration = activity['duration_seconds']
            is_active = activity['is_active']

            if current is None:
                current = {
                    'start_time': timestamp,
                    'project': project,
                    'window_title': window,
                    'duration': duration,
                    'is_active': is_active
                }
            elif current['project'] == project and current['window_title'] == window:
                # Merge with current
                current['duration'] += duration
            else:
                grouped.append(current)
                current = {
                    'start_time': timestamp,
                    'project': project,
                    'window_title': window,
                    'duration': duration,
                    'is_active': is_active
                }

        if current:
            grouped.append(current)

        return grouped

    def _update_summary(self, summary: List[Dict]):
        """Update the summary text."""
        self._summary_text.config(state=tk.NORMAL)
        self._summary_text.delete('1.0', tk.END)

        if not summary:
            self._summary_text.insert('1.0', "No activities recorded for this day.")
        else:
            total_active = sum(s['active_seconds'] for s in summary)
            total_all = sum(s.get('total_seconds', s['active_seconds']) for s in summary)
            total_idle = total_all - total_active

            lines = [
                f"Total Active Time: {self._format_duration(total_active)}",
                f"    |    Idle Time: {self._format_duration(total_idle)}\n\n"
            ]

            for item in summary:
                project = item['project_name']
                duration = self._format_duration(item['active_seconds'])
                lines.append(f"  {project}: {duration}\n")

            self._summary_text.insert('1.0', ''.join(lines))

        self._summary_text.config(state=tk.DISABLED)

    def _format_duration(self, seconds: int) -> str:
        """Format seconds as human-readable duration."""
        if seconds < 60:
            return f"{seconds}s"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _prev_day(self):
        """Go to previous day."""
        self._selected_date -= timedelta(days=1)
        self._safe_refresh()

    def _next_day(self):
        """Go to next day."""
        self._selected_date += timedelta(days=1)
        self._safe_refresh()

    def _go_today(self):
        """Go to today."""
        self._selected_date = datetime.now()
        self._safe_refresh()

    def _safe_refresh(self):
        """Refresh with proper UI update handling."""
        if self.window is None:
            return
        try:
            self.window.config(cursor="wait")
            self.window.update()
            self._refresh()
        except Exception as e:
            logger.error(f"Error refreshing timeline: {e}")
        finally:
            try:
                self.window.config(cursor="")
                self.window.update()
            except Exception:
                pass

    def close(self):
        """Close the timeline window."""
        print(">>> DEBUG: timeline close() called")
        if self.window:
            print(">>> DEBUG: Destroying timeline window")
            try:
                self.window.destroy()
                self.window = None
                print(">>> DEBUG: Timeline window destroyed")
            except Exception as e:
                print(f">>> DEBUG: Error closing timeline: {e}")


if __name__ == "__main__":
    # Test with mock data
    import sys
    sys.path.insert(0, str(__file__).rsplit('/', 2)[0])

    from database import Database

    db = Database(':memory:')

    # Add some test data
    from datetime import datetime

    now = datetime.now()
    for i in range(100):
        minutes_ago = 100 - i
        timestamp = now - timedelta(minutes=minutes_ago)

        # Simulate different projects
        if i < 30:
            project = "ProjectA"
            process = "Code.exe"
        elif i < 60:
            project = "ProjectB"
            process = "Code.exe"
        elif i < 80:
            project = None
            process = "chrome.exe"
        else:
            project = "ProjectA"
            process = "Code.exe"

        db.log_activity(
            window_title=f"test.py - {project or 'Browser'} - Visual Studio Code",
            process_name=process,
            project_name=project,
            is_active=i % 10 != 0,  # Every 10th is idle
            duration_seconds=60
        )

    timeline = TimelineView(db)
    timeline.show()

    if timeline.window:
        timeline.window.mainloop()
