import type { ReactNode } from "react";

/**
 * Every card on the site (11-16): a Title Case header with an optional note or link on the right, then the body.
 * One place to change how cards and their headers look.
 */
export default function Card({ title, aside, className, children }: {
  title?: ReactNode; aside?: ReactNode; className?: string; children: ReactNode;
}) {
  return (
    <section className={`card ${className ?? ""}`}>
      {(title || aside) && (
        <div className="card-head">
          {title && <h2>{title}</h2>}
          {aside && <div className="card-aside">{aside}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
