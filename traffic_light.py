#!/usr/bin/env python3
"""
Claude Code Traffic Light - System Tray Indicator (Multi-Session)

Shows a traffic light icon in the system tray that aggregates Claude Code's
state across ALL running sessions:

  🟢 Green  - All sessions working / idle
  🟡 Yellow - At least one session needs attention (yellow wins)
  🔴 Red    - All sessions stopped (or no sessions detected)

Uses per-session status files written by set_status.py.
  Status files: ~/.claude/traffic_light_sessions/<session_id>.json
  TTL cleanup: sessions not updated in 5 minutes are removed.
"""

import json
import os
import sys
import time
import threading
import atexit
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PIL import Image, ImageDraw
import pystray


# --- Configuration ---
HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "traffic_light_sessions"
LEGACY_STATUS_FILE = CLAUDE_DIR / "traffic_light_status"
PID_FILE = CLAUDE_DIR / "traffic_light.pid"
LOG_FILE = CLAUDE_DIR / "traffic_light.log"
POLL_INTERVAL = 0.5  # seconds
ICON_SIZE = 64  # pixels
SESSION_TTL = timedelta(minutes=5)

# Colors
GREEN = (0, 200, 50)
YELLOW = (255, 200, 0)
RED = (220, 40, 40)
DIM_YELLOW = (180, 140, 50)
GRAY = (100, 100, 100)

# Status priority for aggregation (higher index = higher priority)
STATUS_PRIORITY = {"red": 0, "green": 1, "yellow": 2}


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
    draw.ellipse([margin, margin, size - margin, size - margin],
                 outline=(60, 60, 60), width=3)
    draw.ellipse([margin + 3, margin + 3, size - margin - 3, size - margin - 3],
                 fill=color)
    highlight_margin = size // 3
    draw.ellipse(
        [highlight_margin, size // 6, size - highlight_margin, size // 2],
        fill=(255, 255, 255, 60)
    )
    return image


def read_all_sessions():
    """
    Read all per-session status files.
    Returns (aggregated_status, session_details).

    aggregated_status: one of 'green', 'yellow', 'red', 'unknown'
    session_details: list of dicts with {session_id, status, updated_at}
    """
    sessions = []
    now = datetime.now(timezone.utc)

    if SESSIONS_DIR.exists():
        for f in sorted(SESSIONS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sid = data.get("session_id", f.stem)
                status = data.get("status", "unknown")
                updated_str = data.get("updated_at", "")

                # Parse timestamp
                try:
                    updated = datetime.fromisoformat(updated_str)
                except (ValueError, TypeError):
                    updated = now

                # Skip stale sessions
                if now - updated > SESSION_TTL:
                    # Clean up stale file
                    f.unlink(missing_ok=True)
                    startup_log(f"Cleaned stale session: {sid}")
                    continue

                if status in ("green", "yellow", "red"):
                    sessions.append({
                        "session_id": sid,
                        "status": status,
                        "updated_at": updated,
                    })
            except (json.JSONDecodeError, OSError):
                # Corrupt file, clean it up
                f.unlink(missing_ok=True)

    # Aggregate: pick the highest-priority status
    if not sessions:
        # Fall back to legacy single-file for backward compat
        legacy = _read_legacy_status()
        if legacy != "unknown":
            return legacy, []
        return "unknown", []

    # Priority aggregation: yellow wins over everything, then green, then red
    aggregated = "unknown"
    for s in sessions:
        if STATUS_PRIORITY.get(s["status"], -1) > STATUS_PRIORITY.get(aggregated, -1):
            aggregated = s["status"]

    return aggregated, sessions


def _read_legacy_status():
    """Read legacy single status file (backward compat)."""
    try:
        if LEGACY_STATUS_FILE.exists():
            content = LEGACY_STATUS_FILE.read_text(encoding="utf-8").strip()
            if content in ("green", "yellow", "red"):
                return content
    except Exception:
        pass
    return "unknown"


def build_tooltip(aggregated, sessions):
    """Build a descriptive tooltip from session data."""
    base = "Claude Code Traffic Light"

    if not sessions:
        return f"{base}\nNo active sessions"

    # Status line
    status_line = {
        "green": "🟢 All clear — no sessions need attention",
        "yellow": "🟡 ATTENTION — a session needs your confirmation!",
        "red": "🔴 All sessions stopped",
        "unknown": "⚫ Status unknown",
    }.get(aggregated, "")

    # Session summary
    counts = {}
    for s in sessions:
        counts[s["status"]] = counts.get(s["status"], 0) + 1

    parts = []
    if counts.get("green"):
        parts.append(f"{counts['green']} working")
    if counts.get("yellow"):
        parts.append(f"{counts['yellow']} need attention")
    if counts.get("red"):
        parts.append(f"{counts['red']} stopped")

    session_line = ", ".join(parts) if parts else ""

    return f"{base}\n{status_line}\n{len(sessions)} sessions: {session_line}"


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
    """Check if a process with the given PID is running."""
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    try:
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
                startup_log(f"Cleaning up stale PID file (PID {pid} is dead)")
                PID_FILE.unlink(missing_ok=True)
    except Exception:
        PID_FILE.unlink(missing_ok=True)
    return False


def check_environment():
    """Check that the environment can support a system tray icon."""
    backends = []
    try:
        import tkinter
        backends.append("tkinter")
    except ImportError:
        pass
    try:
        import win32api
        backends.append("win32")
    except ImportError:
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
    """System tray traffic light application with multi-session aggregation."""

    def __init__(self):
        self.current_status = "unknown"
        self.session_count = 0
        self.blink_state = False
        self.blink_counter = 0
        self.running = True
        self._last_session_log = ""

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
            return self.icons["yellow_on"] if self.blink_state else self.icons["yellow_off"]
        return self.icons.get(self.current_status, self.icons["unknown"])

    def poll_status(self, icon):
        """Poll all session files and update tray accordingly."""
        startup_log("Polling thread started (multi-session mode)")
        while self.running:
            try:
                aggregated, sessions = read_all_sessions()

                if aggregated != self.current_status or len(sessions) != self.session_count:
                    # Only log on actual changes
                    if aggregated != self.current_status:
                        yellow_sessions = [s["session_id"] for s in sessions if s["status"] == "yellow"]
                        detail = ""
                        if yellow_sessions:
                            detail = f" (yellow: {', '.join(yellow_sessions[:3])})"
                        startup_log(
                            f"Status: {self.current_status} -> {aggregated} "
                            f"[{len(sessions)} sessions]{detail}"
                        )

                    self.current_status = aggregated
                    self.session_count = len(sessions)
                    icon.icon = self.get_current_icon()
                    icon.title = build_tooltip(aggregated, sessions)

                # Handle blink for yellow
                if self.current_status == "yellow":
                    self.blink_counter += 1
                    if self.blink_counter >= 3:
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
        startup_log("Starting traffic light tray app (multi-session mode)...")

        # Ensure sessions directory exists
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

        icon = pystray.Icon(
            name="claude-traffic-light",
            title="Claude Code Traffic Light",
            icon=self.icons["unknown"],
            menu=pystray.Menu(
                pystray.MenuItem("🚦 Claude Code Traffic Light", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    lambda text: f"Sessions: {self.session_count}",
                    None,
                    enabled=False
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self.on_stop),
            ),
        )

        poll_thread = threading.Thread(target=self.poll_status, args=(icon,), daemon=True)
        poll_thread.start()

        startup_log("Tray icon created, entering main loop...")
        icon.run()
        startup_log("Tray icon main loop exited")


def main():
    """Entry point."""
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
        elif cmd in ("--help", "-h"):
            print(__doc__)
            print("Usage: python traffic_light.py [--kill|--check|--force]")
            return
        else:
            print(f"Unknown option: {cmd}", file=sys.stderr)
            print(f"Usage: python {sys.argv[0]} [--kill|--check|--force]")
            return

    if is_already_running():
        print("Traffic light is already running.", file=sys.stderr)
        print(f"  Use 'python {sys.argv[0]} --force' to force restart.", file=sys.stderr)
        return

    ok, msg = check_environment()
    if not ok:
        print(f"ERROR: {msg}", file=sys.stderr)
        startup_log(f"Environment check failed: {msg}")
        sys.exit(1)

    startup_log(f"Environment OK: {msg}")

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    write_pid()
    atexit.register(remove_pid)

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
