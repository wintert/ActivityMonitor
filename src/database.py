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
                category TEXT,
                is_active BOOLEAN DEFAULT 1,
                duration_seconds INTEGER DEFAULT 5
            )
        ''')

        # Add category column if it doesn't exist (migration for existing databases)
        cursor.execute("PRAGMA table_info(activities)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'category' not in columns:
            cursor.execute('ALTER TABLE activities ADD COLUMN category TEXT')

        # Add project_tag column if it doesn't exist (migration for project tags feature)
        if 'project_tag' not in columns:
            cursor.execute('ALTER TABLE activities ADD COLUMN project_tag TEXT')

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

        # Project mappings table - for custom display name mappings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_type TEXT NOT NULL,
                match_value TEXT NOT NULL,
                display_name TEXT NOT NULL,
                priority INTEGER DEFAULT 1,
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Project tags table - for grouping activities by project
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                keywords TEXT NOT NULL,
                color TEXT DEFAULT '#4A90D9',
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

        # Seed default mappings if this is a fresh database
        self.seed_default_mappings()

    # Activity operations
    def log_activity(self, window_title: str, process_name: str,
                     project_name: Optional[str], is_active: bool,
                     duration_seconds: int = 5,
                     category: Optional[str] = None,
                     project_tag: Optional[str] = None) -> int:
        """Log a single activity record."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Use local time instead of SQLite's UTC CURRENT_TIMESTAMP
        local_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('''
            INSERT INTO activities (timestamp, window_title, process_name, project_name, category, is_active, duration_seconds, project_tag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (local_time, window_title, process_name, project_name, category, is_active, duration_seconds, project_tag))

        activity_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return activity_id

    def get_activities_for_date(self, date: datetime,
                                hidden_categories: Optional[List[str]] = None,
                                hidden_apps: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get all activities for a specific date."""
        conn = self._get_connection()
        cursor = conn.cursor()

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        # Use strftime format to match SQLite's CURRENT_TIMESTAMP format
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        query = '''
            SELECT * FROM activities
            WHERE timestamp >= ? AND timestamp < ?
        '''
        params = [start_str, end_str]

        if hidden_categories:
            placeholders = ','.join('?' * len(hidden_categories))
            query += f' AND (category IS NULL OR category NOT IN ({placeholders}))'
            params.extend(hidden_categories)

        query += ' ORDER BY timestamp'

        cursor.execute(query, params)

        rows = cursor.fetchall()
        conn.close()

        # Filter out hidden apps
        results = [dict(row) for row in rows]
        if hidden_apps:
            results = [r for r in results if not self._is_app_hidden(r.get('project_name', ''), hidden_apps)]

        return results

    def _is_app_hidden(self, project_name: str, hidden_apps: List[str]) -> bool:
        """Check if an app/activity should be hidden based on hidden_apps patterns."""
        if not hidden_apps or not project_name:
            return False
        project_lower = project_name.lower()
        return any(pattern.lower() in project_lower for pattern in hidden_apps)

    def get_daily_summary(self, date: datetime,
                          hidden_categories: Optional[List[str]] = None,
                          hidden_apps: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get aggregated time per project for a date."""
        conn = self._get_connection()
        cursor = conn.cursor()

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        # Use strftime format to match SQLite's CURRENT_TIMESTAMP format
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        # Build query with optional category filtering
        query = '''
            SELECT
                COALESCE(project_name, 'Uncategorized') as project_name,
                category,
                SUM(CASE WHEN is_active THEN duration_seconds ELSE 0 END) as active_seconds,
                SUM(duration_seconds) as total_seconds,
                COUNT(*) as activity_count
            FROM activities
            WHERE timestamp >= ? AND timestamp < ?
        '''
        params = [start_str, end_str]

        if hidden_categories:
            placeholders = ','.join('?' * len(hidden_categories))
            query += f' AND (category IS NULL OR category NOT IN ({placeholders}))'
            params.extend(hidden_categories)

        query += '''
            GROUP BY COALESCE(project_name, 'Uncategorized')
            ORDER BY active_seconds DESC
        '''

        cursor.execute(query, params)

        rows = cursor.fetchall()
        conn.close()

        # Filter out hidden apps (case-insensitive partial match)
        results = [dict(row) for row in rows]
        if hidden_apps:
            results = [r for r in results if not self._is_app_hidden(r['project_name'], hidden_apps)]

        return results

    def get_daily_summary_by_category(self, date: datetime,
                                       hidden_categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get aggregated time per category for a date."""
        conn = self._get_connection()
        cursor = conn.cursor()

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        query = '''
            SELECT
                COALESCE(category, 'Other') as category,
                SUM(CASE WHEN is_active THEN duration_seconds ELSE 0 END) as active_seconds,
                SUM(duration_seconds) as total_seconds,
                COUNT(*) as activity_count
            FROM activities
            WHERE timestamp >= ? AND timestamp < ?
        '''
        params = [start_str, end_str]

        if hidden_categories:
            placeholders = ','.join('?' * len(hidden_categories))
            query += f' AND (category IS NULL OR category NOT IN ({placeholders}))'
            params.extend(hidden_categories)

        query += '''
            GROUP BY COALESCE(category, 'Other')
            ORDER BY active_seconds DESC
        '''

        cursor.execute(query, params)

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_daily_summary_by_category_with_activities(self, date: datetime,
                                                       hidden_categories: Optional[List[str]] = None,
                                                       hidden_apps: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Get aggregated time per category with nested activities for a date.

        Returns a dict structure:
        {
            "Browser": {
                "active_seconds": 8100,
                "total_seconds": 9000,
                "activity_count": 150,
                "activities": [
                    {"project_name": "Browser: Claude Code", "active_seconds": 2880},
                    {"project_name": "Browser: GitHub", "active_seconds": 2100},
                    ...
                ]
            },
            ...
        }
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        # Query groups by both category AND project_name
        query = '''
            SELECT
                COALESCE(category, 'Other') as category,
                COALESCE(project_name, 'Uncategorized') as project_name,
                SUM(CASE WHEN is_active THEN duration_seconds ELSE 0 END) as active_seconds,
                SUM(duration_seconds) as total_seconds,
                COUNT(*) as activity_count
            FROM activities
            WHERE timestamp >= ? AND timestamp < ?
        '''
        params = [start_str, end_str]

        if hidden_categories:
            placeholders = ','.join('?' * len(hidden_categories))
            query += f' AND (category IS NULL OR category NOT IN ({placeholders}))'
            params.extend(hidden_categories)

        query += '''
            GROUP BY COALESCE(category, 'Other'), COALESCE(project_name, 'Uncategorized')
            ORDER BY category, active_seconds DESC
        '''

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Filter out hidden apps
        filtered_rows = [dict(row) for row in rows]
        if hidden_apps:
            filtered_rows = [r for r in filtered_rows if not self._is_app_hidden(r['project_name'], hidden_apps)]

        # Build nested structure
        result: Dict[str, Dict[str, Any]] = {}
        for row in filtered_rows:
            category = row['category']
            if category not in result:
                result[category] = {
                    'active_seconds': 0,
                    'total_seconds': 0,
                    'activity_count': 0,
                    'activities': []
                }

            result[category]['active_seconds'] += row['active_seconds']
            result[category]['total_seconds'] += row['total_seconds']
            result[category]['activity_count'] += row['activity_count']
            result[category]['activities'].append({
                'project_name': row['project_name'],
                'active_seconds': row['active_seconds'],
                'total_seconds': row['total_seconds'],
                'activity_count': row['activity_count']
            })

        # Sort categories by total active_seconds descending
        sorted_result = dict(sorted(
            result.items(),
            key=lambda x: x[1]['active_seconds'],
            reverse=True
        ))

        return sorted_result

    def get_weekly_summary(self, start_date: datetime,
                           hidden_categories: Optional[List[str]] = None,
                           hidden_apps: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get aggregated time per project for a week."""
        conn = self._get_connection()
        cursor = conn.cursor()

        start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)

        # Use strftime format to match SQLite's CURRENT_TIMESTAMP format
        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        query = '''
            SELECT
                COALESCE(project_name, 'Uncategorized') as project_name,
                DATE(timestamp) as date,
                SUM(CASE WHEN is_active THEN duration_seconds ELSE 0 END) as active_seconds
            FROM activities
            WHERE timestamp >= ? AND timestamp < ?
        '''
        params = [start_str, end_str]

        if hidden_categories:
            placeholders = ','.join('?' * len(hidden_categories))
            query += f' AND (category IS NULL OR category NOT IN ({placeholders}))'
            params.extend(hidden_categories)

        query += '''
            GROUP BY COALESCE(project_name, 'Uncategorized'), DATE(timestamp)
            ORDER BY date, active_seconds DESC
        '''

        cursor.execute(query, params)

        rows = cursor.fetchall()
        conn.close()

        # Filter out hidden apps
        results = [dict(row) for row in rows]
        if hidden_apps:
            results = [r for r in results if not self._is_app_hidden(r['project_name'], hidden_apps)]

        return results

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

    # Project Mapping operations
    def add_mapping(self, match_type: str, match_value: str, display_name: str,
                    priority: int = 1, enabled: bool = True) -> int:
        """Add a new project mapping."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO project_mappings (match_type, match_value, display_name, priority, enabled)
            VALUES (?, ?, ?, ?, ?)
        ''', (match_type, match_value, display_name, priority, enabled))

        mapping_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return mapping_id

    def get_mappings(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """Get all project mappings, ordered by priority (highest first)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if enabled_only:
            cursor.execute('''
                SELECT * FROM project_mappings
                WHERE enabled = 1
                ORDER BY priority DESC, id ASC
            ''')
        else:
            cursor.execute('''
                SELECT * FROM project_mappings
                ORDER BY priority DESC, id ASC
            ''')

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def update_mapping(self, mapping_id: int, **kwargs):
        """Update a project mapping."""
        if not kwargs:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        # Build update query dynamically
        valid_fields = ['match_type', 'match_value', 'display_name', 'priority', 'enabled']
        updates = []
        values = []

        for field, value in kwargs.items():
            if field in valid_fields:
                updates.append(f'{field} = ?')
                values.append(value)

        if updates:
            values.append(mapping_id)
            query = f"UPDATE project_mappings SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()

        conn.close()

    def delete_mapping(self, mapping_id: int):
        """Delete a project mapping."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM project_mappings WHERE id = ?', (mapping_id,))

        conn.commit()
        conn.close()

    # Project Tags operations
    def add_project_tag(self, name: str, keywords: List[str],
                        color: str = '#4A90D9', enabled: bool = True) -> int:
        """Add a new project tag."""
        import json

        conn = self._get_connection()
        cursor = conn.cursor()

        keywords_json = json.dumps(keywords)

        cursor.execute('''
            INSERT INTO project_tags (name, keywords, color, enabled)
            VALUES (?, ?, ?, ?)
        ''', (name, keywords_json, color, enabled))

        tag_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return tag_id

    def get_project_tags(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """Get all project tags."""
        import json

        conn = self._get_connection()
        cursor = conn.cursor()

        if enabled_only:
            cursor.execute('''
                SELECT * FROM project_tags
                WHERE enabled = 1
                ORDER BY name ASC
            ''')
        else:
            cursor.execute('SELECT * FROM project_tags ORDER BY name ASC')

        rows = cursor.fetchall()
        conn.close()

        tags = []
        for row in rows:
            tag = dict(row)
            tag['keywords'] = json.loads(tag['keywords'])
            tags.append(tag)

        return tags

    def update_project_tag(self, tag_id: int, **kwargs):
        """Update a project tag."""
        import json

        if not kwargs:
            return

        conn = self._get_connection()
        cursor = conn.cursor()

        # Build update query dynamically
        valid_fields = ['name', 'keywords', 'color', 'enabled']
        updates = []
        values = []

        for field, value in kwargs.items():
            if field in valid_fields:
                if field == 'keywords' and isinstance(value, list):
                    value = json.dumps(value)
                updates.append(f'{field} = ?')
                values.append(value)

        if updates:
            values.append(tag_id)
            query = f"UPDATE project_tags SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()

        conn.close()

    def delete_project_tag(self, tag_id: int):
        """Delete a project tag."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM project_tags WHERE id = ?', (tag_id,))

        conn.commit()
        conn.close()

    def get_daily_summary_by_project_tag(self, date: datetime,
                                          hidden_categories: Optional[List[str]] = None,
                                          hidden_apps: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Get activities grouped by project_tag with nested activities for a date.

        Only returns activities that have a project_tag assigned.
        Untagged activities (Spotify, browsing, etc.) are excluded from this view.

        Returns a dict structure:
        {
            "SiiNewUmbraco": {
                "active_seconds": 5400,
                "total_seconds": 6000,
                "activity_count": 100,
                "color": "#4A90D9",
                "activities": [
                    {"project_name": "Visual Studio - SiiNew...", "active_seconds": 2700},
                    ...
                ]
            },
            ...
        }
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        start_str = start.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end.strftime('%Y-%m-%d %H:%M:%S')

        # Query groups by both project_tag AND project_name
        # Only include activities that have a project_tag (no "Other" bucket)
        query = '''
            SELECT
                project_tag,
                COALESCE(project_name, 'Uncategorized') as project_name,
                SUM(CASE WHEN is_active THEN duration_seconds ELSE 0 END) as active_seconds,
                SUM(duration_seconds) as total_seconds,
                COUNT(*) as activity_count
            FROM activities
            WHERE timestamp >= ? AND timestamp < ?
            AND project_tag IS NOT NULL
        '''
        params = [start_str, end_str]

        if hidden_categories:
            placeholders = ','.join('?' * len(hidden_categories))
            query += f' AND (category IS NULL OR category NOT IN ({placeholders}))'
            params.extend(hidden_categories)

        query += '''
            GROUP BY project_tag, COALESCE(project_name, 'Uncategorized')
            ORDER BY project_tag, active_seconds DESC
        '''

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Filter out hidden apps
        filtered_rows = [dict(row) for row in rows]
        if hidden_apps:
            filtered_rows = [r for r in filtered_rows if not self._is_app_hidden(r['project_name'], hidden_apps)]

        # Get project tag colors
        tag_colors = {tag['name']: tag['color'] for tag in self.get_project_tags()}

        # Build nested structure
        result: Dict[str, Dict[str, Any]] = {}
        for row in filtered_rows:
            tag = row['project_tag'] or None  # Use None for untagged
            if tag not in result:
                result[tag] = {
                    'active_seconds': 0,
                    'total_seconds': 0,
                    'activity_count': 0,
                    'color': tag_colors.get(tag, '#888888') if tag else '#888888',
                    'activities': []
                }

            result[tag]['active_seconds'] += row['active_seconds']
            result[tag]['total_seconds'] += row['total_seconds']
            result[tag]['activity_count'] += row['activity_count']
            result[tag]['activities'].append({
                'project_name': row['project_name'],
                'active_seconds': row['active_seconds'],
                'total_seconds': row['total_seconds'],
                'activity_count': row['activity_count']
            })

        # Sort by total active_seconds descending
        sorted_result = dict(sorted(
            result.items(),
            key=lambda x: x[1]['active_seconds'],
            reverse=True
        ))

        return sorted_result

    def seed_default_mappings(self):
        """Add default app mappings if none exist."""
        # Check if any mappings exist
        existing = self.get_mappings()
        if existing:
            return  # Don't overwrite existing mappings

        # Default app name mappings (process → friendly name)
        default_mappings = [
            ('process', 'devenv.exe', 'Visual Studio', 10),
            ('process', 'Code.exe', 'VS Code', 10),
            ('process', 'code', 'VS Code', 10),
            ('process', 'chrome.exe', 'Chrome', 5),
            ('process', 'firefox.exe', 'Firefox', 5),
            ('process', 'msedge.exe', 'Edge', 5),
            ('process', 'OUTLOOK.EXE', 'Outlook', 5),
            ('process', 'Teams.exe', 'Teams', 5),
            ('process', 'slack.exe', 'Slack', 5),
            ('process', 'WINWORD.EXE', 'Word', 5),
            ('process', 'EXCEL.EXE', 'Excel', 5),
            ('process', 'POWERPNT.EXE', 'PowerPoint', 5),
            ('process', 'notepad.exe', 'Notepad', 3),
            ('process', 'explorer.exe', 'Explorer', 3),
        ]

        for match_type, match_value, display_name, priority in default_mappings:
            self.add_mapping(match_type, match_value, display_name, priority, True)

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
