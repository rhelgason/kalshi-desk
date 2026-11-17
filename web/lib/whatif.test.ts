// The what-if replay against known answers (11-17). Run: node web/lib/whatif.test.ts
import { replayWhatIf } from "./whatif.ts";
let fails = 0;
const eq = (name: string, got: number, want: number, tol = 0.01) => {
  const ok = Math.abs(got - want) <= tol; if (!ok) fails++;
  console.log(ok ? "ok  " : "FAIL", name, "got", +got.toFixed(4), "want", want);
};
const last = (a: number[]) => a[a.length - 1];
const base = { moves: [] as { t: number; amount: number }[], putIn: 100, k: 1, ratio: 1, out: [] as string[] };
const bets: [number, string, number][] = [[1, "a", 10], [2, "b", -5], [3, "a", 20]];
// no change: the real pool
eq("no change = real", last(replayWhatIf({ ...base, bets, times: [3] })), 125);
// twice the money: twice everything
eq("2x money doubles", last(replayWhatIf({ ...base, k: 2, bets, times: [3] })), 250);
// twice the bet size: each result doubled, scaled by the what-if pool's size
// t1: 100 + 10*1*2 = 120 (real 110); t2: 120 - 5*(120/110)*2 = 109.0909 (real 105); t3: + 20*(109.09/105)*2 = 150.649
eq("2x bets compounds", last(replayWhatIf({ ...base, ratio: 2, bets, times: [3] })), 150.6494, 0.001);
// leave b out: a's bets resize with the bigger pool. t1 110 (real 110); t2 skip (real 105); t3 110 + 20*(110/105) = 130.952
eq("leave b out", last(replayWhatIf({ ...base, out: ["b"], bets, times: [3] })), 130.9524, 0.001);
eq("leave everyone out = flat", last(replayWhatIf({ ...base, out: ["a", "b"], bets, times: [3] })), 100);
// broke stays broke: a 40% loss at 3x is -120% -> $0, then a win must not bring it back
const ruin: [number, string, number][] = [[1, "a", -40], [2, "a", -10], [3, "a", 30]];
const r = replayWhatIf({ ...base, ratio: 3, bets: ruin, times: [1, 2, 3] });
eq("ruin hits 0", r[0], 0); eq("losses don't revive it", r[1], 0); eq("wins don't revive it", r[2], 0);
// new money revives a broke pool, scaled by k
eq("a deposit after ruin is real money", last(replayWhatIf({ ...base, ratio: 3, k: 1, bets: ruin, moves: [{ t: 2.5, amount: 50 }], putIn: 150, times: [2.6] })), 50);
console.log(fails ? `${fails} FAILED` : "all passed");
process.exit(fails ? 1 : 0);
