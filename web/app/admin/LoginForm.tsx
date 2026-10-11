"use client";

import { useActionState } from "react";
import { loginAction } from "../actions";

export default function LoginForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState(loginAction, null);
  return (
    <form action={action} className="form">
      <input type="hidden" name="next" value={next} />
      <label>Password <input type="password" name="password" autoComplete="current-password" required /></label>
      {state?.error && <div className="down">{state.error}</div>}
      <button className="btn primary" disabled={pending}>{pending ? "Checking…" : "Log in"}</button>
    </form>
  );
}
