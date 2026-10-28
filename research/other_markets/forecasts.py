"""Archived weather-model forecasts of each Kalshi city's daily high (Open-Meteo's previous-runs API, free).
For day D: the max over D's local hours of the forecast made a day earlier (temperature_2m_previous_day1) and two days
earlier (previous_day2). Known before D's trading morning, so a backtest can use it without peeking.
    python research/other_markets/forecasts.py START END OUT.json"""
import json, sys
from collections import defaultdict
import httpx

CITIES = {"KXHIGHNY": (40.779, -73.9692, "America/New_York"), "KXHIGHLAX": (33.9382, -118.3866, "America/Los_Angeles"),
          "KXHIGHCHI": (41.7868, -87.7522, "America/Chicago"), "KXHIGHMIA": (25.7881, -80.3169, "America/New_York"),
          "KXHIGHAUS": (30.1831, -97.6799, "America/Chicago"), "KXHIGHDEN": (39.8466, -104.6562, "America/Denver")}
start, end, out = sys.argv[1:4]
res = {}
for s, (lat, lon, tz) in CITIES.items():
    d = httpx.get("https://previous-runs-api.open-meteo.com/v1/forecast", timeout=60, params={
        "latitude": lat, "longitude": lon, "timezone": tz, "temperature_unit": "fahrenheit", "start_date": start,
        "end_date": end, "hourly": "temperature_2m_previous_day1,temperature_2m_previous_day2"}).json()["hourly"]
    days = defaultdict(lambda: {"d1": -999, "d2": -999})
    for t, a, b in zip(d["time"], d["temperature_2m_previous_day1"], d["temperature_2m_previous_day2"]):
        x = days[t[:10]]
        if a is not None: x["d1"] = max(x["d1"], a)
        if b is not None: x["d2"] = max(x["d2"], b)
    res[s] = {k: v for k, v in days.items() if v["d1"] > -999}
    print(s, len(res[s]), "days", file=sys.stderr)
json.dump(res, open(out, "w"))
