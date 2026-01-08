"""
Idle detector module for ActivityMonitor.
Detects user inactivity based on keyboard/mouse input.
"""

import ctypes
from ctypes import Structure, POINTER, WINFUNCTYPE, c_uint, sizeof
import time
import logging

logger = logging.getLogger(__name__)


class LASTINPUTINFO(Structure):
    """Windows LASTINPUTINFO structure."""
    _fields_ = [
        ('cbSize', c_uint),
        ('dwTime', c_uint),
    ]


class IdleDetector:
    """
    Detects user idle time using Windows API.

    Uses GetLastInputInfo which tracks the last keyboard or mouse input.
    """

    def __init__(self, idle_threshold_seconds: int = 180):
        """
        Initialize the idle detector.

        Args:
            idle_threshold_seconds: Seconds of inactivity before considered idle (default 3 min)
        """
        self.idle_threshold_seconds = idle_threshold_seconds
        self._last_input_info = LASTINPUTINFO()
        self._last_input_info.cbSize = sizeof(LASTINPUTINFO)

    def get_idle_seconds(self) -> float:
        """
        Get the number of seconds since the last user input.

        Returns:
            Seconds since last keyboard/mouse activity
        """
        try:
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(self._last_input_info))

            # GetTickCount returns milliseconds since system start
            current_tick = ctypes.windll.kernel32.GetTickCount()
            last_input_tick = self._last_input_info.dwTime

            # Handle tick count overflow (happens every ~49 days)
            if current_tick < last_input_tick:
                # Overflow occurred
                idle_ms = (0xFFFFFFFF - last_input_tick) + current_tick
            else:
                idle_ms = current_tick - last_input_tick

            return idle_ms / 1000.0

        except Exception as e:
            logger.error(f"Error getting idle time: {e}")
            return 0.0

    def is_idle(self) -> bool:
        """
        Check if the user is currently idle.

        Returns:
            True if idle time exceeds threshold, False otherwise
        """
        return self.get_idle_seconds() >= self.idle_threshold_seconds

    def set_threshold(self, seconds: int):
        """Update the idle threshold."""
        self.idle_threshold_seconds = seconds

    def get_activity_status(self) -> dict:
        """
        Get detailed activity status.

        Returns:
            Dictionary with idle_seconds, is_idle, and threshold
        """
        idle_seconds = self.get_idle_seconds()
        return {
            'idle_seconds': idle_seconds,
            'is_idle': idle_seconds >= self.idle_threshold_seconds,
            'threshold_seconds': self.idle_threshold_seconds,
            'time_until_idle': max(0, self.idle_threshold_seconds - idle_seconds)
        }


class IdleMonitor:
    """
    Monitors idle state changes over time.

    Useful for tracking when the user became idle and returned.
    """

    def __init__(self, idle_threshold_seconds: int = 180):
        self.detector = IdleDetector(idle_threshold_seconds)
        self._was_idle = False
        self._idle_start_time = None
        self._active_start_time = time.time()

    def update(self) -> dict:
        """
        Update and return the current activity state.

        Returns:
            Dictionary with current state and any transitions
        """
        is_idle = self.detector.is_idle()
        idle_seconds = self.detector.get_idle_seconds()

        result = {
            'is_idle': is_idle,
            'idle_seconds': idle_seconds,
            'became_idle': False,
            'became_active': False,
            'idle_duration': 0,
            'active_duration': 0,
        }

        # Check for state transitions
        if is_idle and not self._was_idle:
            # Just became idle
            result['became_idle'] = True
            self._idle_start_time = time.time()
            if self._active_start_time:
                result['active_duration'] = time.time() - self._active_start_time
            logger.debug("User became idle")

        elif not is_idle and self._was_idle:
            # Just became active
            result['became_active'] = True
            self._active_start_time = time.time()
            if self._idle_start_time:
                result['idle_duration'] = time.time() - self._idle_start_time
            self._idle_start_time = None
            logger.debug("User became active")

        self._was_idle = is_idle
        return result

    def set_threshold(self, seconds: int):
        """Update the idle threshold."""
        self.detector.set_threshold(seconds)

    @property
    def is_idle(self) -> bool:
        """Current idle state."""
        return self._was_idle


if __name__ == "__main__":
    # Test the idle detector
    print("Idle Detector Test - Press Ctrl+C to stop")
    print("Move your mouse or press keys to reset idle time")
    print("-" * 50)

    detector = IdleDetector(idle_threshold_seconds=10)  # 10 seconds for testing

    try:
        while True:
            status = detector.get_activity_status()
            idle_indicator = "IDLE" if status['is_idle'] else "ACTIVE"
            print(f"[{idle_indicator}] Idle for {status['idle_seconds']:.1f}s "
                  f"(threshold: {status['threshold_seconds']}s)", end='\r')
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopped.")
