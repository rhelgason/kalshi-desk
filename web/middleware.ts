import { NextRequest, NextResponse } from "next/server";

// Logins last as long as browsers allow: every visit pushes a signed-in browser's session cookie out to
// 400 days again (lib/session.ts), so someone who opens the site now and then is never asked to sign in.
const SESSION_COOKIE = "desk_session";
const SESSION_SECONDS = 400 * 86_400;

function renew(req: NextRequest, res: NextResponse): NextResponse {
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (token && req.method === "GET") {
    res.cookies.set(SESSION_COOKIE, token, { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: SESSION_SECONDS });
  }
  return res;
}

// Optional password gate. Set DASHBOARD_PASSWORD in Vercel to enable it; any
// username works. Leave it unset for an open dashboard (e.g. local dev).
export function middleware(req: NextRequest) {
  const password = process.env.DASHBOARD_PASSWORD;
  if (!password) return renew(req, NextResponse.next());
  const header = req.headers.get("authorization") ?? "";
  const [scheme, encoded] = header.split(" ");
  if (scheme === "Basic" && encoded) {
    const decoded = atob(encoded);
    if (decoded.slice(decoded.indexOf(":") + 1) === password) return renew(req, NextResponse.next());
  }
  return new NextResponse("Password required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Kalshi Desk"' },
  });
}

// The home-screen widget (/api/widget, /widget/*) checks its own key instead; /api/warm only fills caches
export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|api/widget|api/warm|widget/).*)"] };
