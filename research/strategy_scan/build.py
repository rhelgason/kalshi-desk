"""Build one row per (market, minute) with every feature a strategy might use. -> rows.pkl"""
import gzip, json, sqlite3, sys, math
from datetime import datetime
import numpy as np, pandas as pd

S = sys.argv[1]  # scratchpad
def iso(s): return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())

markets = {}
for d in json.load(gzip.open(f"{S}/hist.json.gz")):
    markets[d["m"]["ticker"]] = d
db = sqlite3.connect("data/research.db")
for (data,) in db.execute("select data from market_history"):
    d = json.loads(data); markets[d["m"]["ticker"]] = d
spot = {}
for (path,) in [("data/research_px.db",)]:
    for sym, day, data in sqlite3.connect(path).execute("select symbol, day, data from price_history where symbol not like 'DVOL%'"):
        spot.setdefault(sym, {}).update({int(k): v for k, v in json.loads(data).items()})
for sym, day, data in db.execute("select symbol, day, data from price_history where symbol not like 'DVOL%'"):
    spot.setdefault(sym, {}).update({int(k): v for k, v in json.loads(data).items()})
print(len(markets), "markets;", {k: len(v) for k, v in spot.items()}, "spot minutes")

COIN = {"KXBTC15M": "BTC", "KXETH15M": "ETH", "KXSOL15M": "SOL", "KXXRP15M": "XRP", "KXDOGE15M": "DOGE",
        "KXBNB15M": "BNB", "KXHYPE15M": "HYPE"}
recs = []
for tk, d in markets.items():
    m = d["m"]
    if m.get("result") not in ("yes", "no"): continue
    coin = COIN.get(tk.split("-")[0])
    if not coin: continue
    close, open_ = iso(m["close_time"]), iso(m["open_time"])
    if close - open_ != 900: continue
    y = 1 if m["result"] == "yes" else 0
    strike = m.get("floor_strike")
    for t, b, a, v in d["c"]:
        if b is None or a is None or not (open_ < t < close): continue
        recs.append((coin, tk, close, t, b, a, v or 0.0, y, strike if strike is not None else np.nan))
df = pd.DataFrame(recs, columns=["coin", "ticker", "close", "t", "bid", "ask", "vol", "y", "strike"])
df = df[(df.bid > 0) & (df.ask < 1) & (df.ask > df.bid)].sort_values(["ticker", "t"]).reset_index(drop=True)
df["left"] = (df.close - df.t) / 60.0
df["mid"] = (df.bid + df.ask) / 2
df["spread"] = df.ask - df.bid
g = df.groupby("ticker", sort=False)
for k in (1, 2, 3, 5):
    df[f"dmid{k}"] = df.mid - g.mid.shift(k)
df["vol_prev"] = g.vol.shift(1)
df["mid_open"] = g.mid.transform("first")

# Spot: price now, short returns, 60-min realized per-minute vol, model probability of finishing >= strike
for sym, closes in spot.items():
    ser = pd.Series(closes).sort_index()
    ser = ser[~ser.index.duplicated()]
    full = ser.reindex(range(int(ser.index.min()), int(ser.index.max()) + 60, 60)).ffill()
    lr = np.log(full).diff()
    sd = lr.rolling(60, min_periods=30).std()
    idx = df.coin == sym
    tt = df.loc[idx, "t"].values
    df.loc[idx, "spot"] = full.reindex(tt).values
    for k in (1, 3, 5):
        df.loc[idx, f"sret{k}"] = (full.reindex(tt).values / full.reindex(tt - 60 * k).values) - 1
    df.loc[idx, "sd1"] = sd.reindex(tt).values
from math import erf
def ncdf(x): return 0.5 * (1 + np.vectorize(erf)(x / math.sqrt(2)))
ok = df.spot.notna() & df.strike.notna() & (df.sd1 > 0)
z = np.log(df.loc[ok, "spot"] / df.loc[ok, "strike"]) / (df.loc[ok, "sd1"] * np.sqrt(df.loc[ok, "left"]))
df.loc[ok, "z"] = z
df.loc[ok, "model"] = ncdf(z.values)

# Cross-coin: bitcoin's market in the same window, same minute
btc = df[df.coin == "BTC"][["close", "t", "mid", "dmid1", "dmid2", "dmid3"]].rename(
    columns={"mid": "btc_mid", "dmid1": "btc_d1", "dmid2": "btc_d2", "dmid3": "btc_d3"})
df = df.merge(btc, on=["close", "t"], how="left")
df["hour"] = pd.to_datetime(df.t, unit="s", utc=True).dt.tz_convert("America/Vancouver").dt.hour
df["day"] = pd.to_datetime(df.close, unit="s", utc=True).dt.tz_convert("America/Vancouver").dt.strftime("%Y-%m-%d")
df.to_pickle(f"{S}/rows.pkl")
print(df.groupby("coin").agg(markets=("ticker", "nunique"), first=("day", "min"), last=("day", "max"),
                             spot=("spot", lambda s: s.notna().mean())))
