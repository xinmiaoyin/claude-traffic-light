#!/usr/bin/env bash
# =============================================================================
# Claude Code Traffic Light - Installation Script
# =============================================================================
# Installs dependencies and configures Claude Code hooks for the traffic light.
#
# Usage:
#   bash install.sh          # Install and configure
#   bash install.sh --dry-run # Preview changes without applying
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS_FILE="$HOME/.claude/settings.json"
DRY_RUN=false

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Claude Code Traffic Light - Installer      ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ---- Step 1: Install Python dependencies ----
echo -e "${YELLOW}[1/3] Installing Python dependencies...${NC}"

DEPS=("pystray" "pillow")
for dep in "${DEPS[@]}"; do
    if python3 -c "import ${dep//-/_}" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $dep already installed"
    else
        if $DRY_RUN; then
            echo -e "  ${YELLOW}[DRY RUN] Would install:${NC} pip install $dep"
        else
            echo -e "  Installing $dep..."
            pip install "$dep"
            echo -e "  ${GREEN}✓${NC} $dep installed"
        fi
    fi
done

echo ""

# ---- Step 2: Configure Claude Code hooks ----
echo -e "${YELLOW}[2/3] Configuring Claude Code hooks...${NC}"

HOOKS_JSON=$(cat <<EOF
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${SCRIPT_DIR}/set_status.py green"
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${SCRIPT_DIR}/set_status.py yellow"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${SCRIPT_DIR}/set_status.py green"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${SCRIPT_DIR}/set_status.py red"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${SCRIPT_DIR}/set_status.py red"
          }
        ]
      }
    ]
  }
}
EOF
)

if $DRY_RUN; then
    echo -e "  ${YELLOW}[DRY RUN] Would add hooks to:${NC} $SETTINGS_FILE"
    echo "$HOOKS_JSON" | python3 -m json.tool 2>/dev/null || echo "$HOOKS_JSON"
else
    # If settings.json exists, merge hooks into it
    if [ -f "$SETTINGS_FILE" ]; then
        echo "  Existing settings found, merging hooks..."
        # Use Python to merge JSON (more reliable than jq on Windows)
        python3 -c "
import json, sys
from pathlib import Path

settings_file = Path.home() / '.claude' / 'settings.json'
new_hooks = $HOOKS_JSON

# Load existing settings
with open(settings_file, 'r') as f:
    existing = json.load(f)

# Merge hooks: new hooks override existing ones for the same event
existing_hooks = existing.get('hooks', {})
for event, hook_list in new_hooks['hooks'].items():
    existing_hooks[event] = hook_list

existing['hooks'] = existing_hooks

# Write back
with open(settings_file, 'w') as f:
    json.dump(existing, f, indent=2)
    f.write('\n')

print('  Hooks merged into settings.json')
"
    else
        echo "  No existing settings, creating new settings.json..."
        mkdir -p "$HOME/.claude"
        echo "$HOOKS_JSON" | python3 -m json.tool > "$SETTINGS_FILE"
    fi
    echo -e "  ${GREEN}✓${NC} Hooks configured"
fi

echo ""

# ---- Step 3: Start traffic light ----
echo -e "${YELLOW}[3/3] Starting traffic light...${NC}"

TRAFFIC_LIGHT_SCRIPT="${SCRIPT_DIR}/traffic_light.py"

if $DRY_RUN; then
    echo -e "  ${YELLOW}[DRY RUN] Would run:${NC} python3 $TRAFFIC_LIGHT_SCRIPT &"
else
    # Check if already running
    PID_FILE="$HOME/.claude/traffic_light.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} Traffic light already running (PID: $PID)"
        else
            rm -f "$PID_FILE"
            python3 "$TRAFFIC_LIGHT_SCRIPT" &
            echo -e "  ${GREEN}✓${NC} Traffic light started (was stale)"
        fi
    else
        python3 "$TRAFFIC_LIGHT_SCRIPT" &
        echo -e "  ${GREEN}✓${NC} Traffic light started"
    fi
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Installation complete! 🚦                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "The traffic light will now show in your system tray:"
echo "  🟢 Green  = Claude Code is working"
echo "  🟡 Yellow = Claude Code needs your attention"
echo "  🔴 Red    = Claude Code has stopped"
echo ""
echo "To stop the traffic light, right-click the tray icon → Exit"
echo "To reinstall:  bash ${SCRIPT_DIR}/install.sh"
