"""
Camera presence detector module for ActivityMonitor.
Uses OpenCV to detect if a person is present at the desk via face detection.
"""

import time
import threading
import logging
from typing import Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.warning("OpenCV not available. Camera detection will be disabled.")


class CameraDetector:
    """
    Detects user presence using camera face detection.

    Uses OpenCV's Haar cascade classifier for face detection.
    Designed to be lightweight and privacy-conscious - no images are stored.
    """

    def __init__(
        self,
        check_interval_seconds: int = 10,
        away_threshold_seconds: int = 30,
        camera_index: int = 0
    ):
        """
        Initialize the camera detector.

        Args:
            check_interval_seconds: How often to check the camera
            away_threshold_seconds: Seconds without face before marking as away
            camera_index: Which camera to use (0 = default)
        """
        self.check_interval = check_interval_seconds
        self.away_threshold = away_threshold_seconds
        self.camera_index = camera_index

        self._enabled = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_face_time: Optional[float] = None
        self._face_detected = False
        self._camera: Optional[cv2.VideoCapture] = None
        self._face_cascade = None
        self._on_presence_change: Optional[Callable[[bool], None]] = None

        # Load face cascade classifier
        if OPENCV_AVAILABLE:
            self._load_cascade()

    def _load_cascade(self):
        """Load the Haar cascades for face detection."""
        try:
            # Load multiple cascades for better detection
            # Frontal face (default)
            frontal_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self._face_cascade = cv2.CascadeClassifier(frontal_path)

            # Profile face (for side views)
            profile_path = cv2.data.haarcascades + 'haarcascade_profileface.xml'
            self._profile_cascade = cv2.CascadeClassifier(profile_path)

            # Alternative frontal (more forgiving)
            alt_path = cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'
            self._alt_cascade = cv2.CascadeClassifier(alt_path)

            if self._face_cascade.empty():
                logger.error("Failed to load face cascade classifier")
                self._face_cascade = None
        except Exception as e:
            logger.error(f"Error loading face cascade: {e}")
            self._face_cascade = None
            self._profile_cascade = None
            self._alt_cascade = None

    @property
    def is_available(self) -> bool:
        """Check if camera detection is available."""
        return OPENCV_AVAILABLE and self._face_cascade is not None

    @property
    def is_enabled(self) -> bool:
        """Check if camera detection is currently enabled."""
        return self._enabled and self._running

    @property
    def is_present(self) -> bool:
        """Check if user is currently present (face detected recently)."""
        if not self._enabled:
            return True  # Assume present if camera is disabled

        if self._last_face_time is None:
            return False

        return (time.time() - self._last_face_time) < self.away_threshold

    @property
    def seconds_since_face(self) -> float:
        """Get seconds since last face detection."""
        if self._last_face_time is None:
            return float('inf')
        return time.time() - self._last_face_time

    def set_presence_callback(self, callback: Callable[[bool], None]):
        """Set callback for presence state changes."""
        self._on_presence_change = callback

    def start(self) -> bool:
        """
        Start camera detection.

        Returns:
            True if started successfully, False otherwise
        """
        if not self.is_available:
            logger.warning("Camera detection not available")
            return False

        if self._running:
            return True

        try:
            # Test camera access
            self._camera = cv2.VideoCapture(self.camera_index)
            if not self._camera.isOpened():
                logger.error(f"Could not open camera {self.camera_index}")
                return False

            # Start detection thread
            self._enabled = True
            self._running = True
            self._last_face_time = time.time()  # Assume present at start
            self._thread = threading.Thread(target=self._detection_loop, daemon=True)
            self._thread.start()

            logger.info("Camera detection started")
            return True

        except Exception as e:
            logger.error(f"Failed to start camera detection: {e}")
            self._cleanup()
            return False

    def stop(self):
        """Stop camera detection."""
        self._running = False
        self._enabled = False

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

        self._cleanup()
        logger.info("Camera detection stopped")

    def _cleanup(self):
        """Release camera resources."""
        if self._camera is not None:
            self._camera.release()
            self._camera = None

    def _detection_loop(self):
        """Main detection loop running in background thread."""
        was_present = True

        while self._running:
            try:
                face_detected = self._check_for_face()

                if face_detected:
                    self._last_face_time = time.time()
                    self._face_detected = True

                # Check for presence state change
                is_present = self.is_present
                if is_present != was_present:
                    if self._on_presence_change:
                        try:
                            self._on_presence_change(is_present)
                        except Exception as e:
                            logger.error(f"Presence callback error: {e}")

                was_present = is_present

            except Exception as e:
                logger.error(f"Detection loop error: {e}")

            # Wait for next check
            time.sleep(self.check_interval)

    def _check_for_face(self) -> bool:
        """
        Capture a frame and check for faces using multiple cascades.

        Returns:
            True if at least one face is detected
        """
        if self._camera is None or self._face_cascade is None:
            return False

        try:
            # Capture frame
            ret, frame = self._camera.read()
            if not ret or frame is None:
                return False

            # Convert to grayscale for detection
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Enhance contrast for low light (histogram equalization)
            gray = cv2.equalizeHist(gray)

            # Try frontal face detection (more forgiving parameters)
            faces = self._face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=3,  # Reduced from 5 for more sensitivity
                minSize=(20, 20),  # Smaller minimum size
                flags=cv2.CASCADE_SCALE_IMAGE
            )

            if len(faces) > 0:
                return True

            # Try alternative frontal cascade
            if self._alt_cascade is not None and not self._alt_cascade.empty():
                faces = self._alt_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    minSize=(20, 20)
                )
                if len(faces) > 0:
                    return True

            # Try profile face detection (for side views)
            if self._profile_cascade is not None and not self._profile_cascade.empty():
                # Check left profile
                faces = self._profile_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    minSize=(20, 20)
                )
                if len(faces) > 0:
                    return True

                # Check right profile (flip image)
                flipped = cv2.flip(gray, 1)
                faces = self._profile_cascade.detectMultiScale(
                    flipped,
                    scaleFactor=1.1,
                    minNeighbors=3,
                    minSize=(20, 20)
                )
                if len(faces) > 0:
                    return True

            return False

        except Exception as e:
            logger.error(f"Face detection error: {e}")
            return False

    def check_once(self) -> bool:
        """
        Perform a single face detection check.

        Useful for testing without starting the background loop.
        """
        if not self.is_available:
            return False

        camera = None
        try:
            camera = cv2.VideoCapture(self.camera_index)
            if not camera.isOpened():
                return False

            ret, frame = camera.read()
            if not ret or frame is None:
                return False

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )

            return len(faces) > 0

        except Exception as e:
            logger.error(f"Single check error: {e}")
            return False

        finally:
            if camera is not None:
                camera.release()

    def get_status(self) -> dict:
        """Get current camera detector status."""
        return {
            'available': self.is_available,
            'enabled': self._enabled,
            'running': self._running,
            'is_present': self.is_present,
            'seconds_since_face': self.seconds_since_face,
            'away_threshold': self.away_threshold,
            'camera_index': self.camera_index
        }


    def show_preview(self, duration_seconds: int = 10):
        """
        Show a preview window of the camera feed for testing.

        Args:
            duration_seconds: How long to show the preview
        """
        if not OPENCV_AVAILABLE:
            logger.error("OpenCV not available for preview")
            return False

        camera = None
        try:
            camera = cv2.VideoCapture(self.camera_index)
            if not camera.isOpened():
                logger.error("Could not open camera for preview")
                return False

            window_name = "Camera Preview - Press 'Q' to close"
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, 640, 480)

            start_time = time.time()
            while (time.time() - start_time) < duration_seconds:
                ret, frame = camera.read()
                if not ret:
                    break

                # Detect faces using all methods
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray_eq = cv2.equalizeHist(gray)  # Enhance for low light

                all_faces = []
                detection_method = ""

                # Try frontal face
                if self._face_cascade is not None:
                    faces = self._face_cascade.detectMultiScale(
                        gray_eq, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20)
                    )
                    if len(faces) > 0:
                        all_faces.extend(faces)
                        detection_method = "Frontal"

                # Try alt frontal
                if len(all_faces) == 0 and self._alt_cascade is not None and not self._alt_cascade.empty():
                    faces = self._alt_cascade.detectMultiScale(
                        gray_eq, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20)
                    )
                    if len(faces) > 0:
                        all_faces.extend(faces)
                        detection_method = "Alt Frontal"

                # Try profile
                if len(all_faces) == 0 and self._profile_cascade is not None and not self._profile_cascade.empty():
                    faces = self._profile_cascade.detectMultiScale(
                        gray_eq, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20)
                    )
                    if len(faces) > 0:
                        all_faces.extend(faces)
                        detection_method = "Profile"
                    else:
                        # Try flipped for right profile
                        flipped = cv2.flip(gray_eq, 1)
                        faces = self._profile_cascade.detectMultiScale(
                            flipped, scaleFactor=1.1, minNeighbors=3, minSize=(20, 20)
                        )
                        if len(faces) > 0:
                            # Adjust coordinates for flipped image
                            h, w = gray_eq.shape
                            for (x, y, fw, fh) in faces:
                                all_faces.append((w - x - fw, y, fw, fh))
                            detection_method = "Profile (R)"

                # Draw rectangles
                for (x, y, w, h) in all_faces:
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

                # Show status
                if len(all_faces) > 0:
                    status = f"DETECTED ({detection_method})"
                    color = (0, 255, 0)
                else:
                    status = "NOT DETECTED"
                    color = (0, 0, 255)

                cv2.putText(frame, f"Face: {status}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                cv2.putText(frame, "Low light? Contrast enhanced", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                cv2.imshow(window_name, frame)

                # Press 'Q' to quit early
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            cv2.destroyAllWindows()
            return True

        except Exception as e:
            logger.error(f"Preview error: {e}")
            return False

        finally:
            if camera is not None:
                camera.release()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    # Test the camera detector
    print("Camera Detector Test")
    print("-" * 50)

    detector = CameraDetector(
        check_interval_seconds=2,
        away_threshold_seconds=10
    )

    print(f"OpenCV available: {OPENCV_AVAILABLE}")
    print(f"Detector available: {detector.is_available}")

    if not detector.is_available:
        print("Camera detection not available. Install opencv-python.")
        exit(1)

    def on_presence_change(is_present: bool):
        status = "PRESENT" if is_present else "AWAY"
        print(f"\n*** Presence changed: {status} ***\n")

    detector.set_presence_callback(on_presence_change)

    print("\nStarting camera detection...")
    if detector.start():
        print("Camera detection started. Press Ctrl+C to stop.")
        print("Step away from camera to test 'away' detection.\n")

        try:
            while True:
                status = detector.get_status()
                presence = "PRESENT" if status['is_present'] else "AWAY"
                print(f"[{presence}] Last face: {status['seconds_since_face']:.1f}s ago", end='\r')
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n\nStopping...")
            detector.stop()
            print("Stopped.")
    else:
        print("Failed to start camera detection.")
