"""
Window tracker module for ActivityMonitor.
Tracks the currently active (foreground) window on Windows.
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


# Windows API constants and functions
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

# Function prototypes
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class POINT(ctypes.Structure):
    """Windows POINT structure."""
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    """Windows RECT structure."""
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]


@dataclass
class WindowInfo:
    """Information about the current foreground window."""
    handle: int
    title: str
    process_name: str
    process_id: int
    cursor_in_window: bool = True  # Is mouse cursor within window bounds?

    def __str__(self):
        return f"{self.process_name}: {self.title}"


class WindowTracker:
    """Tracks the currently active window."""

    def __init__(self):
        self._last_window: Optional[WindowInfo] = None

    def get_active_window(self) -> Optional[WindowInfo]:
        """Get information about the currently active window."""
        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            # Get window title
            title = self._get_window_title(hwnd)

            # Get process information
            process_id = self._get_window_process_id(hwnd)
            process_name = self._get_process_name(process_id) if process_id else "Unknown"

            # Check if cursor is within window bounds (for multi-monitor accuracy)
            cursor_in_window = self._is_cursor_in_window(hwnd)

            window_info = WindowInfo(
                handle=hwnd,
                title=title,
                process_name=process_name,
                process_id=process_id or 0,
                cursor_in_window=cursor_in_window
            )

            self._last_window = window_info
            return window_info

        except Exception as e:
            logger.error(f"Error getting active window: {e}")
            return self._last_window

    def _is_cursor_in_window(self, hwnd: int) -> bool:
        """Check if the mouse cursor is within the window bounds."""
        try:
            # Get cursor position
            cursor = POINT()
            user32.GetCursorPos(ctypes.byref(cursor))

            # Get window rectangle
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

            # Check if cursor is within bounds
            return (rect.left <= cursor.x <= rect.right and
                    rect.top <= cursor.y <= rect.bottom)
        except Exception:
            return True  # Assume in window if we can't determine

    def _get_window_title(self, hwnd: int) -> str:
        """Get the title of a window."""
        try:
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return ""

            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            return buffer.value
        except Exception:
            return ""

    def _get_window_process_id(self, hwnd: int) -> Optional[int]:
        """Get the process ID of a window."""
        try:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value if pid.value else None
        except Exception:
            return None

    def _get_process_name(self, pid: int) -> str:
        """Get the process name from a process ID."""
        # Try QueryFullProcessImageNameW first (works for elevated processes)
        try:
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid
            )
            if handle:
                try:
                    buffer = ctypes.create_unicode_buffer(260)
                    size = wintypes.DWORD(260)
                    # QueryFullProcessImageNameW: kernel32 function
                    result = kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
                    if result and buffer.value:
                        # Extract just the filename from full path
                        import os
                        return os.path.basename(buffer.value)
                finally:
                    kernel32.CloseHandle(handle)
        except Exception:
            pass

        # Fallback: try GetModuleBaseNameW (original method)
        try:
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                False,
                pid
            )

            if not handle:
                return "Unknown"

            try:
                buffer = ctypes.create_unicode_buffer(260)
                psapi.GetModuleBaseNameW(handle, None, buffer, 260)
                return buffer.value if buffer.value else "Unknown"
            finally:
                kernel32.CloseHandle(handle)

        except Exception:
            return "Unknown"

    @property
    def last_window(self) -> Optional[WindowInfo]:
        """Get the last known active window."""
        return self._last_window

    def has_window_changed(self) -> bool:
        """Check if the active window has changed since last check."""
        current = self.get_active_window()
        if current is None or self._last_window is None:
            return True

        return (current.handle != self._last_window.handle or
                current.title != self._last_window.title)

    def get_all_windows(self) -> list:
        """
        Enumerate all visible windows.

        Returns a list of WindowInfo objects for all visible windows.
        Useful for detecting background activity like Teams meetings.
        """
        windows = []

        def enum_callback(hwnd, _):
            """Callback for EnumWindows."""
            try:
                # Skip invisible windows
                if not user32.IsWindowVisible(hwnd):
                    return True

                # Get window title
                title = self._get_window_title(hwnd)
                if not title:  # Skip windows without title
                    return True

                # Get process info
                process_id = self._get_window_process_id(hwnd)
                process_name = self._get_process_name(process_id) if process_id else "Unknown"

                window_info = WindowInfo(
                    handle=hwnd,
                    title=title,
                    process_name=process_name,
                    process_id=process_id or 0,
                    cursor_in_window=False  # Not relevant for enumeration
                )
                windows.append(window_info)

            except Exception as e:
                logger.debug(f"Error enumerating window {hwnd}: {e}")

            return True  # Continue enumeration

        # Define the callback type
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        callback = WNDENUMPROC(enum_callback)

        # Enumerate all top-level windows
        user32.EnumWindows(callback, 0)

        return windows


def get_active_window_info() -> Optional[WindowInfo]:
    """Convenience function to get active window info."""
    tracker = WindowTracker()
    return tracker.get_active_window()


if __name__ == "__main__":
    # Test the window tracker
    import time

    tracker = WindowTracker()
    print("Window Tracker Test - Press Ctrl+C to stop")
    print("-" * 50)

    try:
        while True:
            window = tracker.get_active_window()
            if window:
                print(f"[{window.process_name}] {window.title[:60]}...")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopped.")
