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
from pathlib import Path

from PIL import Image, ImageDraw
import pystray


# --- Configuration ---
STATUS_FILE = Path.home() / ".claude" / "traffic_light_status"
PID_FILE = Path.home() / ".claude" / "traffic_light.pid"
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


def is_already_running():
    """Check if another instance is already running."""
    try:
        if PID_FILE.exists():
            pid = int(PID_FILE.read_text().strip())
            # Check if process is still alive
            try:
                os.kill(pid, 0)  # Signal 0 = just check existence
                return True
            except OSError:
                # Process not alive, clean up stale PID
                PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return False


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

    def update_tray(self, icon):
        """Called by pystray to update the icon."""
        icon.icon = self.get_current_icon()

    def poll_status(self, icon):
        """Poll the status file and update tray accordingly."""
        while self.running:
            new_status = read_status()

            if new_status != self.current_status:
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

            time.sleep(POLL_INTERVAL)

    def on_stop(self, icon):
        """Handle tray exit."""
        self.running = False
        icon.stop()

    def run(self):
        """Start the tray application."""
        # Create the tray icon
        icon = pystray.Icon(
            name="claude-traffic-light",
            title=TOOLTIPS["unknown"],
            icon=self.icons["unknown"],
            menu=pystray.Menu(
                pystray.MenuItem("Claude Code Traffic Light", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self.on_stop),
            ),
        )

        # Start polling thread
        poll_thread = threading.Thread(target=self.poll_status, args=(icon,), daemon=True)
        poll_thread.start()

        # Run the tray icon (blocking)
        icon.run()


def main():
    """Entry point."""
    # Parse command line
    if len(sys.argv) > 1 and sys.argv[1] == "--kill":
        remove_pid()
        print("Traffic light PID file removed.")
        return

    # Prevent duplicate instances
    if is_already_running():
        print("Traffic light is already running. Exiting.")
        print(f"  (PID file: {PID_FILE})")
        print(f"  Run '{os.path.basename(sys.argv[0])} --kill' to force cleanup.")
        return

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
        pass
    finally:
        remove_pid()


if __name__ == "__main__":
    main()
