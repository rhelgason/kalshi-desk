export default function Setup({ error }: { error: string }) {
  return (
    <div className="card">
      <h2>Not connected yet</h2>
      <p className="notice">
        The dashboard reads from the bot&apos;s Postgres database. Set <code>DATABASE_URL</code> (Supabase
        transaction-pooler string) in the Vercel project settings, then redeploy.
      </p>
      <p className="muted" style={{ fontSize: 12 }}>{error}</p>
    </div>
  );
}
