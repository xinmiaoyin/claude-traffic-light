#!/usr/bin/env python3
"""
Claude Code Traffic Light - Status Setter

Writes the current status to the status file read by traffic_light.py.
Called by Claude Code hooks to update the traffic light indicator.

Usage:
  python3 set_status.py green     # Working / idle
  python3 set_status.py yellow    # Needs attention (permission prompt)
  python3 set_status.py red       # Stopped / error
"""

import sys
from datetime import datetime
from pathlib import Path


STATUS_FILE = Path.home() / ".claude" / "traffic_light_status"
VALID_STATUSES = {"green", "yellow", "red"}


def set_status(status: str):
    """Write the status to the status file."""
    status = status.lower().strip()

    if status not in VALID_STATUSES:
        print(f"Error: Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
              file=sys.stderr)
        sys.exit(1)

    # Ensure directory exists
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write status with timestamp
    timestamp = datetime.now().isoformat()
    STATUS_FILE.write_text(f"{status}", encoding="utf-8")

    # Also write a log entry for debugging
    log_file = STATUS_FILE.parent / "traffic_light.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {status}\n")

    print(f"Traffic light set to: {status.upper()}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <green|yellow|red>", file=sys.stderr)
        sys.exit(1)

    set_status(sys.argv[1])
