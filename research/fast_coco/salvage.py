"""Rewrite a .jsonl.gz made of appended gzip members, keeping every intact JSON line (skips torn members)."""
import gzip, json, sys, zlib
src, dst = sys.argv[1], sys.argv[2]
raw = open(src, "rb").read()
starts = [i for i in range(len(raw) - 2) if raw[i] == 0x1f and raw[i + 1] == 0x8b and raw[i + 2] == 0x08]
seen, kept, bad = set(), 0, 0
with gzip.open(dst, "wt") as out:
    for k, s in enumerate(starts):
        d = zlib.decompressobj(31)
        try:
            text = d.decompress(raw[s:]).decode("utf-8", "ignore")
        except zlib.error:
            text = ""
            try:  # salvage what decompressed before the damage
                d2 = zlib.decompressobj(31); chunks = []
                for j in range(s, len(raw), 65536):
                    chunks.append(d2.decompress(raw[j:j + 65536]))
            except zlib.error:
                pass
            text = b"".join(chunks).decode("utf-8", "ignore") if 'chunks' in dir() else ""
            bad += 1
        for line in text.splitlines():
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            if m.get("ticker") and m["ticker"] not in seen:
                seen.add(m["ticker"]); out.write(json.dumps(m, separators=(",", ":")) + "\n"); kept += 1
print(f"{len(starts)} gzip headers, {bad} damaged, {kept} markets kept")
