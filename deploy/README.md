# Hosting Kalshi Desk for free

```
  free VM (Google Cloud e2-micro or Oracle)        Supabase (free Postgres)        Vercel (free)
  python -m desk paper  ── writes ledger + status ──▶  tables  ◀── reads ──  web/ dashboard
```

Why not GitHub Actions or Vercel for the bot itself? Vercel's free plan only
runs scheduled jobs once a day, and GitHub Actions gives private repos 2,000
minutes a month (a bot running nonstop needs ~43,000). A tiny always-on VM is
the free option that actually works.

## 1. Database (Supabase)

1. Create a project at supabase.com (free plan). Save the database password.
2. **Connect** → copy two connection strings:
   - **Session pooler** (port 5432): for the bot and your laptop
   - **Transaction pooler** (port 6543): for Vercel
3. On your Mac, put the session string in `.env` at the repo root:
   `DATABASE_URL=postgresql://postgres.xxxx:PASSWORD@aws-0-us-east-1.pooler.supabase.com:5432/postgres`
4. Copy your existing paper history and backtests up: `python -m desk migrate`

## 2. Bot (pick one VM)

**Google Cloud (simplest):** cloud.google.com/free → Compute Engine → Create
instance: machine type **e2-micro**, region **us-central1 / us-east1 /
us-west1** (only these are free), boot disk **Ubuntu 24.04 LTS, 30 GB
standard**. Then click **SSH**.

**Oracle Cloud (more power, signup can be fiddly):** oracle.com/cloud/free →
Compute → Create instance → Ubuntu 24.04, an "Always Free" shape. SSH in.

On the VM:

```bash
curl -fsSL -o setup.sh https://raw.githubusercontent.com/rhelgason/kalshi-desk/main/deploy/setup.sh  # private repo: copy the file over instead
bash setup.sh
```

The script prints a deploy key to add to GitHub (read-only), asks for the
session-pooler `DATABASE_URL`, and starts the `kalshi-desk` service.

- Logs: `journalctl -u kalshi-desk -f`
- Update to the latest code: `bash ~/kalshi-desk/deploy/update.sh`
- Stop: `sudo systemctl stop kalshi-desk`

Once the VM is running, stop the copy on your Mac (`pkill -f "desk paper"`) so
two bots don't write to the same database.

## 3. Dashboard (Vercel)

```bash
cd web
npx vercel link                       # create/link the project
npx vercel env add DATABASE_URL       # paste the TRANSACTION pooler string (port 6543)
npx vercel env add DASHBOARD_PASSWORD # optional: any password; username can be anything
npx vercel --prod
```

Or import the GitHub repo in the Vercel dashboard with **Root Directory = `web`**
and add the same two environment variables.

## Free-tier budgets to keep in mind

- Supabase free: 500 MB database, 5 GB egress/month. The bot caches history in
  memory and writes small rows, and the dashboard reads hourly-bucketed data.
- Google Cloud e2-micro: 1 GB RAM (the setup script adds swap), 1 GB/month free
  outbound traffic. The bot mostly downloads, which is free.
