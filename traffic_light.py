#!/usr/bin/env python3
"""
Claude Code Traffic Light - System Tray Indicator

Shows a traffic light icon in the system tray that reflects Claude Code's state:
  🟢 Green  - Working / idle
  🟡 Yellow - Needs user attention (permission prompt)
  🔴 Red    - Stopped / error

The tray app polls a status file (~/.claude/traffic_light_status) every 500ms.
Use set_status.py to update the status from Claude Code hooks.
"""

import json
import os
import sys
import time
import threading
import atexit
import traceback
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw
import pystray


# --- Configuration ---
HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
STATUS_FILE = CLAUDE_DIR / "traffic_light_status"
PID_FILE = CLAUDE_DIR / "traffic_light.pid"
LOG_FILE = CLAUDE_DIR / "traffic_light.log"
POLL_INTERVAL = 0.5  # seconds
ICON_SIZE = 64  # pixels (will be scaled by system tray)

# Colors
GREEN = (0, 200, 50)
YELLOW = (255, 200, 0)
RED = (220, 40, 40)
DIM_YELLOW = (180, 140, 50)  # For blink-off phase
GRAY = (100, 100, 100)

# Tooltip texts
TOOLTIPS = {
    "green": "Claude Code: Working",
    "yellow": "Claude Code: Needs Attention!",
    "red": "Claude Code: Stopped",
    "unknown": "Claude Code: Unknown",
}


def startup_log(msg):
    """Log a message to the log file and print to stderr."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    try:
        CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, file=sys.stderr)


def draw_traffic_light(color, size=ICON_SIZE):
    """Draw a circular traffic light icon."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = 4
    # Outer ring (dark border)
    draw.ellipse([margin, margin, size - margin, size - margin],
                 outline=(60, 60, 60), width=3)
    # Inner filled circle
    draw.ellipse([margin + 3, margin + 3, size - margin - 3, size - margin - 3],
                 fill=color)
    # Highlight (gloss effect)
    highlight_margin = size // 3
    draw.ellipse(
        [highlight_margin, size // 6, size - highlight_margin, size // 2],
        fill=(255, 255, 255, 60)
    )

    return image


def read_status():
    """Read status from the status file. Returns 'unknown' if file missing/corrupt."""
    try:
        if STATUS_FILE.exists():
            content = STATUS_FILE.read_text(encoding="utf-8").strip()
            if content in ("green", "yellow", "red"):
                return content
    except Exception:
        pass
    return "unknown"


def write_pid():
    """Write current PID to lock file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def remove_pid():
    """Remove PID lock file."""
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def is_process_alive(pid):
    """Check if a process with the given PID is running. Works on Windows and Unix."""
    try:
        # Try psutil first (most reliable)
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass

    try:
        # Try Windows API
        import ctypes
        from ctypes import wintypes

        SYNCHRONIZE = 0x100000
        PROCESS_QUERY_INFORMATION = 0x0400
        STILL_ACTIVE = 259

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | SYNCHRONIZE, False, pid)
        if handle == 0:
            return False

        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return exit_code.value == STILL_ACTIVE
    except Exception:
        pass

    try:
        # Fallback: os.kill with signal 0
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_already_running():
    """Check if another instance is already running."""
    try:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            if is_process_alive(pid):
                return True
            else:
                # Process not alive, clean up stale PID
                startup_log(f"Cleaning up stale PID file (PID {pid} is dead)")
                PID_FILE.unlink(missing_ok=True)
    except Exception:
        # If PID file is corrupt, just remove it
        PID_FILE.unlink(missing_ok=True)
    return False


def check_environment():
    """Check that the environment can support a system tray icon. Returns (ok, message)."""
    # Check available backends
    backends = []

    try:
        import tkinter
        backends.append("tkinter")
    except ImportError as e:
        pass

    try:
        import win32api
        backends.append("win32")
    except ImportError as e:
        pass

    try:
        import gi
        backends.append("gtk")
    except ImportError:
        pass

    if not backends:
        return False, (
            "No GUI backend available!\n"
            "  On Windows, install one of:\n"
            "    pip install pywin32     (recommended)\n"
            "  Or ensure tkinter is installed with Python."
        )

    return True, f"Backend available: {', '.join(backends)}"


class TrafficLightApp:
    """System tray traffic light application."""

    def __init__(self):
        self.current_status = "unknown"
        self.blink_state = False  # For yellow blinking
        self.blink_counter = 0
        self.running = True

        # Pre-generate icons
        self.icons = {
            "green": draw_traffic_light(GREEN),
            "yellow_on": draw_traffic_light(YELLOW),
            "yellow_off": draw_traffic_light(DIM_YELLOW),
            "red": draw_traffic_light(RED),
            "unknown": draw_traffic_light(GRAY),
        }

    def get_current_icon(self):
        """Get the appropriate icon for current state."""
        if self.current_status == "yellow":
            # Blink every 3 poll cycles (1.5 seconds)
            return self.icons["yellow_on"] if self.blink_state else self.icons["yellow_off"]
        return self.icons.get(self.current_status, self.icons["unknown"])

    def poll_status(self, icon):
        """Poll the status file and update tray accordingly."""
        startup_log("Polling thread started")
        while self.running:
            try:
                new_status = read_status()

                if new_status != self.current_status:
                    startup_log(f"Status changed: {self.current_status} -> {new_status}")
                    self.current_status = new_status
                    icon.icon = self.get_current_icon()
                    icon.title = TOOLTIPS.get(new_status, TOOLTIPS["unknown"])

                # Handle blink for yellow
                if self.current_status == "yellow":
                    self.blink_counter += 1
                    if self.blink_counter >= 3:  # Toggle every ~1.5s
                        self.blink_state = not self.blink_state
                        self.blink_counter = 0
                        icon.icon = self.get_current_icon()
                else:
                    self.blink_state = False
                    self.blink_counter = 0

            except Exception as e:
                startup_log(f"Poll error: {e}")

            time.sleep(POLL_INTERVAL)

    def on_stop(self, icon):
        """Handle tray exit."""
        startup_log("User requested exit")
        self.running = False
        icon.stop()

    def run(self):
        """Start the tray application."""
        startup_log("Starting traffic light tray app...")

        # Create the tray icon
        icon = pystray.Icon(
            name="claude-traffic-light",
            title=TOOLTIPS["unknown"],
            icon=self.icons["unknown"],
            menu=pystray.Menu(
                pystray.MenuItem("🚦 Claude Code Traffic Light", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Status: Green", self._set_green),
                pystray.MenuItem("Status: Yellow", self._set_yellow),
                pystray.MenuItem("Status: Red", self._set_red),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self.on_stop),
            ),
        )

        # Start polling thread
        poll_thread = threading.Thread(target=self.poll_status, args=(icon,), daemon=True)
        poll_thread.start()

        startup_log("Tray icon created, entering main loop...")
        # Run the tray icon (blocking)
        icon.run()
        startup_log("Tray icon main loop exited")

    def _set_green(self, icon, item):
        """Manually set status to green."""
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text("green")
        startup_log("Manually set to GREEN")

    def _set_yellow(self, icon, item):
        """Manually set status to yellow."""
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text("yellow")
        startup_log("Manually set to YELLOW")

    def _set_red(self, icon, item):
        """Manually set status to red."""
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE.write_text("red")
        startup_log("Manually set to RED")


def main():
    """Entry point."""
    # Parse command line
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--kill":
            remove_pid()
            print("PID file removed.")
            return
        elif cmd == "--check":
            ok, msg = check_environment()
            print(msg)
            if ok:
                print("Environment looks good!")
            else:
                print("Environment issues found.")
            return
        elif cmd == "--force":
            remove_pid()
            startup_log("Force-starting (PID file cleared)")
        else:
            print(f"Unknown option: {cmd}", file=sys.stderr)
            print(f"Usage: python {sys.argv[0]} [--kill|--check|--force]")
            return

    # Prevent duplicate instances
    if is_already_running():
        print("Traffic light is already running.", file=sys.stderr)
        print(f"  Use 'python {sys.argv[0]} --force' to force restart.", file=sys.stderr)
        return

    # Check environment
    ok, msg = check_environment()
    if not ok:
        print(f"ERROR: {msg}", file=sys.stderr)
        startup_log(f"Environment check failed: {msg}")
        sys.exit(1)

    startup_log(f"Environment OK: {msg}")

    # Ensure status directory exists
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write PID
    write_pid()
    atexit.register(remove_pid)

    # Start the app
    app = TrafficLightApp()
    try:
        app.run()
    except KeyboardInterrupt:
        startup_log("Interrupted by Ctrl+C")
    except Exception as e:
        startup_log(f"Fatal error: {e}\n{traceback.format_exc()}")
        print(f"ERROR: {e}", file=sys.stderr)
        print(f"Check {LOG_FILE} for details.", file=sys.stderr)
    finally:
        remove_pid()
        startup_log("Traffic light stopped")


if __name__ == "__main__":
    main()
