"""
Project mapper module for ActivityMonitor.
Maps window activities to projects based on rules and categories.
"""

import re
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# Category constants
class Category:
    """Activity categories for grouping similar activities."""
    DEVELOPMENT = "Development"
    BROWSER = "Browser"
    COMMUNICATION = "Communication"
    REMOTE_DESKTOP = "Remote Desktop"
    OFFICE = "Office"
    EMAIL = "Email"
    TERMINAL = "Terminal"
    EDITOR = "Editor"
    MEDIA = "Media"
    SYSTEM = "System"  # File Explorer, utilities
    SECURITY = "Security"  # VPN, antivirus, etc.
    OTHER = "Other"

    # Categories hidden by default in reports
    DEFAULT_HIDDEN = ["System"]

    @classmethod
    def all_categories(cls) -> List[str]:
        """Return all category names."""
        return [
            cls.DEVELOPMENT, cls.BROWSER, cls.COMMUNICATION,
            cls.REMOTE_DESKTOP, cls.OFFICE, cls.EMAIL,
            cls.TERMINAL, cls.EDITOR, cls.MEDIA,
            cls.SYSTEM, cls.SECURITY, cls.OTHER
        ]


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

    def map_activity(self, process_name: str, window_title: str) -> Tuple[str, str]:
        """
        Map an activity to a project name and category.

        Args:
            process_name: The process name (e.g., "devenv.exe")
            window_title: The window title

        Returns:
            Tuple of (project_name, category) - ALWAYS returns something meaningful
        """
        # First, check Visual Studio (highest priority for solution/project detection)
        # Check by process name OR by window title pattern (for elevated processes)
        if (process_name in self.VISUAL_STUDIO_PROCESSES or
            'microsoft visual studio' in window_title.lower()):
            project = self._detect_visual_studio_project(window_title)
            if project:
                return (project, Category.DEVELOPMENT)

        # Also check VS Code for compatibility
        if (process_name in self.VSCODE_PROCESSES or
            'visual studio code' in window_title.lower()):
            project = self._detect_vscode_project(window_title)
            if project:
                return (project, Category.DEVELOPMENT)

        # Check custom rules
        for rule in self._custom_rules:
            if self._matches_rule(rule, process_name, window_title):
                return (rule.project_name, Category.OTHER)

        # Check if it's a known application type
        result = self._detect_app_type(process_name, window_title)
        if result:
            return result

        # Fallback: use process name so nothing is truly "uncategorized"
        if process_name and process_name != "Unknown":
            # Clean up process name (remove .exe)
            clean_name = process_name.replace('.exe', '').replace('.EXE', '')
            return (f"App: {clean_name}", Category.OTHER)

        # Last resort: extract something from window title
        if window_title:
            # Take first meaningful part of title
            parts = window_title.split(' - ')
            if parts:
                return (f"Window: {parts[0][:50]}", Category.OTHER)

        return ("Unknown", Category.OTHER)

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

        # Visual Studio title formats:
        # "SolutionName - FileName.cs - Microsoft Visual Studio (Administrator)"
        # "SolutionName - Microsoft Visual Studio"
        # The solution name is ALWAYS the FIRST part
        parts = window_title.split(' - ')

        if len(parts) >= 2:
            # The solution name is the FIRST part
            solution = parts[0].strip()

            # Remove status indicators like (Running), (Debugging), etc.
            solution = re.sub(r'\s*\([^)]*\)\s*$', '', solution).strip()
            # Remove [Administrator] or similar
            solution = re.sub(r'\s*\[[^\]]*\]\s*$', '', solution).strip()

            # Skip if it looks like a file name (has extension)
            if solution and '.' in solution and len(solution.split('.')[-1]) <= 5:
                # This might be a filename, try the second part
                if len(parts) >= 3:
                    solution = parts[1].strip()
                    solution = re.sub(r'\s*\([^)]*\)\s*$', '', solution).strip()
                    solution = re.sub(r'\s*\[[^\]]*\]\s*$', '', solution).strip()

            if solution and solution.lower() not in ['untitled', 'new project']:
                return solution

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

    def _detect_app_type(self, process_name: str, window_title: str) -> Optional[Tuple[str, str]]:
        """
        Detect common application types and extract project context.

        Returns a tuple of (display_name, category) for known applications.
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
                return (f"Browser: {page_title}", Category.BROWSER)
            return ("Browser", Category.BROWSER)

        # Communication apps (check before general apps)
        # Special handling for Teams to extract meeting/chat context
        if 'teams' in process_lower or 'teams' in title_lower:
            teams_context = self._extract_teams_context(window_title)
            return (teams_context, Category.COMMUNICATION)

        comm_apps = {
            'slack': 'Slack',
            'zoom': 'Zoom',
            'discord': 'Discord',
            'webex': 'Webex',
            'whatsapp': 'WhatsApp',
            'telegram': 'Telegram',
            'signal': 'Signal',
            'skype': 'Skype',
        }
        for app_key, app_name in comm_apps.items():
            if app_key in process_lower or app_key in title_lower:
                return (app_name, Category.COMMUNICATION)

        # Remote Desktop apps
        remote_apps = {
            'mstsc': 'Remote Desktop',
            'rdcman': 'RD Connection Manager',
            'anydesk': 'AnyDesk',
            'teamviewer': 'TeamViewer',
            'rustdesk': 'RustDesk',
            'vmconnect': 'Hyper-V Connect',
            'vmware': 'VMware',
            'virtualbox': 'VirtualBox',
        }
        for app_key, app_name in remote_apps.items():
            if app_key in process_lower:
                # Try to extract connection name from title
                if window_title and window_title not in ['', app_name]:
                    conn_name = window_title.split(' - ')[0][:40]
                    return (f"{app_name}: {conn_name}", Category.REMOTE_DESKTOP)
                return (app_name, Category.REMOTE_DESKTOP)

        # Security/VPN apps
        security_apps = {
            'forticlient': 'FortiClient VPN',
            'vpn': 'VPN',
            'openvpn': 'OpenVPN',
            'wireguard': 'WireGuard',
            'cisco': 'Cisco VPN',
            'globalprotect': 'GlobalProtect',
            'defender': 'Windows Defender',
            'malwarebytes': 'Malwarebytes',
        }
        for app_key, app_name in security_apps.items():
            if app_key in process_lower or app_key in title_lower:
                return (app_name, Category.SECURITY)

        # Text editors - show filename
        text_editors = ['notepad', 'notepad++', 'sublime', 'atom', 'textpad', 'ultraedit']
        if any(editor in process_lower for editor in text_editors):
            filename = self._extract_editor_filename(window_title, process_name)
            if filename:
                return (f"Editor: {filename}", Category.EDITOR)
            return (f"Editor: {process_name.replace('.exe', '')}", Category.EDITOR)

        # Office apps - show document name
        if 'outlook' in process_lower:
            return ('Outlook', Category.EMAIL)
        if any(app in process_lower for app in ['winword', 'word']):
            doc_name = self._extract_office_document(window_title, 'Word')
            return (f"Word: {doc_name}" if doc_name else 'Word', Category.OFFICE)
        if any(app in process_lower for app in ['excel', 'xlim']):
            doc_name = self._extract_office_document(window_title, 'Excel')
            return (f"Excel: {doc_name}" if doc_name else 'Excel', Category.OFFICE)
        if any(app in process_lower for app in ['powerpnt', 'powerpoint']):
            doc_name = self._extract_office_document(window_title, 'PowerPoint')
            return (f"PowerPoint: {doc_name}" if doc_name else 'PowerPoint', Category.OFFICE)
        if 'onenote' in process_lower:
            return ('OneNote', Category.OFFICE)

        # Terminal/Console
        if any(term in process_lower for term in ['windowsterminal', 'cmd', 'powershell', 'conhost', 'wsl']):
            # Try to extract current directory from terminal title
            if window_title:
                dir_name = self._extract_terminal_directory(window_title)
                if dir_name:
                    return (f"Terminal: {dir_name}", Category.TERMINAL)
                # Fallback to window title if no directory found
                return (f"Terminal: {window_title[:50]}", Category.TERMINAL)
            return ('Terminal', Category.TERMINAL)

        # Music/Media
        if 'spotify' in process_lower:
            # Spotify shows "Song - Artist" in title
            if window_title and window_title != 'Spotify':
                return (f"Spotify: {window_title[:50]}", Category.MEDIA)
            return ('Spotify', Category.MEDIA)
        if any(app in process_lower for app in ['music', 'vlc', 'media', 'groove', 'itunes', 'foobar']):
            return ('Media Player', Category.MEDIA)

        # File explorer - show folder name or Desktop (categorized as System)
        if 'explorer' in process_lower:
            if not window_title or window_title.lower() in ['program manager', 'desktop', '']:
                return ("Desktop", Category.SYSTEM)
            return (f"Explorer: {window_title[:50]}", Category.SYSTEM)

        # Other system utilities
        system_apps = ['taskmgr', 'control', 'mmc', 'regedit', 'services', 'perfmon', 'resmon']
        if any(app in process_lower for app in system_apps):
            return ('System Tools', Category.SYSTEM)

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

    def _extract_terminal_directory(self, window_title: str) -> Optional[str]:
        """
        Extract working directory from terminal window title.

        Handles common terminal title formats:
        - "user@host: ~/Projects/MyApp" → "MyApp"
        - "user@host:~/Projects/MyApp" → "MyApp"
        - "MINGW64:/c/Projects/MyApp" → "MyApp"
        - "/home/user/projects/foo" → "foo"
        - "/mnt/c/Projects/ActivityMonitor" → "ActivityMonitor"
        - "~/Projects/MyApp" → "MyApp"
        - "C:\\Projects\\MyApp" → "MyApp"
        - "Ubuntu" (no path) → None (use fallback)
        - "talwinter@Tal: ~/Projects/SomeProject" → "SomeProject"
        """
        if not window_title:
            return None

        title = window_title.strip()

        # Skip if it looks like a simple shell name without a path
        simple_names = ['ubuntu', 'bash', 'zsh', 'sh', 'powershell', 'cmd', 'pwsh',
                        'fish', 'terminal', 'console', 'wsl']
        if title.lower() in simple_names:
            return None

        # Try to find a path in the title
        path = None

        # Pattern 1: "user@host: /path" or "user@host:/path" (SSH/bash style)
        # Also handles "MINGW64:/c/path"
        match = re.search(r'[:\s](~?/[^\s]+|/[^\s]+)', title)
        if match:
            path = match.group(1)

        # Pattern 2: Windows path "C:\path" or "C:/path"
        if not path:
            match = re.search(r'[A-Za-z]:[/\\][^\s]*', title)
            if match:
                path = match.group(0)

        # Pattern 3: Just a Unix path at the start "/home/..." or "~/..."
        if not path:
            if title.startswith('~') or title.startswith('/'):
                # Take the path portion (up to space or end)
                match = re.match(r'(~?/[^\s]+)', title)
                if match:
                    path = match.group(1)

        # Pattern 4: WSL path starting with /mnt/
        if not path:
            match = re.search(r'/mnt/[a-z]/[^\s]*', title, re.IGNORECASE)
            if match:
                path = match.group(0)

        if not path:
            return None

        # Extract the last directory component from the path
        # Normalize path separators
        path = path.replace('\\', '/')

        # Remove trailing slash
        path = path.rstrip('/')

        # Get the last component
        parts = path.split('/')
        if parts:
            last_part = parts[-1]
            # Skip if last part is empty or looks like a drive letter
            if last_part and not re.match(r'^[a-zA-Z]$', last_part):
                # Clean up the directory name
                last_part = last_part.strip()
                if last_part and len(last_part) <= 50:
                    return last_part

        return None

    def _extract_teams_context(self, window_title: str) -> str:
        """
        Extract meeting/chat context from Teams window title.

        Teams window title patterns:
        - "Meeting Name - Microsoft Teams" → "Teams - Meeting Name"
        - "Meeting Name | Microsoft Teams" → "Teams - Meeting Name"
        - "John Doe | Chat" → "Teams - Chat: John Doe"
        - "Chat | John Doe, Jane Smith" → "Teams - Chat: John Doe, Jane Smith"
        - "Teams" (generic) → "Teams"
        - Call windows often have "Call with..." or specific meeting info

        Returns formatted string like "Teams - Meeting Name" or just "Teams".
        """
        if not window_title:
            return "Teams"

        title = window_title.strip()

        # Skip if just "Microsoft Teams" or empty
        if title.lower() in ['microsoft teams', 'teams', '']:
            return "Teams"

        # Meeting/call detection keywords
        meeting_keywords = ['meeting', 'call with', 'scheduled', 'standup', 'sync',
                           'review', 'planning', 'retro', '1:1', '1-1', 'one-on-one']

        # Pattern 1: "Title - Microsoft Teams" or "Title | Microsoft Teams"
        teams_suffix_pattern = re.compile(
            r'^(.+?)\s*[-|]\s*Microsoft\s*Teams\s*$',
            re.IGNORECASE
        )
        match = teams_suffix_pattern.match(title)
        if match:
            context = match.group(1).strip()
            if context and context.lower() not in ['microsoft', '']:
                # Truncate long meeting names
                if len(context) > 50:
                    context = context[:47] + "..."
                return f"Teams - {context}"

        # Pattern 2: "Something | Chat" (Teams chat window)
        chat_pattern = re.compile(r'^(.+?)\s*\|\s*Chat\s*$', re.IGNORECASE)
        match = chat_pattern.match(title)
        if match:
            person_or_group = match.group(1).strip()
            if person_or_group:
                if len(person_or_group) > 40:
                    person_or_group = person_or_group[:37] + "..."
                return f"Teams - Chat: {person_or_group}"

        # Pattern 3: "Chat | Names" (group chat)
        chat_prefix_pattern = re.compile(r'^Chat\s*\|\s*(.+)$', re.IGNORECASE)
        match = chat_prefix_pattern.match(title)
        if match:
            names = match.group(1).strip()
            if names:
                if len(names) > 40:
                    names = names[:37] + "..."
                return f"Teams - Chat: {names}"

        # Pattern 4: Check if it looks like a meeting by keywords
        title_lower = title.lower()
        for keyword in meeting_keywords:
            if keyword in title_lower:
                # Clean up the title for display
                clean_title = title.split(' - ')[0].split(' | ')[0].strip()
                if len(clean_title) > 50:
                    clean_title = clean_title[:47] + "..."
                return f"Teams - {clean_title}"

        # Pattern 5: Just "Person Name" without clear markers - likely a call or chat
        # If title doesn't contain common UI words, it might be a person/meeting name
        ui_words = ['activity', 'calendar', 'files', 'apps', 'search', 'settings',
                    'notifications', 'teams and channels', 'new teams']
        if not any(word in title_lower for word in ui_words):
            # Check if it has typical name patterns (contains spaces, reasonable length)
            if ' ' in title and 3 <= len(title) <= 60:
                # Likely a meeting or chat name
                clean_title = title.split(' - ')[0].split(' | ')[0].strip()
                if len(clean_title) > 50:
                    clean_title = clean_title[:47] + "..."
                if clean_title:
                    return f"Teams - {clean_title}"

        return "Teams"

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
        # Browsers
        ("chrome.exe", "GitHub - anthropics/claude-code"),
        ("msedge.exe", "Google Search - Work - Microsoft Edge"),
        # Communication - Teams with various title formats
        ("Teams.exe", "Weekly Standup - Microsoft Teams"),
        ("ms-teams.exe", "John Doe | Chat"),
        ("Teams.exe", "Chat | Jane Smith, Bob Wilson"),
        ("ms-teams.exe", "Project Review Meeting - Microsoft Teams"),
        ("Teams.exe", "Microsoft Teams"),  # Generic Teams window
        ("WhatsApp.exe", "WhatsApp"),
        # Remote Desktop
        ("mstsc.exe", "server01 - Remote Desktop Connection"),
        ("mstsc.exe", "192.168.1.100"),
        # Security
        ("FortiClient.exe", "FortiClient VPN"),
        # Editors
        ("notepad.exe", "Untitled - Notepad"),
        # System (should be hidden by default)
        ("explorer.exe", "Downloads"),
        ("explorer.exe", ""),
        # Terminal with directory extraction
        ("WindowsTerminal.exe", "talwinter@Tal: ~/Projects/ActivityMonitor"),
        ("WindowsTerminal.exe", "MINGW64:/c/Projects/SomeApp"),
        ("WindowsTerminal.exe", "/mnt/c/Projects/MyProject"),
        ("WindowsTerminal.exe", "Ubuntu"),
        ("powershell.exe", "C:\\Users\\talwinter\\Projects\\WebApi"),
    ]

    print("Project Mapper Test")
    print("-" * 60)

    for process, title in test_cases:
        project, category = mapper.map_activity(process, title)
        print(f"Process: {process}")
        print(f"Title: {title}")
        print(f"Project: {project}")
        print(f"Category: {category}")
        hidden = "(HIDDEN)" if category in Category.DEFAULT_HIDDEN else ""
        print(f"Status: {hidden or 'visible'}")
        print("-" * 60)
