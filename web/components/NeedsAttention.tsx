import type { Advice } from "@/lib/advice";
import type { Employee } from "@/lib/types";
import AdviceAction from "./AdviceAction";
import Avatar from "./Avatar";
import Card from "./ui/Card";

/** What the manager should act on in their real-money office (11-16: on the cockpit for now). */
export default function NeedsAttention({ todo }: { todo: { e: Employee; advice: Advice }[] }) {
  return (
    <Card title="Needs Your Attention">
      {todo.length ? (
        <ul className="todo">
          {todo.map(({ e, advice }) => (
            <li key={e.key}>
              <Avatar k={e.key} emoji={e.emoji} size={36} />
              <div className="what">
                <strong>{advice.headline}</strong>
                <div className="muted">{advice.why}</div>
                <div className="row-btns" style={{ marginTop: 6 }}>
                  <AdviceAction k={e.key} name={e.name} advice={advice} />
                  <a href={`/employee/${e.key}`} className="small">See {e.name} →</a>
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="all-good">Nothing needs you.</p>
      )}
    </Card>
  );
}
