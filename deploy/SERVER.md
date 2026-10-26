# The always-on server

A DigitalOcean droplet (New York, NYC3, $6/month: 1 GB, 1 CPU, Ubuntu 24.04) at **104.131.18.118**,
set up 2026-10-25. It runs one thing: `python -m desk fast` (desk/fast.py), Fast Coco and her 2-minute
twin on pretend money in the database's `fast` schema. Everything else stays on Vercel + Supabase.

- Log in: `ssh root@104.131.18.118` (the owner's Mac key). The bot runs as the `desk` user.
- Firewall: SSH only (ufw). Password logins off. fail2ban and automatic security updates on.
- Code: `/home/desk/kalshi-desk`, pulled from GitHub with a read-only deploy key.
- Secrets: `/etc/kalshi-desk.env` (DATABASE_URL only; no Kalshi key while Fast Coco is on pretend money).
- Service: `deploy/fast-coco.service` -> `/etc/systemd/system/fast-coco.service` (restarts on crash and boot).

```bash
ssh root@104.131.18.118 'systemctl status fast-coco --no-pager; journalctl -u fast-coco -n 50 --no-pager'
ssh root@104.131.18.118 'sudo -u desk git -C /home/desk/kalshi-desk pull -q && systemctl restart fast-coco'   # deploy
python -m desk fast-report     # from anywhere with DATABASE_URL: is the server worth it?
```

Health is in the `fast` schema's `status` row `fast:health` (updated every 30 seconds).

**Before Fast Coco trades real money:** the cron Coco must stop trading real money at the same moment (two bots
must never trade one account), and the twin keeps running as the "without the server" comparison. Fast Coco then
needs the Kalshi key on the server (the owner copies it over) and real cancels: a pull is only worth anything if
the cancel reaches Kalshi within a second. research/fast_coco/README.md has the backtest behind her design.
