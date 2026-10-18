"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { pickCoin } from "@/app/actions";
import { COIN_NAMES, COIN_SHORT, COINS, type Coin } from "@/lib/coin";

/** All / BTC / ETH in the header: every page's numbers follow it. */
export default function CoinSwitch({ value }: { value: Coin }) {
  const router = useRouter();
  const [picked, setPicked] = useState(value);
  const [pending, start] = useTransition();
  useEffect(() => setPicked(value), [value]);
  return (
    <div className="seg seg-mini coin-switch" role="tablist" aria-label="Coin" data-pending={pending || undefined}>
      {COINS.map((c) => (
        <button key={c} role="tab" title={COIN_NAMES[c]} aria-selected={c === picked} aria-current={c === picked ? "true" : undefined}
          onClick={() => {
            if (c === picked) return;
            setPicked(c);
            start(async () => {
              await pickCoin(c);
              router.refresh();
            });
          }}>
          {COIN_SHORT[c]}
        </button>
      ))}
    </div>
  );
}
