const CITIES: Record<string, string> = { MIA: "Miami", NY: "New York", CHI: "Chicago", AUS: "Austin", DEN: "Denver",
  PHIL: "Philadelphia", LAX: "Los Angeles" };

/** A market in a few words (11-16): "BTC" for the 15-minute coins, "Miami high" for weather, "BTC hourly", else the series. */
export function marketLabel(ticker: string): string {
  const series = ticker.split("-")[0];
  if (/^KX[A-Z]+15M$/.test(series)) return coinOfTicker(ticker);
  const city = /^KXHIGH([A-Z]+)$/.exec(series)?.[1];
  if (city) return `${CITIES[city] ?? city} high`;
  if (series === "KXBTCD") return "BTC hourly";
  return series.replace(/^KX/, "");
}

/** KXBTC15M-26OCT...-15 -> BTC, KXDOGE15M-... -> DOGE (anything else: its series name). */
export function coinOfTicker(ticker: string): string {
  const m = /^KX([A-Z]+)15M/.exec(ticker);
  return m ? m[1] : ticker.split("-")[0];
}
