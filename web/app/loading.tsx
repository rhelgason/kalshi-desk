/**
 * Shown the moment a page is asked for, while the server gathers its numbers (11-16): the shape of the page to come,
 * gently shimmering, so a click lands somewhere straight away (Training's season is big and takes a few seconds).
 */
export default function Loading() {
  return (
    <div className="stack" aria-busy="true" aria-label="Loading">
      <section className="card">
        <div className="skel skel-title" />
        <div className="skel skel-big" />
        <div className="skel skel-row" />
        <div className="skel skel-chart" />
      </section>
      <section className="card">
        <div className="skel skel-title" />
        <div className="skel skel-line" />
        <div className="skel skel-line" />
        <div className="skel skel-line short" />
      </section>
    </div>
  );
}
