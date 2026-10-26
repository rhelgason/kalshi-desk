#!/bin/sh
# Put a Kalshi API key on the always-on server without it passing through anything else.
#   deploy/add-kalshi-key.sh ~/Downloads/<the downloaded key file> <Key ID>
# Copies the private key to /etc/kalshi-desk.key (readable by root and the desk user only), points
# /etc/kalshi-desk.env at it, and deletes the local download. Prints nothing secret.
set -eu
FILE="$1"; KEY_ID="$2"; HOST="${DESK_HOST:-root@104.131.18.118}"
grep -q "PRIVATE KEY" "$FILE" || { echo "That file doesn't look like a private key: $FILE"; exit 1; }
scp -q "$FILE" "$HOST:/etc/kalshi-desk.key"
ssh "$HOST" "chown root:desk /etc/kalshi-desk.key && chmod 640 /etc/kalshi-desk.key &&
  sed -i '/^KALSHI_API_KEY_ID=/d; /^KALSHI_PRIVATE_KEY_PATH=/d' /etc/kalshi-desk.env &&
  printf 'KALSHI_API_KEY_ID=%s\nKALSHI_PRIVATE_KEY_PATH=/etc/kalshi-desk.key\n' '$KEY_ID' >> /etc/kalshi-desk.env"
rm -P "$FILE" 2>/dev/null || rm "$FILE"
echo "Key installed on the server (ID ${KEY_ID%"${KEY_ID#????????}"}...). The download was deleted from this Mac."
