"""
Admiral Time Reporting Automation

Automates time entry submission to Admiral Pro using Playwright browser automation.
Handles Azure AD authentication and the Admiral time entry UI.
"""

import logging
import json
import os
from datetime import datetime, date
from typing import Optional, Dict, List
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Playwright is optional - only imported when needed
try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Install with: pip install playwright && playwright install chromium")


@dataclass
class TimeEntry:
    """Represents a time entry to submit to Admiral."""
    date: date
    project: str  # Admiral project name (e.g., "Ewave")
    sub_project: str  # Admiral sub-project (e.g., "כללי Ewave")
    hours: float
    comment: str


class AdmiralReporter:
    """
    Automates time reporting to Admiral Pro.

    Usage:
        reporter = AdmiralReporter()
        reporter.login()  # Opens browser for Azure AD login
        reporter.submit_time(TimeEntry(...))
        reporter.close()
    """

    ADMIRAL_URL = "https://admiral.co.il/AdmiralPro_ssl2//Main/Frame_Main.aspx?C=F1308D9B"
    AUTH_STATE_FILE = "admiral_auth_state.json"

    def __init__(self, headless: bool = False, auth_state_dir: Optional[str] = None):
        """
        Initialize the Admiral reporter.

        Args:
            headless: Run browser in headless mode (default False for login visibility)
            auth_state_dir: Directory to store authentication state
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is required for Admiral automation. "
                "Install with: pip install playwright && playwright install chromium"
            )

        self.headless = headless
        self.auth_state_dir = auth_state_dir or os.path.dirname(os.path.abspath(__file__))
        self.auth_state_path = os.path.join(self.auth_state_dir, self.AUTH_STATE_FILE)

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._logged_in = False

    def _start_browser(self):
        """Start the browser if not already running."""
        if self._playwright is None:
            self._playwright = sync_playwright().start()

        if self._browser is None:
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                slow_mo=100  # Slight delay for stability
            )

        # Try to load existing auth state
        if self._context is None:
            if os.path.exists(self.auth_state_path):
                try:
                    self._context = self._browser.new_context(
                        storage_state=self.auth_state_path
                    )
                    logger.info("Loaded saved authentication state")
                except Exception as e:
                    logger.warning(f"Failed to load auth state: {e}")
                    self._context = self._browser.new_context()
            else:
                self._context = self._browser.new_context()

        if self._page is None:
            self._page = self._context.new_page()

    def _save_auth_state(self):
        """Save the current authentication state for reuse."""
        if self._context:
            try:
                self._context.storage_state(path=self.auth_state_path)
                logger.info(f"Saved authentication state to {self.auth_state_path}")
            except Exception as e:
                logger.warning(f"Failed to save auth state: {e}")

    def login(self, timeout_ms: int = 120000) -> bool:
        """
        Open browser and wait for user to complete Azure AD login.

        The browser will open to the Admiral login page. Complete the Azure AD
        login manually. Once logged in, the session will be saved for future use.

        Args:
            timeout_ms: Maximum time to wait for login (default 2 minutes)

        Returns:
            True if login successful, False otherwise
        """
        self._start_browser()

        logger.info("Navigating to Admiral...")
        self._page.goto(self.ADMIRAL_URL, timeout=60000)

        # Check if we're already logged in (no redirect to login.microsoftonline.com)
        current_url = self._page.url
        if "login.microsoftonline.com" not in current_url and "admiral" in current_url.lower():
            # Check for a known element that indicates we're logged in
            try:
                # Wait for the page to be fully loaded
                self._page.wait_for_load_state("networkidle", timeout=10000)
                # Check if we're on the main Admiral page (not login)
                if "admiral" in self._page.url.lower() and "login" not in self._page.url.lower():
                    logger.info("Already logged in (session restored)")
                    self._logged_in = True
                    return True
            except:
                pass

        # Need to login - wait for user to complete Azure AD flow
        logger.info("Please complete Azure AD login in the browser...")
        print("\n" + "=" * 50)
        print("ADMIRAL LOGIN REQUIRED")
        print("=" * 50)
        print("1. Complete the Azure AD login in the browser window")
        print("2. Wait until you see the Admiral time report page")
        print("3. Press ENTER here to continue")
        print("=" * 50 + "\n")

        try:
            # Wait for user to confirm they've logged in
            input("Press ENTER when you see the Admiral report page...")

            # Check all pages/tabs - Admiral might have opened in a new tab
            all_pages = self._context.pages
            print(f"  Found {len(all_pages)} browser tab(s)")

            admiral_page = None
            for page in all_pages:
                url = page.url.lower()
                print(f"  Tab URL: {page.url[:80]}...")
                if "admiral" in url or "tmura" in url:
                    admiral_page = page
                    break

            if admiral_page:
                self._page = admiral_page
                print("  ✓ Found Admiral page!")
            else:
                # Maybe it's in the same page, just check if user confirmed
                print("  Using current page (user confirmed login)")

            # Wait for page to be ready
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=10000)
            except:
                pass

            print("  ✓ Login successful!")
            logger.info("Login successful!")
            self._logged_in = True
            self._save_auth_state()
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def _get_main_frame(self):
        """Get the main content frame (handles iframes)."""
        # Check if content is in an iframe
        frames = self._page.frames
        print(f"  Found {len(frames)} frame(s)")

        # Find frame with actual content (has inputs)
        best_frame = None
        max_inputs = 0

        for i, frame in enumerate(frames):
            url = frame.url
            try:
                input_count = frame.locator("input").count()
            except:
                input_count = 0
            print(f"    Frame {i}: {input_count} inputs - {url[:50]}...")

            # Pick the frame with the most inputs
            if input_count > max_inputs:
                max_inputs = input_count
                best_frame = frame

        if best_frame and max_inputs > 0:
            print(f"  Using frame with {max_inputs} inputs")
            return best_frame

        # Return main page if no good iframe found
        return self._page

    def _select_project(self, project_name: str) -> bool:
        """
        Select a project from the dropdown filter.

        The dropdown is a jQuery UI autocomplete widget (#ui-id-1).

        Args:
            project_name: The project name to select (e.g., "Ewave", "מכון התקנים הישראלי On Line+PO")

        Returns:
            True if successful
        """
        try:
            print(f"  Selecting project: {project_name}")

            # Get the correct frame (might be in iframe)
            frame = self._get_main_frame()

            # Debug: show what inputs exist
            inputs = frame.locator("input")
            print(f"  Found {inputs.count()} input(s) on page")

            # Find and click the PROJECT dropdown input (not the user dropdown)
            # There are multiple autocomplete inputs - user is first, project is second
            dropdown_input = None

            # First, try to find all autocomplete inputs
            autocomplete_inputs = frame.locator("input.ui-autocomplete-input")
            autocomplete_count = autocomplete_inputs.count()
            print(f"  Found {autocomplete_count} autocomplete inputs")

            if autocomplete_count >= 2:
                # Second autocomplete is the project dropdown
                dropdown_input = autocomplete_inputs.nth(1)
                print(f"  Using 2nd autocomplete (project dropdown)")
            elif autocomplete_count == 1:
                dropdown_input = autocomplete_inputs.first
                print(f"  Using only autocomplete found")
            else:
                # Try other selectors
                selectors = [
                    "input[id*='project']",
                    "input[id*='customer']",
                    "input[id*='client']",
                    "[role='combobox']",
                ]
                for selector in selectors:
                    elem = frame.locator(selector).first
                    if elem.count() > 0:
                        print(f"  Found dropdown with selector: {selector}")
                        dropdown_input = elem
                        break

            if dropdown_input is None:
                # Show available inputs for debugging
                print("  Available inputs:")
                for i in range(min(5, inputs.count())):
                    inp = inputs.nth(i)
                    try:
                        inp_id = inp.get_attribute("id") or "(no id)"
                        inp_class = inp.get_attribute("class") or "(no class)"
                        print(f"    {i}: id={inp_id}, class={inp_class[:30]}")
                    except:
                        pass

                # Try the first visible input
                dropdown_input = inputs.first

            # Click to open the dropdown
            dropdown_input.click()
            frame.wait_for_timeout(300)

            # Click again (some dropdowns need double interaction)
            dropdown_input.click()
            frame.wait_for_timeout(500)

            # Wait for the dropdown list to appear (check main page too, dropdowns often render outside iframe)
            dropdown_visible = False
            dropdown_list = None

            # Check in frame first
            for selector in ["#ui-id-1", ".ui-autocomplete", "ul.ui-menu"]:
                dropdown_list = frame.locator(selector)
                if dropdown_list.count() > 0:
                    try:
                        dropdown_list.wait_for(state="visible", timeout=1000)
                        dropdown_visible = True
                        print(f"  Found dropdown in frame: {selector}")
                        break
                    except:
                        pass

            # Check main page (dropdowns sometimes render at page level)
            if not dropdown_visible:
                for selector in ["#ui-id-1", ".ui-autocomplete", "ul.ui-menu"]:
                    dropdown_list = self._page.locator(selector)
                    if dropdown_list.count() > 0:
                        try:
                            dropdown_list.wait_for(state="visible", timeout=1000)
                            dropdown_visible = True
                            print(f"  Found dropdown in main page: {selector}")
                            break
                        except:
                            pass

            if not dropdown_visible:
                print("  Dropdown not visible, typing to search...")
                dropdown_input.fill("")
                dropdown_input.type(project_name[:15], delay=50)
                frame.wait_for_timeout(1000)

            # Debug: show all menu items found
            for location, loc_name in [(frame, "frame"), (self._page, "page")]:
                menu_items = location.locator("li.ui-menu-item")
                count = menu_items.count()
                print(f"  {loc_name}: found {count} menu items")
                if count > 0 and count <= 10:
                    for i in range(count):
                        try:
                            text = menu_items.nth(i).inner_text()
                            print(f"    - {text[:40]}")
                        except:
                            pass

            # Find and click the matching project item (search both frame and page)
            project_item = None
            search_locations = [frame, self._page]

            for location in search_locations:
                item = location.locator(f"li.ui-menu-item:has-text('{project_name}')")
                if item.count() > 0:
                    project_item = item.first
                    break

                # Try partial match with first word
                partial_name = project_name.split()[0] if ' ' in project_name else project_name
                item = location.locator(f"li.ui-menu-item:has-text('{partial_name}')")
                if item.count() > 0:
                    project_item = item.first
                    print(f"  Using partial match: {partial_name}")
                    break

            if project_item:
                project_item.click()
                print(f"  ✓ Selected: {project_name}")
            else:
                print(f"  ✗ Project not found: {project_name}")
                self._page.keyboard.press("Escape")
                return False

            # Wait for grid to update
            frame.wait_for_timeout(1000)
            return True

        except Exception as e:
            logger.error(f"Failed to select project {project_name}: {e}")
            return False

    def _click_date_cell(self, target_date: date, row_index: int = 0) -> bool:
        """
        Click on a date cell in the grid to open the entry balloon.

        Args:
            target_date: The date to click
            row_index: Which row (project) to click (0-based)

        Returns:
            True if successful
        """
        try:
            # Format date as shown in the UI (DD/MM)
            date_str = target_date.strftime("%d/%m")

            # Find the column header with this date
            # Then click the corresponding cell in the target row
            # The grid structure needs inspection - for now use a general approach

            # Try to find a cell containing the date
            cell_selector = f"td:has-text('{date_str}')"
            cells = self._page.locator(cell_selector)

            if cells.count() > row_index:
                cells.nth(row_index).click()
                self._page.wait_for_timeout(500)
                return True

            logger.warning(f"Could not find cell for date {date_str}")
            return False

        except Exception as e:
            logger.error(f"Failed to click date cell: {e}")
            return False

    def _click_balloon(self) -> bool:
        """Click the balloon that appears after clicking a cell."""
        try:
            # The balloon is a small popup that appears on the cell
            # Look for it and click
            balloon = self._page.locator(".balloon, .popup-trigger, [class*='balloon']").first
            if balloon.count() > 0:
                balloon.click()
                self._page.wait_for_timeout(500)
                return True

            # Alternative: double-click the cell might open directly
            return True

        except Exception as e:
            logger.error(f"Failed to click balloon: {e}")
            return False

    def _fill_time_entry_popup(self, hours: float, comment: str) -> bool:
        """
        Fill the time entry popup form.

        Args:
            hours: Total hours to enter (סכום כולל)
            comment: Comment text (הערות)

        Returns:
            True if successful
        """
        try:
            # Wait for popup to appear
            self._page.wait_for_selector("text=סכום כולל", timeout=5000)

            # Find and fill the hours field (סכום כולל)
            # The field appears to be an input near the "סכום כולל" label
            hours_input = self._page.locator("input[type='text']").filter(
                has=self._page.locator("text=סכום כולל")
            ).first

            # Alternative: find by position relative to label
            if hours_input.count() == 0:
                # Try finding input fields and use the one for hours
                inputs = self._page.locator("input[type='text']")
                # The hours input is typically the first numeric field
                for i in range(inputs.count()):
                    inp = inputs.nth(i)
                    # Check if it looks like an hours field
                    if inp.is_visible():
                        inp.fill(str(hours))
                        break
            else:
                hours_input.fill(str(hours))

            # Find and fill the comment field (הערות)
            comment_input = self._page.locator("input[type='text'], textarea").filter(
                has=self._page.locator("text=הערות")
            ).first

            if comment_input.count() == 0:
                # Try finding a textarea or larger text input
                textarea = self._page.locator("textarea").first
                if textarea.count() > 0:
                    textarea.fill(comment)
                else:
                    # Find the last text input (usually comments)
                    inputs = self._page.locator("input[type='text']")
                    if inputs.count() > 1:
                        inputs.last.fill(comment)
            else:
                comment_input.fill(comment)

            return True

        except Exception as e:
            logger.error(f"Failed to fill time entry popup: {e}")
            return False

    def _save_and_close_popup(self) -> bool:
        """Save the time entry and close the popup."""
        try:
            # Look for save/submit button
            # Common patterns: button with text, specific class, or icon
            save_selectors = [
                "button:has-text('שמור')",
                "button:has-text('אישור')",
                "input[type='submit']",
                ".save-btn",
                "[class*='save']",
                "button[type='submit']",
            ]

            for selector in save_selectors:
                btn = self._page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    self._page.wait_for_timeout(1000)
                    return True

            # Try clicking outside to close (some UIs auto-save)
            self._page.keyboard.press("Escape")
            self._page.wait_for_timeout(500)
            return True

        except Exception as e:
            logger.error(f"Failed to save popup: {e}")
            return False

    def submit_time(self, entry: TimeEntry) -> bool:
        """
        Submit a single time entry to Admiral.

        Args:
            entry: The TimeEntry to submit

        Returns:
            True if successful
        """
        if not self._logged_in:
            if not self.login():
                return False

        logger.info(f"Submitting time entry: {entry.date} - {entry.project} - {entry.hours}h")

        # Step 1: Select the project
        if not self._select_project(entry.project):
            return False

        # Step 2: Click the date cell
        if not self._click_date_cell(entry.date):
            return False

        # Step 3: Click the balloon to open popup
        if not self._click_balloon():
            return False

        # Step 4: Fill the popup form
        if not self._fill_time_entry_popup(entry.hours, entry.comment):
            return False

        # Step 5: Save and close
        if not self._save_and_close_popup():
            return False

        logger.info("Time entry submitted successfully")
        return True

    def submit_daily_summary(self,
                            target_date: date,
                            project_hours: Dict[str, float],
                            default_comment: str = "פיתוח") -> Dict[str, bool]:
        """
        Submit time entries for multiple projects for a single day.

        Args:
            target_date: The date to submit for
            project_hours: Dict mapping Admiral project names to hours
            default_comment: Default comment to use for all entries

        Returns:
            Dict mapping project names to success status
        """
        results = {}

        for project, hours in project_hours.items():
            if hours <= 0:
                continue

            entry = TimeEntry(
                date=target_date,
                project=project,
                sub_project=f"כללי {project}",
                hours=hours,
                comment=default_comment
            )

            results[project] = self.submit_time(entry)

        return results

    def close(self):
        """Close the browser and cleanup."""
        if self._page:
            self._page.close()
            self._page = None

        if self._context:
            self._context.close()
            self._context = None

        if self._browser:
            self._browser.close()
            self._browser = None

        if self._playwright:
            self._playwright.stop()
            self._playwright = None

        self._logged_in = False
        logger.info("Admiral reporter closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


class AdmiralProjectMapper:
    """
    Maps ActivityMonitor project tags to Admiral projects.

    Stores mappings in a JSON file for persistence.
    """

    MAPPINGS_FILE = "admiral_project_mappings.json"

    def __init__(self, mappings_dir: Optional[str] = None):
        """
        Initialize the project mapper.

        Args:
            mappings_dir: Directory to store mappings file
        """
        self.mappings_dir = mappings_dir or os.path.dirname(os.path.abspath(__file__))
        self.mappings_path = os.path.join(self.mappings_dir, self.MAPPINGS_FILE)
        self._mappings: Dict[str, str] = {}
        self._load_mappings()

    def _load_mappings(self):
        """Load mappings from file."""
        if os.path.exists(self.mappings_path):
            try:
                with open(self.mappings_path, 'r', encoding='utf-8') as f:
                    self._mappings = json.load(f)
                logger.info(f"Loaded {len(self._mappings)} project mappings")
            except Exception as e:
                logger.warning(f"Failed to load mappings: {e}")
                self._mappings = {}

    def _save_mappings(self):
        """Save mappings to file."""
        try:
            with open(self.mappings_path, 'w', encoding='utf-8') as f:
                json.dump(self._mappings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save mappings: {e}")

    def set_mapping(self, activity_monitor_tag: str, admiral_project: str):
        """
        Set a mapping from ActivityMonitor tag to Admiral project.

        Args:
            activity_monitor_tag: The project tag from ActivityMonitor
            admiral_project: The corresponding Admiral project name
        """
        self._mappings[activity_monitor_tag] = admiral_project
        self._save_mappings()

    def get_admiral_project(self, activity_monitor_tag: str) -> Optional[str]:
        """
        Get the Admiral project for an ActivityMonitor tag.

        Args:
            activity_monitor_tag: The project tag from ActivityMonitor

        Returns:
            Admiral project name, or None if no mapping exists
        """
        return self._mappings.get(activity_monitor_tag)

    def get_all_mappings(self) -> Dict[str, str]:
        """Get all current mappings."""
        return self._mappings.copy()

    def remove_mapping(self, activity_monitor_tag: str):
        """Remove a mapping."""
        if activity_monitor_tag in self._mappings:
            del self._mappings[activity_monitor_tag]
            self._save_mappings()


def aggregate_hours_for_admiral(db, target_date: date,
                                 mapper: AdmiralProjectMapper) -> Dict[str, float]:
    """
    Aggregate ActivityMonitor hours by Admiral project for a given date.

    Args:
        db: Database instance
        target_date: Date to aggregate
        mapper: Project mapper instance

    Returns:
        Dict mapping Admiral project names to total hours
    """
    from datetime import datetime as dt

    # Get summary by project tag for the date
    summary = db.get_daily_summary_by_project_tag(dt.combine(target_date, dt.min.time()))

    admiral_hours: Dict[str, float] = {}

    for tag, data in summary.items():
        if tag is None:
            continue

        admiral_project = mapper.get_admiral_project(tag)
        if admiral_project:
            # Convert seconds to hours
            hours = data['active_seconds'] / 3600

            if admiral_project in admiral_hours:
                admiral_hours[admiral_project] += hours
            else:
                admiral_hours[admiral_project] = hours

    # Round to 2 decimal places
    return {k: round(v, 2) for k, v in admiral_hours.items()}


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Admiral Time Reporter")
    parser.add_argument("--login", action="store_true", help="Just login and save session")
    parser.add_argument("--test", action="store_true", help="Test submit a dummy entry")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.login:
        with AdmiralReporter(headless=False) as reporter:
            if reporter.login():
                print("Login successful! Session saved.")
            else:
                print("Login failed.")

    elif args.test:
        print("Test mode - would submit entry")
        entry = TimeEntry(
            date=date.today(),
            project="Ewave",
            sub_project="כללי Ewave",
            hours=1.0,
            comment="בדיקה"
        )
        print(f"Entry: {entry}")
