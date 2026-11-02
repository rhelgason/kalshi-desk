/** KXBTC15M-26OCT...-15 -> BTC, KXDOGE15M-... -> DOGE (anything else: its series name). */
export function coinOfTicker(ticker: string): string {
  const m = /^KX([A-Z]+)15M/.exec(ticker);
  return m ? m[1] : ticker.split("-")[0];
}
