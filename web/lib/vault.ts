import "server-only";
import { constants, createCipheriv, createPrivateKey, publicEncrypt, randomBytes, sign } from "node:crypto";

/**
 * Friends' Kalshi keys. The website checks a key works, then locks it to the server's public key
 * (SERVER_PUBLIC_KEY below): AES-256-GCM, with the AES key wrapped by RSA-OAEP-SHA256. Only the always-on server holds
 * the private half (desk/offices.py open_box), so the website and the database can store a key but never read
 * one back.
 */
// The server's public key (its private half: /etc/kalshi-desk-offices.pem, made there 2026-11-10, never copied off).
// Not a secret. A new server key: replace this, or set OFFICE_KEY_PUBLIC on the website.
const SERVER_PUBLIC_KEY = `-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAti4WsFcSIjP2ltGBt4Cy
HN1/oSt9IepbEAqbviwbI8g7DZnkcH/pRszrlv12wEgDBRxKbyLUkyjhVgXNrl2D
5Kz6niop0lNqeebto9ltCPJSarJGiY4R+QfANI5hNL6fR6qHYCL5wnR1QMcHVcWR
SA6CJN6VzPQl2FUmgIo9bHzXsqb9pFS2LGGdpJNQVGqLQkihF2h6EDiL9gFwnDV5
MTOdfy3eijuN5b43C60W6P1W5JWuySCtgghlLZlvm7IzNLbqc+hSAt60qFSGkwf2
SDi9Ft/nXEt4vNc3zzEeSs0kDcLUe5zFBLzdfc+M0ey/KfYq8A7UoFC13rNRRMGA
R8ZuqA+CAWaZOar5lsOT4obyQ5ocL6vYM4EvyUIZqm+2kQah00qda3A/RjK+ms0E
4/x/jC3SY8DDLZ8sq+cIgUfUtuu929s7NbEFiPQRH7JerlXDLIL76aPXVem1SoZy
LMPJBkwjtEzMji2BehvrRtMHeYWgMpARWwqZevfM/LrtAgMBAAE=
-----END PUBLIC KEY-----`;

export function lockKey(pem: string): string {
  const pub = process.env.OFFICE_KEY_PUBLIC || SERVER_PUBLIC_KEY;
  const aes = randomBytes(32), iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", aes, iv);
  const data = Buffer.concat([cipher.update(pem, "utf8"), cipher.final(), cipher.getAuthTag()]);
  const key = publicEncrypt({ key: pub.replace(/\\n/g, "\n"), padding: constants.RSA_PKCS1_OAEP_PADDING, oaepHash: "sha256" }, aes);
  return JSON.stringify({ v: 1, key: key.toString("base64"), iv: iv.toString("base64"), data: data.toString("base64") });
}

/**
 * Undo copy-paste damage (like desk/kalshi/auth.py _tidy_pem): quotes, literal \n, squashed or indented lines,
 * blank lines, text around the key, a key pasted without its BEGIN/END lines. The key's body is rebuilt from its
 * letters alone, 64 to a line. (11-15: the first friend's first paste was refused as "not a private key".)
 */
export function tidyPem(text: string): string {
  const t = text.replace(/\\n/g, "\n");
  const m = t.match(/-----BEGIN ([A-Z ]+)-----([\s\S]*?)-----END \1-----/);
  const body = (m ? m[2] : t.replace(/^\s*['"]|['"]\s*$/g, "")).replace(/[^A-Za-z0-9+/=]/g, "");
  const wrap = (label: string) =>
    [`-----BEGIN ${label}-----`, ...(body.match(/.{1,64}/g) ?? []), `-----END ${label}-----`].join("\n") + "\n";
  if (m) return wrap(m[1]);
  for (const label of ["RSA PRIVATE KEY", "PRIVATE KEY"]) {
    try {
      createPrivateKey(wrap(label));
      return wrap(label);
    } catch {}
  }
  return t.trim() + "\n";
}

const HOSTS = { prod: "https://external-api.kalshi.com", demo: "https://external-api.demo.kalshi.co" } as const;

/** Ask Kalshi for the account's balance with this key: proof it works. Returns dollars, or throws a plain reason. */
export async function kalshiBalance(keyId: string, pem: string, env: keyof typeof HOSTS = "prod"): Promise<number> {
  let key;
  try {
    key = createPrivateKey(pem);
  } catch {
    throw new Error("That doesn't look like a whole private key. Choose the file Kalshi downloaded when you made the key, or paste all of it, from -----BEGIN to -----END.");
  }
  const path = "/trade-api/v2/portfolio/balance";
  const ts = String(Date.now());
  const message = Buffer.from(ts + "GET" + path);
  // Kalshi takes RSA keys (signed RSA-PSS, SHA-256) and Ed25519 keys
  const signature = (key.asymmetricKeyType === "ed25519" ? sign(null, message, key)
    : sign("sha256", message, { key, padding: constants.RSA_PKCS1_PSS_PADDING, saltLength: constants.RSA_PSS_SALTLEN_DIGEST })
  ).toString("base64");
  const res = await fetch(HOSTS[env] + path, {
    headers: { "KALSHI-ACCESS-KEY": keyId.trim(), "KALSHI-ACCESS-TIMESTAMP": ts, "KALSHI-ACCESS-SIGNATURE": signature },
    cache: "no-store",
  });
  if (res.status === 401 || res.status === 403) {
    throw new Error("Kalshi didn't accept that key. Check the Key ID matches the file (they come in pairs).");
  }
  if (!res.ok) throw new Error(`Kalshi didn't answer (${res.status}). Try again in a minute.`);
  const d = await res.json();
  return d.balance_dollars != null ? Number(d.balance_dollars) : Number(d.balance ?? 0) / 100;
}
