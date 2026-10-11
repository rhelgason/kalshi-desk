#!/usr/bin/env bash
# One-time setup for the Kalshi Desk bot on a fresh Ubuntu 24.04 VM.
#
#   curl -fsSL <raw url of this file> | bash      (or copy it over and run: bash setup.sh)
#
# What it does:
#   1. installs Python, git, and a 1 GB swap file (free-tier VMs have ~1 GB RAM)
#   2. creates an SSH "deploy key" so this VM can read your private repo
#   3. clones the repo, builds a virtualenv
#   4. asks for your DATABASE_URL and stores it in /etc/kalshi-desk.env
#   5. installs a systemd service that keeps `python -m desk paper` running,
#      restarting it if it crashes and starting it on boot
set -euo pipefail

REPO="${REPO:-git@github.com:rhelgason/kalshi-desk.git}"
APP_DIR="$HOME/kalshi-desk"
KEY="$HOME/.ssh/kalshi_desk_deploy"

echo "==> Installing packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip git >/dev/null

if ! swapon --show | grep -q /swapfile; then
  echo "==> Adding 1 GB swap"
  sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

if [ ! -f "$KEY" ]; then
  echo "==> Creating a read-only deploy key for GitHub"
  mkdir -p ~/.ssh && ssh-keygen -t ed25519 -N "" -C "kalshi-desk-vm" -f "$KEY" >/dev/null
  cat >> ~/.ssh/config <<CFG
Host github.com
  IdentityFile $KEY
  StrictHostKeyChecking accept-new
CFG
fi

if ! ssh -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
  echo
  echo "Add this public key to the repo as a read-only deploy key:"
  echo "  GitHub -> rhelgason/kalshi-desk -> Settings -> Deploy keys -> Add deploy key"
  echo "  (or on your Mac: gh repo deploy-key add <file> --repo rhelgason/kalshi-desk --title vm)"
  echo
  cat "$KEY.pub"
  echo
  read -rp "Press Enter once the key is added... "
fi

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone "$REPO" "$APP_DIR"
fi

echo "==> Building virtualenv"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

if [ ! -f /etc/kalshi-desk.env ]; then
  echo
  read -rsp "Paste your DATABASE_URL (Supabase session pooler string; input hidden): " DBURL
  echo
  printf 'DATABASE_URL=%s\n' "$DBURL" | sudo tee /etc/kalshi-desk.env >/dev/null
  sudo chmod 600 /etc/kalshi-desk.env
fi

echo "==> Installing systemd service"
sed -e "s|__USER__|$USER|g" -e "s|__APP_DIR__|$APP_DIR|g" "$APP_DIR/deploy/kalshi-desk.service" \
  | sudo tee /etc/systemd/system/kalshi-desk.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now kalshi-desk
sleep 5
sudo systemctl --no-pager status kalshi-desk | head -12
echo
echo "Done. Follow the logs with:  journalctl -u kalshi-desk -f"
