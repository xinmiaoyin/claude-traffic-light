#!/usr/bin/env python3
"""
Claude Code Traffic Light - Status Setter (Multi-Session)

Writes per-session status files read by traffic_light.py.
Called by Claude Code hooks to update the traffic light indicator.

When called from a Claude Code hook, it reads the hook JSON from stdin
to extract the session_id. For manual use, pass --session-id <id>.

Usage:
  # Called by Claude Code hook (reads session_id from stdin JSON):
  python3 set_status.py green

  # Manual usage (specify session explicitly):
  python3 set_status.py yellow --session-id vscode-main
  python3 set_status.py red --session-id vscode-project2
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


CLAUDE_DIR = Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "traffic_light_sessions"
LEGACY_STATUS_FILE = CLAUDE_DIR / "traffic_light_status"  # Backward compat
VALID_STATUSES = {"green", "yellow", "red"}
SESSION_TTL_SECONDS = 300  # Sessions inactive for 5 min are considered stale


def get_session_id():
    """
    Try to extract session_id from Claude Code hook stdin JSON.
    Falls back to a hostname-based default if not in a hook context.
    """
    # Try stdin first (Claude Code passes hook data as JSON via stdin)
    try:
        # Non-blocking check: only read if stdin is a pipe (not a terminal)
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                data = json.loads(raw)
                sid = data.get("session_id")
                if sid:
                    return sid
    except (json.JSONDecodeError, IOError):
        pass

    # Fallback: generate from hostname + working directory
    hostname = os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "unknown"))
    cwd = os.getcwd()
    # Create a deterministic ID per working directory
    return f"{hostname}-{Path(cwd).name}"


def set_status(status: str, session_id: str = None):
    """Write the status for a specific session."""
    status = status.lower().strip()

    if status not in VALID_STATUSES:
        print(f"Error: Invalid status '{status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
              file=sys.stderr)
        sys.exit(1)

    if session_id is None:
        session_id = get_session_id()

    # Ensure directories exist
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Write per-session status file
    session_file = SESSIONS_DIR / f"{session_id}.json"
    data = {
        "session_id": session_id,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    session_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Also update legacy status file for backward compat
    LEGACY_STATUS_FILE.write_text(f"{status}", encoding="utf-8")

    # Log
    timestamp = datetime.now().isoformat()
    log_file = CLAUDE_DIR / "traffic_light.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{session_id}] {status}\n")

    print(f"[{session_id}] → {status.upper()}")


if __name__ == "__main__":
    args = sys.argv[1:]
    session_id = None

    # Parse --session-id from args
    positional = []
    i = 0
    while i < len(args):
        if args[i] == "--session-id" and i + 1 < len(args):
            session_id = args[i + 1]
            i += 2
        elif args[i] == "--help" or args[i] == "-h":
            print(__doc__)
            sys.exit(0)
        else:
            positional.append(args[i])
            i += 1

    if not positional:
        print(f"Usage: python3 {sys.argv[0]} <green|yellow|red> [--session-id <id>]",
              file=sys.stderr)
        sys.exit(1)

    set_status(positional[0], session_id=session_id)
