/**
 * Live checks on what someone pastes while connecting Kalshi (11-17): both early friends were unsure what goes in
 * which box and whether the "-----BEGIN…-----" lines belong. The server's tidyPem (lib/vault.ts) accepts the key with
 * or without those lines; these only say, as they type, whether it looks right and what's wrong if not.
 */
export type Check = { ok: boolean; text: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function checkKeyId(value: string): Check | null {
  const t = value.trim();
  if (!t) return null;
  if (/BEGIN|PRIVATE|^MII/.test(t) || t.length > 80) return { ok: false, text: "That's the private key. It goes in the second box." };
  if (UUID.test(t) || /^[0-9a-f-]{20,64}$/i.test(t)) return { ok: true, text: "Looks like a Key ID" };
  return { ok: false, text: "A Key ID is numbers, letters a–f and dashes, like 1a2b3c4d-5e6f-…. Copy it from Kalshi's API keys list." };
}

export function checkPem(value: string): Check | null {
  const t = value.replace(/\\n/g, "\n").trim();
  if (!t) return null;
  if (UUID.test(t)) return { ok: false, text: "That's the Key ID. It goes in the first box." };
  if (/PUBLIC KEY/.test(t)) return { ok: false, text: "That's a public key. We need the private key Kalshi gave you when you made the key." };
  const begin = /-----BEGIN [A-Z ]+-----/.test(t), end = /-----END [A-Z ]+-----/.test(t);
  const body = t.replace(/-----(BEGIN|END) [A-Z ]+-----/g, "").replace(/[^A-Za-z0-9+/=]/g, "");
  if (begin && !end) return { ok: false, text: "It's cut off: the last line, -----END … KEY-----, is missing. Copy all of it." };
  if (!begin && end) return { ok: false, text: "The start is missing: copy from the very first line." };
  if (body.length < 800) return { ok: false, text: "Too short to be a whole private key (they're about 25 lines). Copy all of it." };
  return { ok: true, text: begin ? "Looks like a whole private key" : "Looks like a private key (no ----- lines: that's fine, we add them)" };
}
