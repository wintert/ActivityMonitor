#!/usr/bin/env python3
"""
Submit Hours to Admiral

Simple CLI to submit ActivityMonitor tracked hours to Admiral Pro.
Opens a visible browser so you can monitor the automation.

Usage:
    python submit_hours.py              # Submit today's hours
    python submit_hours.py --date 2026-01-19  # Submit specific date
    python submit_hours.py --login      # Just login and save session
    python submit_hours.py --mappings   # Show/edit project mappings
"""

import argparse
import sys
import os
from datetime import date, datetime, timedelta

# Add src directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from admiral_reporter import (
    AdmiralReporter, AdmiralProjectMapper, TimeEntry,
    aggregate_hours_for_admiral, PLAYWRIGHT_AVAILABLE
)


def print_banner():
    print("=" * 60)
    print("   ADMIRAL TIME REPORTER")
    print("   Submit ActivityMonitor hours to Admiral Pro")
    print("=" * 60)
    print()


def show_mappings(mapper: AdmiralProjectMapper):
    """Display current project mappings."""
    mappings = mapper.get_all_mappings()

    print("\nCurrent Project Mappings:")
    print("-" * 40)

    if not mappings:
        print("(No mappings configured)")
        print("\nTo add a mapping, edit: admiral_project_mappings.json")
        print("Format: {\"ActivityMonitor Tag\": \"Admiral Project Name\"}")
    else:
        for am_tag, admiral_proj in sorted(mappings.items()):
            print(f"  {am_tag} → {admiral_proj}")

    print()


def edit_mappings(mapper: AdmiralProjectMapper, db: Database):
    """Interactive mapping editor."""
    print("\n=== Project Mapping Editor ===")
    print()

    # Show ActivityMonitor project tags
    from datetime import datetime as dt
    today = dt.now()
    week_ago = today - timedelta(days=7)

    # Get recent project tags from activities
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT project_tag
        FROM activities
        WHERE project_tag IS NOT NULL
        AND timestamp >= ?
        ORDER BY project_tag
    ''', (week_ago.strftime('%Y-%m-%d'),))
    recent_tags = [row['project_tag'] for row in cursor.fetchall()]
    conn.close()

    print("Recent ActivityMonitor project tags (last 7 days):")
    for i, tag in enumerate(recent_tags, 1):
        admiral = mapper.get_admiral_project(tag)
        status = f" → {admiral}" if admiral else " (not mapped)"
        print(f"  {i}. {tag}{status}")

    print()
    print("Commands:")
    print("  add       - Add/update a mapping (will ask for details)")
    print("  remove    - Remove a mapping")
    print("  list      - Show all mappings")
    print("  quit      - Exit editor")
    print()

    while True:
        try:
            cmd = input(">>> ").strip().lower()
            if not cmd:
                continue

            if cmd in ('quit', 'exit', 'q'):
                break

            elif cmd == 'add':
                print("\n  Available ActivityMonitor tags:")
                for i, tag in enumerate(recent_tags, 1):
                    print(f"    {i}. {tag}")
                print()

                tag_input = input("  Enter tag name or number: ").strip()

                # Check if it's a number
                if tag_input.isdigit():
                    idx = int(tag_input) - 1
                    if 0 <= idx < len(recent_tags):
                        tag = recent_tags[idx]
                    else:
                        print("  Invalid number")
                        continue
                else:
                    tag = tag_input

                admiral = input("  Enter Admiral project name (exact): ").strip()

                if tag and admiral:
                    mapper.set_mapping(tag, admiral)
                    print(f"  ✓ Added: {tag} → {admiral}")
                else:
                    print("  Cancelled")

            elif cmd == 'remove':
                tag = input("  Enter tag name to remove: ").strip()
                if tag:
                    mapper.remove_mapping(tag)
                    print(f"  ✓ Removed: {tag}")

            elif cmd == 'list':
                mappings = mapper.get_all_mappings()
                if mappings:
                    print("\n  Current mappings:")
                    for am_tag, admiral_proj in sorted(mappings.items()):
                        print(f"    {am_tag} → {admiral_proj}")
                else:
                    print("  No mappings configured")
                print()

            else:
                print("  Unknown command. Try: add, remove, list, or quit")

        except KeyboardInterrupt:
            print()
            break
        except EOFError:
            break


def preview_submission(db: Database, mapper: AdmiralProjectMapper, target_date: date):
    """Preview what would be submitted without actually submitting."""
    print(f"\nPreview for {target_date.strftime('%A, %d/%m/%Y')}:")
    print("-" * 50)

    # Get hours grouped by project tag
    from datetime import datetime as dt
    summary = db.get_daily_summary_by_project_tag(dt.combine(target_date, dt.min.time()))

    if not summary:
        print("No activity recorded for this date.")
        return {}

    admiral_hours = {}
    unmapped = []

    for tag, data in summary.items():
        if tag is None:
            continue

        hours = data['active_seconds'] / 3600
        admiral_project = mapper.get_admiral_project(tag)

        if admiral_project:
            if admiral_project in admiral_hours:
                admiral_hours[admiral_project] += hours
            else:
                admiral_hours[admiral_project] = hours
            print(f"  ✓ {tag}: {hours:.2f}h → Admiral: {admiral_project}")
        else:
            unmapped.append((tag, hours))
            print(f"  ✗ {tag}: {hours:.2f}h → NOT MAPPED (will skip)")

    print()
    if admiral_hours:
        print("Will submit to Admiral:")
        for proj, hrs in sorted(admiral_hours.items()):
            print(f"  • {proj}: {hrs:.2f} hours")
    else:
        print("Nothing to submit (no mapped projects)")

    if unmapped:
        print()
        print("Unmapped projects (run with --mappings to configure):")
        for tag, hrs in unmapped:
            print(f"  • {tag}: {hrs:.2f}h")

    return {k: round(v, 2) for k, v in admiral_hours.items()}


def submit_hours(db: Database, mapper: AdmiralProjectMapper, target_date: date,
                default_comment: str, dry_run: bool = False):
    """Submit hours to Admiral."""

    # Preview first
    admiral_hours = preview_submission(db, mapper, target_date)

    if not admiral_hours:
        print("\nNothing to submit.")
        return

    if dry_run:
        print("\n[DRY RUN] Would submit the above entries.")
        return

    print()
    confirm = input("Submit these hours to Admiral? (yes/no): ").strip().lower()
    if confirm not in ('yes', 'y'):
        print("Cancelled.")
        return

    print()
    print("Opening browser for Admiral submission...")
    print("Watch the browser window - you can intervene if needed.")
    print()

    with AdmiralReporter(headless=False) as reporter:
        # Login first
        if not reporter.login():
            print("ERROR: Login failed. Please try again.")
            return

        print()
        print("Logged in! Starting submission...")
        print()

        # Submit each project
        results = {}
        for project, hours in admiral_hours.items():
            print(f"Submitting {project}: {hours}h...")

            entry = TimeEntry(
                date=target_date,
                project=project,
                sub_project=f"כללי {project}",
                hours=hours,
                comment=default_comment
            )

            success = reporter.submit_time(entry)
            results[project] = success

            if success:
                print(f"  ✓ {project}: Success")
            else:
                print(f"  ✗ {project}: FAILED")

        print()
        print("=" * 40)
        print("Summary:")
        succeeded = sum(1 for s in results.values() if s)
        print(f"  Submitted: {succeeded}/{len(results)}")

        if succeeded < len(results):
            print("  Some submissions failed. Check the browser for errors.")


def main():
    parser = argparse.ArgumentParser(
        description="Submit ActivityMonitor hours to Admiral Pro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python submit_hours.py              # Submit today's hours
  python submit_hours.py --date 2026-01-19
  python submit_hours.py --yesterday
  python submit_hours.py --login      # Just login and save session
  python submit_hours.py --mappings   # Configure project mappings
  python submit_hours.py --dry-run    # Preview without submitting
        """
    )

    parser.add_argument('--date', type=str, help='Date to submit (YYYY-MM-DD)')
    parser.add_argument('--yesterday', action='store_true', help='Submit yesterday\'s hours')
    parser.add_argument('--login', action='store_true', help='Just login and save session')
    parser.add_argument('--mappings', action='store_true', help='Show/edit project mappings')
    parser.add_argument('--dry-run', action='store_true', help='Preview without submitting')
    parser.add_argument('--comment', type=str, default='פיתוח', help='Comment for entries')

    args = parser.parse_args()

    print_banner()

    # Check Playwright
    if not PLAYWRIGHT_AVAILABLE and not args.mappings:
        print("ERROR: Playwright is not installed.")
        print()
        print("Install it with:")
        print("  pip install playwright")
        print("  playwright install chromium")
        print()
        sys.exit(1)

    # Initialize
    db = Database()
    mapper = AdmiralProjectMapper()

    # Handle commands
    if args.mappings:
        show_mappings(mapper)
        edit_mappings(mapper, db)
        return

    if args.login:
        print("Opening browser for login...")
        with AdmiralReporter(headless=False) as reporter:
            if reporter.login():
                print("\n✓ Login successful! Session saved for future use.")
            else:
                print("\n✗ Login failed or timed out.")
        return

    # Determine target date
    if args.yesterday:
        target_date = date.today() - timedelta(days=1)
    elif args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    else:
        target_date = date.today()

    # Submit hours
    submit_hours(db, mapper, target_date, args.comment, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
