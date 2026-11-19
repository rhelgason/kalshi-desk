# The always-on server

A DigitalOcean droplet (New York, NYC3, $6/month: 1 GB, 1 CPU, Ubuntu 24.04) at **104.131.18.118**,
set up 2026-10-25. It runs one thing: `python -m desk fast` (desk/fast.py), Fast Sadie and her 2-minute
twin on pretend money in the database's `fast` schema. Everything else stays on Vercel + Supabase.

- Log in: `ssh root@104.131.18.118` (the owner's Mac key). The bot runs as the `desk` user.
- Firewall: SSH only (ufw). Password logins off. fail2ban and automatic security updates on.
- Code: `/home/desk/kalshi-desk`, pulled from GitHub with a read-only deploy key.
- Secrets: `/etc/kalshi-desk.env` (DATABASE_URL, KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH=/etc/kalshi-desk.key).
  The key ("Server" on Kalshi) was installed with deploy/add-kalshi-key.sh; it can trade but is only used to read
  (signed reads get the key's own rate limit). Delete it on kalshi.com -> Settings -> API Keys to revoke.
- Research downloads run here too (research/fast_coco/tape.py, index_history.py) into /home/desk/research; stop one
  with `kill $(cat /home/desk/research/tape15/pid)`, never `pkill -f` (it matches your own ssh command).
- **Polymarket US recorder** (11-19, research only: no account, no key, no trading, no database): `deploy/pm-recorder.service`
  runs research/polymarket/recorder.py, saving best bid/ask, last trade, contracts traded (every 2 s) and the top of the
  book (every 10 s) of Polymarket US's 15-minute up/down windows to `/home/desk/pm_tape/YYYY-MM-DD.jsonl[.gz]` (~20 MB a
  day). Its public data has no trade history, so this is the tape a future replay would need. Gold/silver/oil/gas books
  answer 404 publicly (11-19); only BTC/ETH/SOL/XRP record. Check: `du -sh /home/desk/pm_tape; journalctl -u pm-recorder -n 20`.
- Service: `deploy/fast-coco.service` -> `/etc/systemd/system/fast-coco.service` (restarts on crash and boot).

```bash
ssh root@104.131.18.118 'systemctl status fast-coco --no-pager; journalctl -u fast-coco -n 50 --no-pager'
ssh root@104.131.18.118 'sudo -u desk git -C /home/desk/kalshi-desk pull -q && systemctl restart fast-coco'   # deploy
# A real-money command that reads Kalshi (e.g. new-season on the real book), run with the server's key:
ssh root@104.131.18.118 'cd /home/desk/kalshi-desk && sudo -u desk bash -c "set -a; . /etc/kalshi-desk.env; set +a; KALSHI_LIVE_TRADING=yes .venv/bin/python -m desk new-season --config desk.real.yaml --why ..."'
python -m desk fast-report     # from anywhere with DATABASE_URL: is the server worth it?
```

Health is in the `fast` schema's `status` row `fast:health` (updated every 30 seconds).

**Before Fast Sadie trades real money:** the cron bot must stop trading real money at the same moment (two bots
must never trade one account), and the twin keeps running as the "without the server" comparison. Fast Sadie then
needs real orders and cancels: a pull is only worth anything if
the cancel reaches Kalshi within a second. research/fast_coco/README.md has the backtest behind her design.

## The owner's books (2026-11-16)

Vercel Hobby's Fluid allowance ran out on 11-16 (the bot was 93% of it) and Vercel disabled both projects, so the
owner's books moved here: `python -m desk tick` (one run of the real book, then Training, exactly what /api/tick did)
from a systemd timer every 2 minutes at :05 past even minutes (`deploy/tick.service` + `deploy/tick.timer` ->
`/etc/systemd/system/kalshi-tick.{service,timer}`). It trades with the server's own Kalshi key ("Server") and has no
CPU budget (`DESK_CPU_BUDGET_HOURS=0`). The pg_cron job `kalshi-desk-tick` that called Vercel is switched off
(`cron.alter_job(1, active := false)`): never turn it back on while this timer runs, or two bots trade one account.
Vercel now only hosts the website.

```bash
ssh root@104.131.18.118 'systemctl list-timers kalshi-tick.timer --no-pager; journalctl -u kalshi-tick -n 40 --no-pager'
ssh root@104.131.18.118 'systemctl stop kalshi-tick.timer'    # stop the owner's bot (bets already on settle on Kalshi)
```

## Friends' offices (2026-11-09)

`python -m desk offices` (desk/offices.py, `deploy/offices.service` -> `/etc/systemd/system/kalshi-offices.service`) runs
each friend's office every 2 minutes, 30 seconds after the owner's run, all in one process with each office kept in
memory (the database is only written to). A friend joins from an invite link made on the website's /offices page;
their Kalshi key arrives locked to `/etc/kalshi-desk-offices.pem` (made on this server 2026-11-10, root:desk 640;
its public half is in web/lib/vault.ts). Never copy that file off the server; if it's lost, friends reconnect Kalshi.

```bash
ssh root@104.131.18.118 'systemctl status kalshi-offices --no-pager; journalctl -u kalshi-offices -n 50 --no-pager'
ssh root@104.131.18.118 'sudo -u desk git -C /home/desk/kalshi-desk pull -q && systemctl restart kalshi-offices fast-coco'   # deploy
```

The office loop never touches the owner's books: it reads the real book's playbook and resting bids, and writes only
office_<name> schemas and public.offices. Stopping the service stops every office (bets already on settle on Kalshi).
