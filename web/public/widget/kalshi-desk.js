// Kalshi Desk home-screen widget: the design (Scriptable, https://scriptable.app).
//
// The script on the phone is a small loader (widget/loader.js in the repo) that
// fetches this file from the dashboard and runs it, so the design can change
// without pasting anything again. It runs with DASHBOARD and KEY passed in.
//
// Shows real money once a real-money book exists, the pretend pool until then.
// Black and green, terminal style: the office pool's total, a line of it over
// the last 7 days (the widget's Parameter sets the days), and a sentence about
// today. Tap to open the dashboard.

const DEFAULT_DAYS = 7;

const G = {
  bg: new Color("#000000"),
  bright: new Color("#3dff8a"),
  mid: new Color("#5fd38d"),
  dim: new Color("#2a7a4b"),
  faint: new Color("#0f2e1c"),
  loss: new Color("#ff4d5e"),
  alert: new Color("#ffb000"),
};
const HEX = { bright: "#3dff8a", loss: "#ff4d5e", dim: "#2a7a4b", faint: "#0f2e1c" };
// Money lost is red; everything else stays green
const tone = (v, gain = G.mid) => (v < 0 ? G.loss : gain);

const money = (v, sign = false) =>
  (sign ? (v >= 0 ? "+" : "−") : v < 0 ? "−" : "") +
  "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const short = (v) => "$" + Math.round(v).toLocaleString("en-US");
const fmt = (t, pattern) => {
  const f = new DateFormatter();
  f.dateFormat = pattern;
  return f.string(new Date(t));
};

function text(stack, s, size, color = G.mid, weight = "regular") {
  const t = stack.addText(s);
  t.font = weight === "bold" ? Font.boldMonospacedSystemFont(size)
    : weight === "medium" ? Font.mediumMonospacedSystemFont(size) : Font.regularMonospacedSystemFont(size);
  t.textColor = color;
  t.lineLimit = 1;
  t.minimumScaleFactor = 0.5;
  return t;
}

function chart(d, w, h, labels = true) {
  const ctx = new DrawContext();
  ctx.size = new Size(w, h);
  ctx.opaque = false;
  ctx.respectScreenScale = true;
  const pts = d.series.length > 1 ? d.series : [[Date.now() - 1, d.equity], [Date.now(), d.equity]];
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
  let lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
  if (hi - lo < 4) { const m = (hi + lo) / 2; lo = m - 2; hi = m + 2; } // small wiggles shouldn't look like cliffs
  const top = labels ? 12 : 3, bottom = 3, left = 2, right = 6;
  const ink = d.chart.change < 0 ? HEX.loss : HEX.bright;
  const x = (t) => left + ((t - t0) / (t1 - t0 || 1)) * (w - left - right);
  const y = (v) => top + (1 - (v - lo) / (hi - lo)) * (h - top - bottom);

  // Grid: three faint lines
  for (let i = 0; i <= 2; i++) {
    const gy = top + (i / 2) * (h - top - bottom);
    const g = new Path();
    g.move(new Point(left, gy));
    g.addLine(new Point(w - right, gy));
    ctx.addPath(g);
    ctx.setStrokeColor(new Color(HEX.faint));
    ctx.setLineWidth(1);
    ctx.strokePath();
  }

  const area = new Path();
  area.move(new Point(x(pts[0][0]), h - bottom));
  for (const [t, v] of pts) area.addLine(new Point(x(t), y(v)));
  area.addLine(new Point(x(t1), h - bottom));
  area.closeSubpath();
  ctx.addPath(area);
  ctx.setFillColor(new Color(ink, 0.12));
  ctx.fillPath();

  const line = new Path();
  line.move(new Point(x(pts[0][0]), y(pts[0][1])));
  for (const [t, v] of pts.slice(1)) line.addLine(new Point(x(t), y(v)));
  ctx.addPath(line);
  ctx.setStrokeColor(new Color(ink));
  ctx.setLineWidth(1.6);
  ctx.strokePath();

  // The latest value, glowing
  const ex = x(t1), ey = y(pts[pts.length - 1][1]);
  ctx.setFillColor(new Color(ink, 0.25));
  ctx.fillEllipse(new Rect(ex - 5, ey - 5, 10, 10));
  ctx.setFillColor(new Color(ink));
  ctx.fillEllipse(new Rect(ex - 2, ey - 2, 4, 4));

  if (labels) {
    ctx.setFont(Font.mediumMonospacedSystemFont(8));
    ctx.setTextColor(new Color(HEX.dim));
    const span = d.chart.full ? `${d.chart.days}D` : `SINCE ${fmt(d.chart.since, "MMM d").toUpperCase()}`;
    ctx.drawTextInRect(span, new Rect(left, 0, w / 2, 10));
    ctx.setTextAlignedRight();
    ctx.drawTextInRect(`H ${short(d.chart.high)}  L ${short(d.chart.low)}`, new Rect(w / 2, 0, w / 2 - right, 10));
  }
  return ctx.getImage();
}

function header(w, d, size) {
  const row = w.addStack();
  row.centerAlignContent();
  // Real money once it exists; until then the pretend pool, labelled so it's never mistaken for real
  const which = !d ? "" : d.book === "real" ? " · REAL" : " · PRETEND";
  text(row, `KALSHI DESK${which}`, size, d && d.book === "real" ? G.mid : G.dim, "bold");
  row.addSpacer();
  if (!d) return;
  if (d.stale) text(row, `● OFFLINE ${fmt(d.updated_at, "h:mm a")}`, size, G.alert, "bold");
  else text(row, `● ${fmt(d.updated_at, "h:mm a")}`, size, G.dim, "medium");
}

function build(d, family) {
  const w = new ListWidget();
  w.backgroundColor = G.bg;
  w.url = DASHBOARD;
  w.refreshAfterDate = new Date(Date.now() + 15 * 60_000);
  const small = family === "small", large = family === "large";
  w.setPadding(12, 14, 12, 14);
  header(w, d, small ? 9 : 10);

  if (!d || !d.ok) {
    w.addSpacer();
    text(w, d && d.error === "unauthorized" ? "> KEY NOT ACCEPTED" : "> CAN'T REACH THE DESK", 12, G.alert, "bold");
    text(w, "tap to open the dashboard", 10, G.dim);
    w.addSpacer();
    return w;
  }

  w.addSpacer(small ? 4 : 2);
  const pool = w.addStack();
  pool.bottomAlignContent();
  text(pool, money(d.equity), small ? 24 : large ? 38 : 32, G.bright, "bold");
  if (!small) {
    pool.addSpacer(8);
    const side = pool.addStack();
    side.layoutVertically();
    text(side, "SEASON", 8, G.dim, "medium");
    text(side, money(d.pnl, true), 11, tone(d.pnl), "medium");
  }

  w.addSpacer(small ? 6 : 6);
  const width = small ? 127 : 310;
  w.addImage(chart(d, width, small ? 40 : large ? 130 : 46, !small));
  w.addSpacer(small ? 6 : 6);

  if (small) {
    text(w, `TODAY ${money(d.today.dollars, true)}`, 10, tone(d.today.dollars), "medium");
    const sub = d.today.settled ? `${d.today.won}/${d.today.settled} WON` : "NO BETS SETTLED";
    text(w, d.stale ? "BOT OFFLINE" : sub, 9, d.stale ? G.alert : G.dim);
    return w;
  }

  const t = text(w, `> ${large ? d.today.text : d.today.brief || d.today.text}`, large ? 12 : 10,
    d.safety === "clear" ? tone(d.today.dollars) : G.alert);
  t.lineLimit = large ? 5 : 2;

  if (large) {
    w.addSpacer(8);
    const status = { halted: "REAL TRADING STOPPED", stopped: "STOPPED FOR TODAY", braked: "BETS HALVED" }[d.safety] || "ALL CLEAR";
    text(w, `STATUS   ${status}`, 10, d.safety === "clear" ? G.dim : G.alert, "medium");
    text(w, `IN PLAY  ${money(d.in_play)} on ${d.open_bets} bet${d.open_bets === 1 ? "" : "s"}`, 10, G.dim, "medium");
    text(w, `CHANGE   ${money(d.chart.change, true)} over the chart`, 10, d.chart.change < 0 ? G.loss : G.dim, "medium");
    w.addSpacer();
  }
  return w;
}

const param = parseFloat(args.widgetParameter);
const days = param > 0 ? param : DEFAULT_DAYS;
let data = null;
try {
  const req = new Request(`${DASHBOARD}/api/widget?key=${encodeURIComponent(KEY)}&days=${days}`);
  req.timeoutInterval = 20;
  data = await req.loadJSON();
} catch (e) {
  data = null;
}
const widget = build(data, config.widgetFamily || "medium");
if (config.runsInWidget) Script.setWidget(widget);
else await widget.presentMedium();
Script.complete();
