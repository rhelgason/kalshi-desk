"""Download the official CF Benchmarks index (what Kalshi settles on), one value per whole second, through Kalshi's
REST passthrough. Resumable: one gzip line per hour, {"index", "hour", "v": {unix_second: value}}.
    python research/fast_coco/index_history.py OUTDIR DAYS INDEX...     env RATE (requests/s, default 2)
    python research/fast_coco/index_history.py --check INDEX TICKER     the official average vs. this download"""
import gzip, json, os, sys, time
from datetime import datetime, timedelta, timezone

import httpx

sys.path.insert(0, ".")
from desk.kalshi.auth import KalshiSigner  # noqa: E402

HOST, PATH = "https://api.elections.kalshi.com", "/trade-api/v2/cfbenchmarks/history/values"
signer = KalshiSigner.from_env()
http = httpx.Client(timeout=60)
GAP = 1 / float(os.environ.get("RATE", "2"))


def hour_values(index: str, hour: datetime) -> dict[int, float]:
    for i in range(30):
        r = http.get(HOST + PATH, params={"id": index, "timespan": "HOUR", "timestamp": hour.strftime("%Y-%m-%dT%H:%M:%S.000Z")},
                     headers=signer.headers("GET", PATH))
        if r.status_code == 200:
            return {p["time"] // 1000: float(p["value"]) for p in r.json()["data"]["payload"] if p["time"] % 1000 == 0}
        time.sleep(min(60, 2 ** i))
    raise RuntimeError(f"{index} {hour}: {r.status_code} {r.text[:200]}")


def download(out: str, days: float, indices: list[str]) -> None:
    os.makedirs(out, exist_ok=True)
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    start = end - timedelta(days=days)
    for index in indices:
        path = f"{out}/{index}.jsonl.gz"
        done = set()
        if os.path.exists(path):
            try:
                with gzip.open(path, "rt") as fh:
                    for line in fh:
                        done.add(json.loads(line)["hour"])
            except (EOFError, OSError, json.JSONDecodeError):
                pass
        with gzip.open(path, "at") as fh:
            h, n = start, 0
            while h <= end:
                key = int(h.timestamp())
                if key not in done:
                    t = time.time()
                    v = hour_values(index, h)
                    fh.write(json.dumps({"index": index, "hour": key, "v": v}, separators=(",", ":")) + "\n")
                    n += 1
                    if n % 50 == 0:
                        fh.flush(); print(index, h.isoformat(), n, "hours", flush=True)
                    time.sleep(max(0, GAP - (time.time() - t)))
                h += timedelta(hours=1)
        print(index, "done", flush=True)


def check(index: str, ticker: str) -> None:
    m = http.get(f"{HOST}/trade-api/v2/markets/{ticker}").json()["market"]
    close = int(datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp())
    v = {}
    for h in {close - 61, close - 1, close - 901 - 60, close - 901}:
        v.update(hour_values(index, datetime.fromtimestamp(h - h % 3600, timezone.utc)))
    avg = lambda end: sum(v[s] for s in range(end - 60, end)) / 60
    print(f"{ticker}: official settle {m.get('expiration_value')} / ours {avg(close):.4f};"
          f" official strike {m.get('floor_strike')} / ours {avg(close - 900):.4f}; result {m.get('result')}")


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        check(sys.argv[2], sys.argv[3])
    else:
        download(sys.argv[1], float(sys.argv[2]), sys.argv[3:])
