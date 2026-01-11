"""
Project mapper module for ActivityMonitor.
Maps window activities to projects based on rules.
"""

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProjectRule:
    """A rule for mapping activities to projects."""
    project_name: str
    process_patterns: List[str]  # Regex patterns for process name
    title_patterns: List[str]  # Regex patterns for window title
    priority: int = 0  # Higher priority rules are checked first


class ProjectMapper:
    """
    Maps window activities to projects.

    Primary detection is Visual Studio solution/project names.
    Also supports VS Code and custom rules for other applications.
    """

    # Visual Studio process names
    VISUAL_STUDIO_PROCESSES = {'devenv.exe', 'devenv'}

    # VS Code process names (kept for compatibility)
    VSCODE_PROCESSES = {'Code.exe', 'Code', 'code', 'Code - Insiders.exe'}

    # Visual Studio title patterns:
    # "SolutionName - Microsoft Visual Studio"
    # "FileName.cs - SolutionName - Microsoft Visual Studio"
    # "FileName.cs (Design) - SolutionName - Microsoft Visual Studio"
    # "SolutionName (Running) - Microsoft Visual Studio"
    # "SolutionName - Microsoft Visual Studio [Administrator]"
    VISUAL_STUDIO_TITLE_PATTERN = re.compile(
        r'^(?:.*?\s+-\s+)?([^-\(\)]+?)(?:\s*\([^)]*\))?\s*-\s*Microsoft Visual Studio',
        re.IGNORECASE
    )

    # Alternative pattern to extract solution name before "- Microsoft Visual Studio"
    VISUAL_STUDIO_SIMPLE_PATTERN = re.compile(
        r'([^-]+)\s*-\s*Microsoft Visual Studio',
        re.IGNORECASE
    )

    # VS Code title patterns (kept for compatibility)
    VSCODE_TITLE_PATTERN = re.compile(
        r'^(?:.*? - )?([^-\[\]]+?)(?:\s*\[.*?\])?\s*-\s*Visual Studio Code',
        re.IGNORECASE
    )

    def __init__(self, database=None):
        self.db = database
        self._custom_rules: List[ProjectRule] = []
        self._display_mappings: List[Dict] = []
        self._load_rules()
        self._load_display_mappings()

    def _load_rules(self):
        """Load custom rules from database."""
        if self.db is None:
            return

        projects = self.db.get_projects()
        for project in projects:
            keywords = project.get('keywords', [])
            if keywords:
                rule = ProjectRule(
                    project_name=project['name'],
                    process_patterns=[],
                    title_patterns=[re.escape(kw) for kw in keywords],
                    priority=1
                )
                self._custom_rules.append(rule)

        # Sort by priority (higher first)
        self._custom_rules.sort(key=lambda r: r.priority, reverse=True)

    def add_rule(self, rule: ProjectRule):
        """Add a custom mapping rule."""
        self._custom_rules.append(rule)
        self._custom_rules.sort(key=lambda r: r.priority, reverse=True)

    def _load_display_mappings(self):
        """Load display name mappings from database."""
        if self.db is None:
            return
        self._display_mappings = self.db.get_mappings(enabled_only=True)

    def reload_mappings(self):
        """Reload mappings from database (call after adding/editing mappings)."""
        self._load_display_mappings()

    def apply_display_mappings(self, project_name: str, process_name: str,
                                window_title: str) -> str:
        """
        Apply custom display name mappings to transform project name.

        Creates a combined format: "App - Project" where:
        - App comes from process mapping (e.g., "devenv.exe" → "Visual Studio")
        - Project comes from project mapping (e.g., "EwaveShamirUmbraco13" → "Shamir Website")

        Args:
            project_name: The detected project name
            process_name: The process name (e.g., "devenv.exe")
            window_title: The window title

        Returns:
            Combined display name in format "App - Project", or just project if no app mapping
        """
        app_name = None
        mapped_project = project_name

        # First pass: find app name from process mapping
        for mapping in self._display_mappings:
            if mapping['match_type'] == 'process':
                match_value = mapping['match_value'].lower()
                if process_name and match_value in process_name.lower():
                    app_name = mapping['display_name']
                    break

        # Second pass: find project name mapping
        for mapping in self._display_mappings:
            if mapping['match_type'] == 'project':
                match_value = mapping['match_value'].lower()
                if project_name and match_value in project_name.lower():
                    mapped_project = mapping['display_name']
                    break

        # Third pass: check window title mappings (can override everything)
        for mapping in self._display_mappings:
            if mapping['match_type'] == 'window':
                match_value = mapping['match_value'].lower()
                if window_title and match_value in window_title.lower():
                    # Window mapping overrides the project name
                    mapped_project = mapping['display_name']
                    break

        # Combine app and project if both exist
        if app_name and mapped_project:
            # Avoid duplication like "Visual Studio - Visual Studio"
            if app_name.lower() != mapped_project.lower():
                return f"{app_name} - {mapped_project}"
            else:
                return app_name
        elif app_name:
            return app_name
        else:
            return mapped_project

    def map_activity(self, process_name: str, window_title: str) -> Optional[str]:
        """
        Map an activity to a project name.

        Args:
            process_name: The process name (e.g., "devenv.exe")
            window_title: The window title

        Returns:
            Project name - ALWAYS returns something meaningful, never None
        """
        # First, check Visual Studio (highest priority for solution/project detection)
        # Check by process name OR by window title pattern (for elevated processes)
        if (process_name in self.VISUAL_STUDIO_PROCESSES or
            'microsoft visual studio' in window_title.lower()):
            project = self._detect_visual_studio_project(window_title)
            if project:
                return project

        # Also check VS Code for compatibility
        if (process_name in self.VSCODE_PROCESSES or
            'visual studio code' in window_title.lower()):
            project = self._detect_vscode_project(window_title)
            if project:
                return project

        # Check custom rules
        for rule in self._custom_rules:
            if self._matches_rule(rule, process_name, window_title):
                return rule.project_name

        # Check if it's a known application type
        app_type = self._detect_app_type(process_name, window_title)
        if app_type:
            return app_type

        # Fallback: use process name so nothing is truly "uncategorized"
        if process_name and process_name != "Unknown":
            # Clean up process name (remove .exe)
            clean_name = process_name.replace('.exe', '').replace('.EXE', '')
            return f"App: {clean_name}"

        # Last resort: extract something from window title
        if window_title:
            # Take first meaningful part of title
            parts = window_title.split(' - ')
            if parts:
                return f"Window: {parts[0][:50]}"

        return "Unknown"

    def _detect_visual_studio_project(self, window_title: str) -> Optional[str]:
        """Extract solution/project name from Visual Studio window title."""
        if not window_title:
            return None

        # Skip non-project windows
        skip_titles = ['start page', 'getting started', 'welcome', 'options', 'about']
        title_lower = window_title.lower()
        if any(skip in title_lower for skip in skip_titles):
            return None

        # Check if this is actually a Visual Studio window
        if 'microsoft visual studio' not in title_lower:
            return None

        # Try to extract the solution/project name
        # Pattern: "FileName.cs - SolutionName - Microsoft Visual Studio"
        # Or: "SolutionName - Microsoft Visual Studio"
        parts = window_title.split(' - ')

        if len(parts) >= 2:
            # Find the part just before "Microsoft Visual Studio"
            for i, part in enumerate(parts):
                if 'microsoft visual studio' in part.lower():
                    if i > 0:
                        # Get the previous part as solution name
                        solution = parts[i - 1].strip()
                        # Remove status indicators like (Running), (Debugging), etc.
                        solution = re.sub(r'\s*\([^)]*\)\s*$', '', solution).strip()
                        # Remove [Administrator] or similar
                        solution = re.sub(r'\s*\[[^\]]*\]\s*$', '', solution).strip()

                        if solution and solution.lower() not in ['untitled', 'new project']:
                            return solution
                    break

        # Fallback: try regex pattern
        match = self.VISUAL_STUDIO_TITLE_PATTERN.match(window_title)
        if match:
            project = match.group(1).strip()
            if project and project.lower() not in ['untitled', 'new project', 'start page']:
                return project

        return None

    def _detect_vscode_project(self, window_title: str) -> Optional[str]:
        """Extract project/workspace name from VS Code window title."""
        if not window_title:
            return None

        # Skip welcome and settings tabs
        skip_titles = ['welcome', 'settings', 'extensions', 'keyboard shortcuts']
        title_lower = window_title.lower()
        if any(skip in title_lower for skip in skip_titles):
            return None

        # Try the main pattern
        match = self.VSCODE_TITLE_PATTERN.match(window_title)
        if match:
            project = match.group(1).strip()
            # Filter out common non-project names
            if project.lower() not in ['untitled', 'output', 'terminal', 'debug console']:
                return project

        # Try path-based pattern (for "filename - FolderName - VS Code")
        parts = window_title.split(' - ')
        if len(parts) >= 3 and 'visual studio code' in parts[-1].lower():
            # Second to last part before "Visual Studio Code" is usually the folder
            project = parts[-2].strip()
            # Remove any WSL/Remote indicators
            project = re.sub(r'\s*\[.*?\]\s*', '', project).strip()
            if project and project.lower() not in ['untitled', 'output', 'terminal']:
                return project

        return None

    def _matches_rule(self, rule: ProjectRule, process_name: str, window_title: str) -> bool:
        """Check if activity matches a rule."""
        # Check process patterns
        for pattern in rule.process_patterns:
            if re.search(pattern, process_name, re.IGNORECASE):
                return True

        # Check title patterns
        for pattern in rule.title_patterns:
            if re.search(pattern, window_title, re.IGNORECASE):
                return True

        return False

    def _detect_app_type(self, process_name: str, window_title: str) -> Optional[str]:
        """
        Detect common application types and extract project context.

        Returns a project/category name for known applications.
        """
        process_lower = process_name.lower()
        title_lower = window_title.lower()

        # Browsers - show actual tab title
        browsers = ['chrome', 'firefox', 'msedge', 'brave', 'opera', 'edge']
        if any(b in process_lower for b in browsers):
            # Extract the page title (everything before " - Profile - Browser")
            page_title = self._extract_browser_page_title(window_title)
            if page_title:
                # Truncate long titles
                if len(page_title) > 60:
                    page_title = page_title[:57] + "..."
                return f"Browser: {page_title}"
            return "Browser"

        # Text editors - show filename
        text_editors = ['notepad', 'notepad++', 'sublime', 'atom', 'textpad', 'ultraedit']
        if any(editor in process_lower for editor in text_editors):
            filename = self._extract_editor_filename(window_title, process_name)
            if filename:
                return f"Editor: {filename}"
            return f"Editor: {process_name.replace('.exe', '')}"

        # Communication apps
        if any(app in process_lower for app in ['teams', 'slack', 'zoom', 'discord', 'webex']):
            return 'Communication'

        # Office apps - show document name
        if 'outlook' in process_lower:
            return 'Email'
        if any(app in process_lower for app in ['winword', 'word']):
            doc_name = self._extract_office_document(window_title, 'Word')
            return f"Word: {doc_name}" if doc_name else 'Word'
        if any(app in process_lower for app in ['excel', 'xlim']):
            doc_name = self._extract_office_document(window_title, 'Excel')
            return f"Excel: {doc_name}" if doc_name else 'Excel'
        if any(app in process_lower for app in ['powerpnt', 'powerpoint']):
            doc_name = self._extract_office_document(window_title, 'PowerPoint')
            return f"PowerPoint: {doc_name}" if doc_name else 'PowerPoint'
        if 'onenote' in process_lower:
            return 'OneNote'

        # Terminal/Console
        if any(term in process_lower for term in ['windowsterminal', 'cmd', 'powershell', 'conhost']):
            # Try to extract current directory or command from title
            return f"Terminal: {window_title[:50]}" if window_title else 'Terminal'

        # Music/Media
        if 'spotify' in process_lower:
            # Spotify shows "Song - Artist" in title
            if window_title and window_title != 'Spotify':
                return f"Spotify: {window_title[:50]}"
            return 'Spotify'
        if any(app in process_lower for app in ['music', 'vlc', 'media', 'groove']):
            return 'Media'

        # File explorer - show folder name or Desktop
        if 'explorer' in process_lower:
            if not window_title or window_title.lower() in ['program manager', 'desktop', '']:
                return "Desktop"
            return f"Explorer: {window_title[:50]}"

        return None

    def _extract_browser_page_title(self, window_title: str) -> Optional[str]:
        """Extract the actual page title from browser window title."""
        if not window_title:
            return None

        # Browser titles usually end with " - BrowserName" or " - Profile - BrowserName"
        # Examples:
        # "Google - Work - Microsoft Edge"
        # "GitHub - Google Chrome"
        # "Page Title and 5 more pages - Work - Microsoft Edge"

        # Remove browser name suffixes
        browser_suffixes = [
            ' - Microsoft Edge', ' - Microsoft​ Edge',  # Note: second has special char
            ' - Google Chrome', ' - Mozilla Firefox',
            ' - Brave', ' - Opera',
        ]

        title = window_title
        for suffix in browser_suffixes:
            if title.endswith(suffix):
                title = title[:-len(suffix)]
                break

        # Remove profile name if present (e.g., " - Work" at the end)
        # But keep it if it's part of the page title
        parts = title.rsplit(' - ', 1)
        if len(parts) == 2:
            # Check if the last part looks like a profile (short, single word)
            potential_profile = parts[1].strip()
            if len(potential_profile) <= 20 and ' ' not in potential_profile:
                title = parts[0]

        # Remove "and X more pages" suffix that Edge adds for multiple tabs
        # Pattern: "Page Title and 5 more pages" or "Page Title and 12 more pages"
        import re
        title = re.sub(r'\s+and\s+\d+\s+more\s+pages?\s*$', '', title, flags=re.IGNORECASE)

        return title.strip() if title.strip() else None

    def _extract_editor_filename(self, window_title: str, process_name: str) -> Optional[str]:
        """Extract filename from text editor window title."""
        if not window_title:
            return None

        # Common patterns:
        # "filename.txt - Notepad"
        # "*filename.txt - Notepad" (unsaved changes)
        # "filename.txt - Notepad++"

        # Remove editor name suffix
        editor_suffixes = [' - Notepad++', ' - Notepad', ' - Sublime Text', ' - Atom']
        title = window_title
        for suffix in editor_suffixes:
            if suffix.lower() in title.lower():
                idx = title.lower().find(suffix.lower())
                title = title[:idx]
                break

        # Remove unsaved indicator
        title = title.lstrip('*').strip()

        return title if title else None

    def _extract_office_document(self, window_title: str, app_name: str) -> Optional[str]:
        """Extract document name from Office app window title."""
        if not window_title:
            return None

        # Patterns:
        # "Document1 - Word"
        # "Book1 - Excel"
        # "Presentation1 - PowerPoint"

        parts = window_title.split(' - ')
        if parts:
            doc_name = parts[0].strip()
            # Filter out generic names
            if doc_name.lower() not in ['document', 'book', 'presentation', app_name.lower()]:
                return doc_name[:50]

        return None

    def get_project_suggestions(self, window_title: str) -> List[str]:
        """
        Get project name suggestions based on window title.

        Useful for manual tagging UI.
        """
        suggestions = []

        # Extract potential project names from title
        # Split by common separators
        parts = re.split(r'\s*[-|/\\]\s*', window_title)

        for part in parts:
            part = part.strip()
            # Skip very short or very long parts
            if 3 <= len(part) <= 50:
                # Skip common non-project words
                skip_words = ['microsoft visual studio', 'visual studio code', 'google chrome', 'microsoft', 'the', 'and']
                if not any(sw in part.lower() for sw in skip_words):
                    suggestions.append(part)

        # Also add any existing projects from DB
        if self.db:
            existing = [p['name'] for p in self.db.get_projects()]
            suggestions.extend(existing)

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for s in suggestions:
            s_lower = s.lower()
            if s_lower not in seen:
                seen.add(s_lower)
                unique.append(s)

        return unique[:10]  # Return top 10 suggestions


if __name__ == "__main__":
    # Test the project mapper
    mapper = ProjectMapper()

    test_cases = [
        # Visual Studio test cases
        ("devenv.exe", "ActivityMonitor - Microsoft Visual Studio"),
        ("devenv.exe", "Program.cs - ActivityMonitor - Microsoft Visual Studio"),
        ("devenv.exe", "ActivityMonitor (Running) - Microsoft Visual Studio"),
        ("devenv.exe", "Form1.cs [Design] - MyWinForms - Microsoft Visual Studio"),
        ("devenv.exe", "Start Page - Microsoft Visual Studio"),
        # VS Code test cases (for compatibility)
        ("Code.exe", "main.py - MyProject - Visual Studio Code"),
        # Other apps
        ("chrome.exe", "GitHub - anthropics/claude-code"),
        ("Teams.exe", "Meeting with Team"),
        ("notepad.exe", "Untitled - Notepad"),
    ]

    print("Project Mapper Test")
    print("-" * 60)

    for process, title in test_cases:
        project = mapper.map_activity(process, title)
        print(f"Process: {process}")
        print(f"Title: {title}")
        print(f"Project: {project or 'Uncategorized'}")
        print("-" * 60)
