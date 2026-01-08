"""
Database module for ActivityMonitor.
Handles SQLite storage for activity logs, projects, and settings.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path


class Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to data folder in project root
            project_root = Path(__file__).parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "activity.db")

        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database tables."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Activity log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                window_title TEXT,
                process_name TEXT,
                project_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                duration_seconds INTEGER DEFAULT 5
            )
        ''')

        # Projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                color TEXT DEFAULT '#4A90D9',
                keywords TEXT DEFAULT '[]'
            )
        ''')

        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Create indexes for common queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_activities_timestamp
            ON activities(timestamp)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_activities_project
            ON activities(project_name)
        ''')

        conn.commit()
        conn.close()

    # Activity operations
    def log_activity(self, window_title: str, process_name: str,
                     project_name: Optional[str], is_active: bool,
                     duration_seconds: int = 5) -> int:
        """Log a single activity record."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Use local time instead of SQLite's UTC CURRENT_TIMESTAMP
        local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('''
            INSERT INTO activities (timestamp, window_title, process_name, project_name, is_active, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (local_time, window_title, process_name, project_name, is_active, duration_seconds))

        activity_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return activity_id

    def get_activities_for_date(self, date: datetime) -> List[Dict[str, Any]]:
        """Get all activities for a specific date."""
        conn = self._get_connection()
        cursor = conn.cursor()

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        # Use strftime format to match SQLite's CURRENT_TIMESTAMP format
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('''
            SELECT * FROM activities
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp
        ''', (start_str, end_str))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_daily_summary(self, date: datetime) -> List[Dict[str, Any]]:
        """Get aggregated time per project for a date."""
        conn = self._get_connection()
        cursor = conn.cursor()

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        # Use strftime format to match SQLite's CURRENT_TIMESTAMP format
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('''
            SELECT
                COALESCE(project_name, 'Uncategorized') as project_name,
                SUM(CASE WHEN is_active THEN duration_seconds ELSE 0 END) as active_seconds,
                SUM(duration_seconds) as total_seconds,
                COUNT(*) as activity_count
            FROM activities
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY COALESCE(project_name, 'Uncategorized')
            ORDER BY active_seconds DESC
        ''', (start_str, end_str))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_weekly_summary(self, start_date: datetime) -> List[Dict[str, Any]]:
        """Get aggregated time per project for a week."""
        conn = self._get_connection()
        cursor = conn.cursor()

        start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)

        # Use strftime format to match SQLite's CURRENT_TIMESTAMP format
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('''
            SELECT
                COALESCE(project_name, 'Uncategorized') as project_name,
                DATE(timestamp) as date,
                SUM(CASE WHEN is_active THEN duration_seconds ELSE 0 END) as active_seconds
            FROM activities
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY COALESCE(project_name, 'Uncategorized'), DATE(timestamp)
            ORDER BY date, active_seconds DESC
        ''', (start_str, end_str))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_activity_project(self, activity_id: int, project_name: str):
        """Update the project for an activity (for manual tagging)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE activities SET project_name = ? WHERE id = ?
        ''', (project_name, activity_id))

        conn.commit()
        conn.close()

    # Project operations
    def add_project(self, name: str, color: str = '#4A90D9',
                    keywords: Optional[List[str]] = None) -> int:
        """Add a new project."""
        import json

        conn = self._get_connection()
        cursor = conn.cursor()

        keywords_json = json.dumps(keywords or [])

        cursor.execute('''
            INSERT OR REPLACE INTO projects (name, color, keywords)
            VALUES (?, ?, ?)
        ''', (name, color, keywords_json))

        project_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return project_id

    def get_projects(self) -> List[Dict[str, Any]]:
        """Get all projects."""
        import json

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM projects ORDER BY name')

        rows = cursor.fetchall()
        conn.close()

        projects = []
        for row in rows:
            project = dict(row)
            project['keywords'] = json.loads(project['keywords'])
            projects.append(project)

        return projects

    def delete_project(self, project_id: int):
        """Delete a project."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))

        conn.commit()
        conn.close()

    # Settings operations
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        import json

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return default

        try:
            return json.loads(row['value'])
        except json.JSONDecodeError:
            return row['value']

    def set_setting(self, key: str, value: Any):
        """Set a setting value."""
        import json

        conn = self._get_connection()
        cursor = conn.cursor()

        value_json = json.dumps(value)

        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
        ''', (key, value_json))

        conn.commit()
        conn.close()

    # Export functionality
    def export_to_csv(self, date: datetime, filepath: str):
        """Export daily summary to CSV."""
        import csv

        summary = self.get_daily_summary(date)

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Project', 'Active Time (hours)', 'Active Time (formatted)'])

            for row in summary:
                hours = row['active_seconds'] / 3600
                formatted = self._format_duration(row['active_seconds'])
                writer.writerow([row['project_name'], f"{hours:.2f}", formatted])

    def export_timeline_to_csv(self, date: datetime, filepath: str):
        """Export detailed timeline to CSV."""
        import csv

        activities = self.get_activities_for_date(date)

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Timestamp', 'Project', 'Window Title', 'Process', 'Active', 'Duration (s)'])

            for row in activities:
                writer.writerow([
                    row['timestamp'],
                    row['project_name'] or 'Uncategorized',
                    row['window_title'],
                    row['process_name'],
                    'Yes' if row['is_active'] else 'No',
                    row['duration_seconds']
                ])

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format seconds as hours and minutes."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
