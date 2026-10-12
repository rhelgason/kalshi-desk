import type { Advice } from "@/lib/advice";
import AdviceAction from "./AdviceAction";

const ICON = { act: "👉", watch: "👀", relax: "👍" } as const;

/** "What should I do about this employee?" in one sentence, with the button if there is one. */
export default function AdviceCard({ k, name, advice, admin }: { k: string; name: string; advice: Advice; admin: boolean }) {
  return (
    <section className={`card advice ${advice.tone}`}>
      <div className="label">What to do</div>
      <p className="advice-head"><span aria-hidden>{ICON[advice.tone]}</span> {advice.headline}</p>
      <p className="advice-why">{advice.why}</p>
      {advice.action && (admin
        ? <div className="row-btns"><AdviceAction k={k} name={name} advice={advice} /></div>
        : advice.tone === "act" && <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>The manager decides.</p>)}
    </section>
  );
}
