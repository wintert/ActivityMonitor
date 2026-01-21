"""
Reports view UI for ActivityMonitor.
Shows daily and weekly summaries with export functionality.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

import tkinter as tk
from tkinter import filedialog, messagebox

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

# Matplotlib for charts
try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

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
    - Daily summary with activity/category breakdown
    - Weekly summary with daily totals
    - CSV export functionality
    - Hidden categories filtering (e.g., System/Explorer hidden by default)
    """

    def __init__(self, database, parent: Optional[tk.Tk] = None, config_manager=None):
        self.db = database
        self.parent = parent
        self.config_manager = config_manager
        self.window: Optional[tk.Toplevel] = None
        self._selected_date = datetime.now()
        self._view_mode = 'daily'  # 'daily' or 'weekly'
        self._group_by = 'activity'  # 'activity', 'category', or 'project'
        self._color_map: Dict[str, str] = {}
        self._color_index = 0

    def _get_hidden_categories(self) -> List[str]:
        """Get list of categories to hide from reports."""
        if self.config_manager:
            return self.config_manager.config.hidden_categories
        return ["System"]  # Default: hide System (File Explorer, etc.)

    def _get_hidden_apps(self) -> List[str]:
        """Get list of app patterns to hide from reports."""
        if self.config_manager:
            return self.config_manager.config.hidden_apps
        return []

    def _get_min_activity_seconds(self) -> int:
        """Get minimum activity seconds threshold."""
        if self.config_manager:
            return self.config_manager.config.minimum_activity_seconds
        return 0

    def _get_time_rounding_minutes(self) -> int:
        """Get time rounding setting (0 = no rounding)."""
        if self.config_manager:
            return self.config_manager.config.time_rounding_minutes
        return 0

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
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Header with view toggle and date navigation (top)
        self._create_header(main_frame)

        # Export buttons (bottom - pack with side=BOTTOM before notebook)
        self._create_export_buttons(main_frame)

        # Report content area (middle - expands to fill remaining space)
        self._create_report_area(main_frame)

    def _create_header(self, parent):
        """Create the header with view toggle and date navigation."""
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 10))

        # View mode toggle (Daily/Weekly)
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

        # Separator
        ttk.Separator(mode_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)

        # Group by toggle (Activity/Category)
        self._activity_btn = ttk.Button(
            mode_frame, text="By Activity",
            command=lambda: self._set_group_by('activity')
        )
        self._activity_btn.pack(side=tk.LEFT, padx=(0, 5))

        self._category_btn = ttk.Button(
            mode_frame, text="By Category",
            command=lambda: self._set_group_by('category')
        )
        self._category_btn.pack(side=tk.LEFT, padx=(0, 5))

        self._project_btn = ttk.Button(
            mode_frame, text="By Project",
            command=lambda: self._set_group_by('project')
        )
        self._project_btn.pack(side=tk.LEFT)

        # Separator before expand/collapse buttons
        ttk.Separator(mode_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)

        # Expand/Collapse buttons (for category view)
        self._expand_btn = ttk.Button(
            mode_frame, text="+",
            command=self._expand_all,
            width=3
        )
        self._expand_btn.pack(side=tk.LEFT, padx=(0, 2))

        self._collapse_btn = ttk.Button(
            mode_frame, text="-",
            command=self._collapse_all,
            width=3
        )
        self._collapse_btn.pack(side=tk.LEFT)

        # Navigation buttons
        nav_frame = ttk.Frame(header)
        nav_frame.pack(side=tk.RIGHT)

        ttk.Button(nav_frame, text="◀", command=self._prev_period, width=3).pack(side=tk.LEFT)

        self._date_label = ttk.Label(
            nav_frame,
            text="",
            font=('Segoe UI', 11, 'bold'),
            width=25,
            anchor='center'
        )
        self._date_label.pack(side=tk.LEFT, padx=10)

        ttk.Button(nav_frame, text="▶", command=self._next_period, width=3).pack(side=tk.LEFT)
        ttk.Button(nav_frame, text="📅 Today", command=self._go_today).pack(side=tk.LEFT, padx=(10, 0))

    def _create_report_area(self, parent):
        """Create the main report display area with tabs for table and charts."""
        # Summary stats at top
        stats_frame = ttk.Frame(parent)
        stats_frame.pack(fill=tk.X, pady=(0, 10))

        # Left side: Active and Idle time
        time_stats = ttk.Frame(stats_frame)
        time_stats.pack(side=tk.LEFT)

        self._total_label = ttk.Label(
            time_stats,
            text="Active: --",
            font=('Segoe UI', 12, 'bold'),
            foreground='#50C878'  # Green for active
        )
        self._total_label.pack(side=tk.LEFT)

        self._idle_label = ttk.Label(
            time_stats,
            text="Idle: --",
            font=('Segoe UI', 12, 'bold'),
            foreground='#FF6B6B'  # Red for idle
        )
        self._idle_label.pack(side=tk.LEFT, padx=(20, 0))

        self._ratio_label = ttk.Label(
            time_stats,
            text="",
            font=('Segoe UI', 10),
            foreground='#888'
        )
        self._ratio_label.pack(side=tk.LEFT, padx=(15, 0))

        # Right side: Add Manual Entry button
        ttk.Button(
            stats_frame,
            text="+ Add Time",
            command=self._show_add_time_dialog
        ).pack(side=tk.RIGHT)

        # Notebook for tabs
        self._notebook = ttk.Notebook(parent)
        self._notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Tab 1: Table view
        table_frame = ttk.Frame(self._notebook)
        self._notebook.add(table_frame, text="Table")
        self._create_table(table_frame)

        # Tab 2: Weekly Grid view (hours per project per day)
        grid_frame = ttk.Frame(self._notebook)
        self._notebook.add(grid_frame, text="Weekly Grid")
        self._create_weekly_grid(grid_frame)

        # Tab 3: Charts view (only if matplotlib available)
        if MATPLOTLIB_AVAILABLE:
            charts_frame = ttk.Frame(self._notebook)
            self._notebook.add(charts_frame, text="Charts")
            self._create_charts(charts_frame)

    def _create_table(self, parent):
        """Create the activity/category breakdown table."""
        columns = ('project', 'time', 'percentage')
        self._report_tree = ttk.Treeview(
            parent,
            columns=columns,
            show='tree headings',  # Enable tree column for expand/collapse
            height=12
        )

        # Configure tree column (for expand/collapse indicators)
        self._report_tree.heading('#0', text='')
        self._report_tree.column('#0', width=30, minwidth=30, stretch=False)

        self._report_tree.heading('project', text='Activity')
        self._report_tree.heading('time', text='Time')
        self._report_tree.heading('percentage', text='%')

        self._report_tree.column('project', width=270, minwidth=150)
        self._report_tree.column('time', width=120, minwidth=80, anchor='center')
        self._report_tree.column('percentage', width=80, minwidth=60, anchor='center')

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._report_tree.yview)
        self._report_tree.configure(yscrollcommand=scrollbar.set)

        self._report_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _create_weekly_grid(self, parent):
        """Create the weekly grid view showing hours per project per day."""
        # Column headers: Project, Sun, Mon, Tue, Wed, Thu, Fri, Sat, Total
        columns = ('project', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'total')
        self._weekly_grid_tree = ttk.Treeview(
            parent,
            columns=columns,
            show='headings',
            height=15
        )

        # Configure columns
        self._weekly_grid_tree.heading('project', text='Project')
        self._weekly_grid_tree.column('project', width=180, minwidth=120)

        day_names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
        day_cols = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
        for col, name in zip(day_cols, day_names):
            self._weekly_grid_tree.heading(col, text=name)
            self._weekly_grid_tree.column(col, width=60, minwidth=50, anchor='center')

        self._weekly_grid_tree.heading('total', text='Total')
        self._weekly_grid_tree.column('total', width=70, minwidth=60, anchor='center')

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._weekly_grid_tree.yview)
        self._weekly_grid_tree.configure(yscrollcommand=scrollbar.set)

        self._weekly_grid_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _update_weekly_grid(self, start_date: datetime):
        """Update the weekly grid with data for the week starting at start_date."""
        # Clear existing data
        for item in self._weekly_grid_tree.get_children():
            self._weekly_grid_tree.delete(item)

        hidden_categories = self._get_hidden_categories()
        hidden_apps = self._get_hidden_apps()
        min_activity_seconds = self._get_min_activity_seconds()

        # Get raw weekly data (project, date, active_seconds)
        raw_data = self.db.get_weekly_summary(start_date, hidden_categories, hidden_apps, min_activity_seconds)

        # Build a dict: project -> {day_index: hours}
        project_days: Dict[str, Dict[int, float]] = {}
        for item in raw_data:
            project = item['project_name']
            date_str = item['date']
            seconds = item.get('active_seconds', 0)

            # Parse date and get day of week (0=Mon, 6=Sun in Python, but we want Sun=0)
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                # Convert to Sun=0, Mon=1, ... Sat=6
                day_index = (dt.weekday() + 1) % 7
            except:
                continue

            if project not in project_days:
                project_days[project] = {}

            hours = seconds / 3600
            project_days[project][day_index] = project_days[project].get(day_index, 0) + hours

        # Sort projects by total hours
        project_totals = {p: sum(days.values()) for p, days in project_days.items()}
        sorted_projects = sorted(project_totals.keys(), key=lambda p: project_totals[p], reverse=True)

        # Add rows to grid
        for project in sorted_projects:
            days = project_days[project]
            total = sum(days.values())

            # Format hours for each day
            values = [project]
            for day_idx in range(7):
                hours = days.get(day_idx, 0)
                if hours > 0:
                    values.append(f"{hours:.1f}h")
                else:
                    values.append("-")

            values.append(f"{total:.1f}h")

            self._weekly_grid_tree.insert('', tk.END, values=values)

        # Add totals row
        day_totals = [0.0] * 7
        for project, days in project_days.items():
            for day_idx, hours in days.items():
                day_totals[day_idx] += hours

        grand_total = sum(day_totals)
        total_values = ['TOTAL']
        for hours in day_totals:
            total_values.append(f"{hours:.1f}h" if hours > 0 else "-")
        total_values.append(f"{grand_total:.1f}h")

        self._weekly_grid_tree.insert('', tk.END, values=total_values, tags=('total',))

        # Style the total row
        try:
            self._weekly_grid_tree.tag_configure('total', font=('Segoe UI', 10, 'bold'))
        except:
            pass

    def _create_charts(self, parent):
        """Create the charts area with pie chart and bar chart stacked vertically."""
        # Create figure with two subplots stacked vertically
        self._fig = Figure(figsize=(10, 8), dpi=100)
        self._fig.patch.set_facecolor('#2b3e50')  # Match dark theme

        # Pie chart (top)
        self._pie_ax = self._fig.add_subplot(211)
        self._pie_ax.set_facecolor('#2b3e50')

        # Bar chart (bottom)
        self._bar_ax = self._fig.add_subplot(212)
        self._bar_ax.set_facecolor('#2b3e50')

        # Embed in tkinter
        self._chart_canvas = FigureCanvasTkAgg(self._fig, parent)
        self._chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _update_charts(self, data: List[Dict]):
        """Update the charts with current data."""
        if not MATPLOTLIB_AVAILABLE:
            return

        # Clear previous charts
        self._pie_ax.clear()
        self._bar_ax.clear()
        self._pie_ax.set_facecolor('#2b3e50')
        self._bar_ax.set_facecolor('#2b3e50')

        if not data:
            self._pie_ax.text(0.5, 0.5, 'No data', ha='center', va='center', color='white', fontsize=14)
            self._bar_ax.text(0.5, 0.5, 'No data', ha='center', va='center', color='white', fontsize=14)
            self._chart_canvas.draw()
            return

        # Prepare data - limit to top 6 projects for readability
        projects = [item['project_name'] for item in data[:6]]
        seconds = [item.get('active_seconds', 0) for item in data[:6]]
        colors = [self._get_project_color(p) for p in projects]

        # Use full project names
        display_names = projects

        # Draw pie chart
        if sum(seconds) > 0:
            wedges, texts, autotexts = self._pie_ax.pie(
                seconds,
                colors=colors,
                autopct=lambda pct: f'{pct:.1f}%' if pct > 3 else '',
                startangle=90,
                textprops={'color': 'white', 'fontsize': 10},
                pctdistance=0.75
            )
            # Add legend instead of labels on pie (cleaner look)
            self._pie_ax.legend(
                wedges, display_names,
                loc='center left',
                bbox_to_anchor=(1, 0.5),
                fontsize=9,
                frameon=False,
                labelcolor='white'
            )
            if self._group_by == 'category':
                chart_title = 'Time by Category'
            elif self._group_by == 'project':
                chart_title = 'Time by Project'
            else:
                chart_title = 'Time by Activity'
            self._pie_ax.set_title(chart_title, color='white', fontsize=12, fontweight='bold', pad=10)
        else:
            self._pie_ax.text(0.5, 0.5, 'No activity', ha='center', va='center', color='white', fontsize=14)

        # Draw bar chart (hours per project)
        if projects and sum(seconds) > 0:
            hours = [s / 3600 for s in seconds]
            y_pos = range(len(projects))
            bars = self._bar_ax.barh(y_pos, hours, color=colors, height=0.6)
            self._bar_ax.set_yticks(y_pos)
            self._bar_ax.set_yticklabels(display_names, fontsize=10, color='white')
            self._bar_ax.set_xlabel('Hours', color='white', fontsize=11)
            if self._group_by == 'category':
                bar_title = 'Hours by Category'
            elif self._group_by == 'project':
                bar_title = 'Hours by Project'
            else:
                bar_title = 'Hours by Activity'
            self._bar_ax.set_title(bar_title, color='white', fontsize=12, fontweight='bold', pad=10)
            self._bar_ax.tick_params(axis='x', colors='white', labelsize=10)
            self._bar_ax.tick_params(axis='y', colors='white')
            self._bar_ax.invert_yaxis()  # Top project at top

            # Add hour labels on bars
            for i, (bar, hour) in enumerate(zip(bars, hours)):
                if hour > 0:
                    label = f'{hour:.1f}h' if hour >= 1 else f'{int(hour*60)}m'
                    self._bar_ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2,
                                     label, va='center', color='white', fontsize=9)

            # Add some padding to x-axis
            max_hours = max(hours) if hours else 1
            self._bar_ax.set_xlim(0, max_hours * 1.2)

        self._fig.tight_layout(pad=2.0)
        self._chart_canvas.draw()

    def _create_export_buttons(self, parent):
        """Create export buttons."""
        export_frame = ttk.Frame(parent)
        export_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        ttk.Button(
            export_frame,
            text="📊 Export Summary",
            command=self._export_summary
        ).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            export_frame,
            text="📋 Export Timeline",
            command=self._export_timeline
        ).pack(side=tk.LEFT)

        ttk.Button(
            export_frame,
            text="📄 Copy to Clipboard",
            command=self._copy_to_clipboard
        ).pack(side=tk.RIGHT)

    def _set_view_mode(self, mode: str):
        """Set the view mode (daily or weekly)."""
        self._view_mode = mode
        self._refresh()

    def _set_group_by(self, group_by: str):
        """Set the grouping mode (activity or category)."""
        self._group_by = group_by
        self._refresh()

    def _refresh(self):
        """Refresh the report display."""
        if self.window is None:
            return

        hidden_categories = self._get_hidden_categories()
        hidden_apps = self._get_hidden_apps()
        min_activity_seconds = self._get_min_activity_seconds()

        # Update date label
        if self._view_mode == 'daily':
            self._date_label.config(text=self._selected_date.strftime("%A, %B %d, %Y"))
            if self._group_by == 'category':
                # Get hierarchical data for category view
                category_data = self.db.get_daily_summary_by_category_with_activities(
                    self._selected_date, hidden_categories, hidden_apps, min_activity_seconds
                )
                # Also get flat data for charts (category totals)
                data = [
                    {'project_name': cat, 'active_seconds': info['active_seconds'],
                     'total_seconds': info['total_seconds']}
                    for cat, info in category_data.items()
                ]
                project_data = None
            elif self._group_by == 'project':
                # Get hierarchical data for project tag view
                project_data = self.db.get_daily_summary_by_project_tag(
                    self._selected_date, hidden_categories, hidden_apps, min_activity_seconds
                )
                # Also get flat data for charts (project totals)
                data = [
                    {'project_name': tag or 'Other', 'active_seconds': info['active_seconds'],
                     'total_seconds': info['total_seconds']}
                    for tag, info in project_data.items()
                ]
                category_data = None
            else:
                data = self.db.get_daily_summary(self._selected_date, hidden_categories, hidden_apps, min_activity_seconds)
                category_data = None
                project_data = None
        else:
            # Weekly view - start from Monday
            start = self._selected_date - timedelta(days=self._selected_date.weekday())
            end = start + timedelta(days=6)
            self._date_label.config(
                text=f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"
            )
            data = self._get_weekly_data(start, hidden_categories, hidden_apps, min_activity_seconds)
            category_data = None
            project_data = None

        # Update totals (active and idle)
        total_active = sum(item.get('active_seconds', 0) for item in data)
        total_all = sum(item.get('total_seconds', item.get('active_seconds', 0)) for item in data)
        total_idle = total_all - total_active

        self._total_label.config(text=f"Active: {self._format_duration(total_active)}")
        self._idle_label.config(text=f"Idle: {self._format_duration(total_idle)}")

        # Show active percentage
        if total_all > 0:
            active_pct = (total_active / total_all) * 100
            self._ratio_label.config(text=f"({active_pct:.0f}% active)")
        else:
            self._ratio_label.config(text="")

        # Update table header based on grouping mode
        if self._group_by == 'category':
            header_text = 'Category'
        elif self._group_by == 'project':
            header_text = 'Project'
        else:
            header_text = 'Activity'
        self._report_tree.heading('project', text=header_text)

        # Update table
        for item in self._report_tree.get_children():
            self._report_tree.delete(item)

        if self._group_by == 'category' and category_data:
            # Hierarchical display for category mode
            self._populate_category_tree(category_data, total_active)
        elif self._group_by == 'project' and project_data:
            # Hierarchical display for project tag mode
            self._populate_project_tree(project_data, total_active)
        else:
            # Flat display for activity mode
            for item in data:
                project = item['project_name']
                seconds = item.get('active_seconds', 0)
                time_str = self._format_duration(seconds)
                pct = (seconds / total_active * 100) if total_active > 0 else 0

                self._report_tree.insert(
                    '', tk.END,
                    values=(project, time_str, f"{pct:.1f}%")
                )

        # Update charts
        if MATPLOTLIB_AVAILABLE:
            self._update_charts(data)

        # Update weekly grid (always update, it handles its own date range)
        start = self._selected_date - timedelta(days=self._selected_date.weekday())
        self._update_weekly_grid(start)

    def _populate_category_tree(self, category_data: dict, total_active: int):
        """Populate the tree with hierarchical category data."""
        for category, info in category_data.items():
            cat_seconds = info['active_seconds']
            cat_time = self._format_duration(cat_seconds)
            cat_pct = (cat_seconds / total_active * 100) if total_active > 0 else 0

            # Insert category as parent node (with expand/collapse)
            cat_id = self._report_tree.insert(
                '', tk.END,
                text='',  # Tree column text (empty, using expand arrow only)
                values=(category, cat_time, f"{cat_pct:.1f}%"),
                open=False,  # Collapsed by default
                tags=('category',)
            )

            # Insert activities as children
            for activity in info['activities']:
                act_seconds = activity['active_seconds']
                act_time = self._format_duration(act_seconds)
                act_pct = (act_seconds / total_active * 100) if total_active > 0 else 0

                # Extract just the activity name (remove category prefix if present)
                act_name = activity['project_name']
                # Show with indent indicator
                display_name = f"  {act_name}"

                self._report_tree.insert(
                    cat_id, tk.END,
                    text='',
                    values=(display_name, act_time, f"{act_pct:.1f}%"),
                    tags=('activity',)
                )

        # Apply bold styling to category rows if supported
        try:
            self._report_tree.tag_configure('category', font=('Segoe UI', 10, 'bold'))
            self._report_tree.tag_configure('activity', font=('Segoe UI', 9))
        except Exception:
            pass  # Skip if styling not supported

    def _populate_project_tree(self, project_data: dict, total_active: int):
        """Populate the tree with hierarchical project tag data."""
        for tag, info in project_data.items():
            tag_seconds = info['active_seconds']
            tag_time = self._format_duration(tag_seconds)
            tag_pct = (tag_seconds / total_active * 100) if total_active > 0 else 0

            # Display name for the tag (None becomes "Other")
            display_tag = tag if tag else "Other"

            # Insert project tag as parent node (with expand/collapse)
            tag_id = self._report_tree.insert(
                '', tk.END,
                text='',  # Tree column text (empty, using expand arrow only)
                values=(display_tag, tag_time, f"{tag_pct:.1f}%"),
                open=False,  # Collapsed by default
                tags=('project_tag',)
            )

            # Insert activities as children
            for activity in info['activities']:
                act_seconds = activity['active_seconds']
                act_time = self._format_duration(act_seconds)
                act_pct = (act_seconds / total_active * 100) if total_active > 0 else 0

                # Show with indent indicator
                act_name = activity['project_name']
                display_name = f"  {act_name}"

                self._report_tree.insert(
                    tag_id, tk.END,
                    text='',
                    values=(display_name, act_time, f"{act_pct:.1f}%"),
                    tags=('activity',)
                )

        # Apply bold styling to project tag rows if supported
        try:
            self._report_tree.tag_configure('project_tag', font=('Segoe UI', 10, 'bold'))
            self._report_tree.tag_configure('activity', font=('Segoe UI', 9))
        except Exception:
            pass  # Skip if styling not supported

    def _expand_all(self):
        """Expand all parent nodes in the tree."""
        for item in self._report_tree.get_children():
            self._report_tree.item(item, open=True)

    def _collapse_all(self):
        """Collapse all parent nodes in the tree."""
        for item in self._report_tree.get_children():
            self._report_tree.item(item, open=False)

    def _get_weekly_data(self, start_date: datetime,
                         hidden_categories: List[str] = None,
                         hidden_apps: List[str] = None,
                         min_activity_seconds: int = 0) -> List[Dict]:
        """Get aggregated weekly data."""
        # Get raw weekly data
        raw_data = self.db.get_weekly_summary(start_date, hidden_categories, hidden_apps, min_activity_seconds)

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

    def _format_duration(self, seconds: int, apply_rounding: bool = True) -> str:
        """Format seconds as human-readable duration.

        Args:
            seconds: Duration in seconds
            apply_rounding: Whether to apply time rounding setting
        """
        # Apply time rounding if configured
        rounding_minutes = self._get_time_rounding_minutes() if apply_rounding else 0
        if rounding_minutes > 0:
            # Round to nearest interval
            total_minutes = seconds / 60
            rounded_minutes = round(total_minutes / rounding_minutes) * rounding_minutes
            seconds = int(rounded_minutes * 60)

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

    def _show_add_time_dialog(self):
        """Show dialog to manually add time entry."""
        dialog = Toplevel(self.window)
        dialog.title("Add Manual Time Entry")
        dialog.geometry("400x300")
        dialog.transient(self.window)
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        x = self.window.winfo_x() + (self.window.winfo_width() - 400) // 2
        y = self.window.winfo_y() + (self.window.winfo_height() - 300) // 2
        dialog.geometry(f"+{x}+{y}")

        main = ttk.Frame(dialog, padding=20)
        main.pack(fill=tk.BOTH, expand=True)

        # Date selection
        date_frame = ttk.Frame(main)
        date_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(date_frame, text="Date:", width=12).pack(side=tk.LEFT)
        date_var = tk.StringVar(value=self._selected_date.strftime("%Y-%m-%d"))
        date_entry = ttk.Entry(date_frame, textvariable=date_var, width=15)
        date_entry.pack(side=tk.LEFT)
        ttk.Label(date_frame, text="(YYYY-MM-DD)", foreground='#888').pack(side=tk.LEFT, padx=(5, 0))

        # Project selection
        project_frame = ttk.Frame(main)
        project_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(project_frame, text="Project:", width=12).pack(side=tk.LEFT)

        # Get existing project names for dropdown
        existing_projects = []
        try:
            summary = self.db.get_daily_summary(self._selected_date)
            existing_projects = [item['project_name'] for item in summary]
        except:
            pass

        project_var = tk.StringVar()
        project_combo = ttk.Combobox(project_frame, textvariable=project_var, values=existing_projects, width=25)
        project_combo.pack(side=tk.LEFT)

        # Hours entry
        hours_frame = ttk.Frame(main)
        hours_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(hours_frame, text="Duration:", width=12).pack(side=tk.LEFT)

        hours_var = tk.StringVar(value="0")
        hours_spin = ttk.Spinbox(hours_frame, from_=0, to=12, textvariable=hours_var, width=5)
        hours_spin.pack(side=tk.LEFT)
        ttk.Label(hours_frame, text="h").pack(side=tk.LEFT, padx=(2, 10))

        minutes_var = tk.StringVar(value="30")
        minutes_spin = ttk.Spinbox(hours_frame, from_=0, to=59, textvariable=minutes_var, width=5)
        minutes_spin.pack(side=tk.LEFT)
        ttk.Label(hours_frame, text="m").pack(side=tk.LEFT, padx=(2, 0))

        # Description
        desc_frame = ttk.Frame(main)
        desc_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(desc_frame, text="Description:", width=12).pack(side=tk.LEFT, anchor=tk.N)
        desc_text = tk.Text(desc_frame, height=3, width=30)
        desc_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        desc_text.insert('1.0', 'Manual entry')

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(20, 0))

        def save_entry():
            try:
                # Parse inputs
                entry_date = datetime.strptime(date_var.get(), "%Y-%m-%d")
                project = project_var.get().strip()
                hours = int(hours_var.get() or 0)
                minutes = int(minutes_var.get() or 0)
                description = desc_text.get('1.0', tk.END).strip()

                if not project:
                    self._show_error("Error", "Please enter a project name")
                    return

                if hours == 0 and minutes == 0:
                    self._show_error("Error", "Please enter a duration")
                    return

                total_seconds = hours * 3600 + minutes * 60

                # Log the manual entry
                self.db.log_activity(
                    window_title=f"Manual: {description}",
                    process_name="manual-entry",
                    project_name=project,
                    is_active=True,
                    duration_seconds=total_seconds,
                    category="Manual",
                    timestamp=entry_date
                )

                dialog.destroy()
                self._refresh()
                self._show_info("Success", f"Added {hours}h {minutes}m to {project}")

            except ValueError as e:
                self._show_error("Error", f"Invalid input: {e}")

        ttk.Button(btn_frame, text="Save", command=save_entry).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT)

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
