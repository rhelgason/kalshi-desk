-- Friends' offices (2026-11-09): logins for the website and the offices the server runs (desk/offices.py).
-- Run once before the code that uses them goes out (psql, or psycopg with the whole file as one execute).
-- Row-level security on with no policies, like every other table: Supabase's public REST API can't read them;
-- the website and bot connect as the table owner, which RLS skips.
CREATE TABLE IF NOT EXISTS public.users (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'friend')),
    office TEXT UNIQUE,                       -- a friend's office: schema office_<office>
    prefs JSONB NOT NULL DEFAULT '{}',        -- the look, etc. (follows them to every device)
    share_overview BOOLEAN NOT NULL DEFAULT false,  -- agreed the owner may see their office (app/join)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.passkeys (
    id TEXT PRIMARY KEY,                      -- the credential id (base64url)
    user_id BIGINT NOT NULL REFERENCES public.users ON DELETE CASCADE,
    public_key TEXT NOT NULL,                 -- only the public half
    counter BIGINT NOT NULL DEFAULT 0,
    transports TEXT,
    device TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS public.sessions (
    token_hash TEXT PRIMARY KEY,              -- sha256 of the cookie (the cookie itself is never stored)
    user_id BIGINT NOT NULL REFERENCES public.users ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent TEXT
);
CREATE TABLE IF NOT EXISTS public.invites (
    token_hash TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    user_id BIGINT REFERENCES public.users ON DELETE CASCADE,  -- set once they start (or for a new-device link)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS public.offices (
    slug TEXT PRIMARY KEY,
    user_id BIGINT,
    name TEXT NOT NULL,
    env TEXT NOT NULL DEFAULT 'prod',
    key_id TEXT,
    key_box TEXT,                             -- the Kalshi key, locked to the server's key (web/lib/vault.ts)
    status TEXT NOT NULL DEFAULT 'setup',     -- setup -> ready (key in) -> active (season started) | closed
    note TEXT,                                -- the server's last problem with it, for /offices
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.passkeys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.offices ENABLE ROW LEVEL SECURITY;
-- Family bids (desk/offices.py family_bids): the resting orders of each book, looked up every run
CREATE INDEX IF NOT EXISTS orders_resting ON real.orders (status) WHERE status = 'resting';
