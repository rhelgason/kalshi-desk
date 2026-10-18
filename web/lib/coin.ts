/** Which coin a page shows: everything, or only bitcoin / only ether markets (the header switcher). */
export type Coin = "all" | "BTC" | "ETH";
export const COIN_COOKIE = "coin";
export const COINS: Coin[] = ["all", "BTC", "ETH"];
export const COIN_NAMES: Record<Coin, string> = { all: "All coins", BTC: "Bitcoin", ETH: "Ether" };
export const COIN_SHORT: Record<Coin, string> = { all: "All", BTC: "BTC", ETH: "ETH" };

export const parseCoin = (v?: string | null): Coin => (v === "BTC" || v === "ETH" ? v : "all");

/** KXBTC15M-26OCT...-15 -> BTC, KXETH15M-... -> ETH (anything else: its series name). */
export function coinOfTicker(ticker: string): string {
  const m = /^KX(BTC|ETH|SOL)/.exec(ticker);
  return m ? m[1] : ticker.split("-")[0];
}

export const onCoin = (ticker: string, coin: Coin) => coin === "all" || coinOfTicker(ticker) === coin;
