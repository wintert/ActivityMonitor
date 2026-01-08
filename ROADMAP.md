# ActivityMonitor Roadmap

## Current Sprint: Quick Wins (Visual & UX Improvements)

### 1. ttkbootstrap Integration (Modern Look)
- Replace tkinter/ttk with ttkbootstrap
- Use "darkly" or "superhero" theme for modern flat design
- Affects: timeline_view.py, report_view.py, settings_view.py, activity_monitor.py
- Benefits: Rounded corners, better colors, professional appearance

### 2. Dark Mode Toggle
- Add setting to switch between light/dark themes
- Store preference in database settings
- Apply theme on app startup
- Themes to support: "litera" (light), "darkly" (dark)

### 3. Daily Summary Notification
- Show notification at configurable time (default: 6 PM)
- Summary includes: Total active time, top 3 projects, idle time
- Uses system tray notification
- Add setting to enable/disable and set time

### 4. Break Reminders
- Remind user to take breaks after X minutes of continuous work
- Default: Every 50 minutes (Pomodoro-style)
- Show notification with option to snooze
- Add settings: Enable/disable, interval, snooze duration

---

## Next Sprint: Medium Effort Features

### 5. Charts in Reports
- Pie chart: Project time distribution
- Bar chart: Daily hours over the week
- Library: matplotlib or plotly
- Embed in report_view.py

### 6. Timeline Tooltips
- Hover over timeline segments to see details
- Show: Project name, duration, time range
- Click to filter activity list

### 7. Search/Filter Activities
- Add search box to timeline view
- Filter by: project name, window title, date range
- Highlight matching entries

### 8. Mini Dashboard (Tray Popup)
- Click tray icon shows quick stats
- Today's active time, current project, break reminder status
- Quick actions: Pause, Open Timeline, Open Reports

### 9. Icons
- Add icons to buttons (using ttkbootstrap's built-in icons)
- Tray menu icons
- Window title bar icons

---

## Future Sprint: Larger Features

### 10. Productivity Insights
- Analyze patterns: most productive hours, days
- Show insights in reports view
- "You're 40% more productive in the morning"

### 11. Trends View
- Weekly/monthly activity trends
- Compare weeks, identify patterns
- Line charts showing progress over time

### 12. Activity Heatmap
- GitHub-style contribution graph
- Shows activity intensity by day
- Click day to see details

### 13. Goals & Progress
- Set daily/weekly hour goals per project
- Progress bar in tray and dashboard
- Notifications when goals reached

### 14. PDF Reports
- Export professional PDF reports
- Include charts, summaries, detailed logs
- Suitable for work time reporting

### 15. Project Categories/Tags
- Group projects: Work, Personal, Learning
- Color coding by category
- Filter reports by category

---

## Technical Notes

### ttkbootstrap Themes
- Light: litera, flatly, journal, lumen, minty, pulse, sandstone, united, yeti, cosmo
- Dark: darkly, cyborg, vapor, superhero, solar

### Files to Modify for ttkbootstrap
1. `requirements.txt` - Add ttkbootstrap
2. `src/activity_monitor.py` - Initialize ttkbootstrap window
3. `src/ui/timeline_view.py` - Use ttkbootstrap widgets
4. `src/ui/report_view.py` - Use ttkbootstrap widgets
5. `src/ui/settings_view.py` - Use ttkbootstrap widgets, add new settings
6. `src/config.py` - Add new config options (theme, break reminders, etc.)

### New Config Options Needed
```python
# Theme
theme: str = "darkly"  # or "litera" for light

# Daily Summary
daily_summary_enabled: bool = True
daily_summary_time: str = "18:00"  # 6 PM

# Break Reminders
break_reminder_enabled: bool = True
break_reminder_interval_minutes: int = 50
break_reminder_snooze_minutes: int = 10
```
