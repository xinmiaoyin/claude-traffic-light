# 🚦 Claude Code Traffic Light

A Windows system tray indicator that shows Claude Code's real-time status — no more switching screens to check if Claude needs your confirmation!

| Icon | Status | Meaning |
|------|--------|---------|
| 🟢 **Green** | Working | Claude Code is running normally or idle |
| 🟡 **Yellow** (blinking) | Attention | Claude Code needs your permission/confirmation |
| 🔴 **Red** | Stopped | Claude Code has stopped or session ended |

## How It Works

```
┌─────────────────────┐         ┌──────────────────────┐
│   Claude Code        │         │  Traffic Light Tray  │
│   (VS Code)          │         │  (Windows Taskbar)   │
│                      │  hooks  │                      │
│  Permission prompt ──┼────────>│  🟡 Yellow blinking  │
│  Tool executed     ──┼────────>│  🟢 Green            │
│  Session stopped   ──┼────────>│  🔴 Red              │
└─────────────────────┘         └──────────────────────┘
```

Claude Code hooks automatically update the tray icon. No manual interaction needed.

## Quick Install

```bash
# Clone the repo
git clone https://github.com/xinmiaoyin/claude-traffic-light.git
cd claude-traffic-light

# Run the installer (installs Python deps + configures hooks)
bash install.sh
```

The installer will:
1. Install Python dependencies (`pystray`, `pillow`)
2. Configure Claude Code hooks in `~/.claude/settings.json`
3. Start the traffic light tray app

## Manual Setup

### Prerequisites

- Python 3.8+
- Git Bash (comes with Git for Windows)

### Step 1: Install Python packages

```bash
pip install pystray pillow
```

### Step 2: Start the traffic light

```bash
python3 traffic_light.py &
```

### Step 3: Configure Claude Code hooks

Add this to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 /d/git/claude-traffic-light/set_status.py green"
        }]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [{
          "type": "command",
          "command": "python3 /d/git/claude-traffic-light/set_status.py yellow"
        }]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 /d/git/claude-traffic-light/set_status.py green"
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 /d/git/claude-traffic-light/set_status.py red"
        }]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 /d/git/claude-traffic-light/set_status.py red"
        }]
      }
    ]
  }
}
```

## Usage

### Manual status control

```bash
python3 set_status.py green    # Set to working
python3 set_status.py yellow   # Set to attention needed
python3 set_status.py red      # Set to stopped
```

### Stop the traffic light

- Right-click the tray icon → **Exit**
- Or force cleanup: `python3 traffic_light.py --kill`

## Status Log

All status changes are logged to `~/.claude/traffic_light.log` for debugging:

```
[2026-06-15T14:30:01] green
[2026-06-15T14:30:15] yellow
[2026-06-15T14:30:18] green
```

## Files

| File | Purpose |
|------|---------|
| `traffic_light.py` | System tray app (the traffic light) |
| `set_status.py` | CLI tool to update status (called by hooks) |
| `install.sh` | One-click installer |
| `~/.claude/traffic_light_status` | Status file (written by hooks, read by tray) |
| `~/.claude/traffic_light.log` | Status change log |
| `~/.claude/traffic_light.pid` | PID lock file |
