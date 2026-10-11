#!/usr/bin/env bash
# Pull the latest code onto the VM and restart the bot.
set -euo pipefail
cd "$HOME/kalshi-desk"
git pull --ff-only
.venv/bin/pip install -q -r requirements-bot.txt
sudo systemctl restart kalshi-desk
sudo systemctl --no-pager status kalshi-desk | head -5
