// Kalshi Desk home-screen widget for Scriptable (https://scriptable.app).
//
// Shows how much the office pool gained or lost over the last few hours, a
// line of its value over that time, the pool's total, today's change, and
// whether a guardrail is on. Tap it to open the dashboard.
//
// Setup: paste this into a new Scriptable script, add a Scriptable widget to
// the home screen, and pick this script. The widget's "Parameter" field sets
// the hours to look back (default 6), e.g. 1, 12 or 24.
// Data: GET /api/widget on the dashboard, with the WIDGET_TOKEN key.

const DASHBOARD = "https://kalshi-desk-nu.vercel.app";
const KEY = ""; // the widget key; left empty, the script asks once and keeps it in the Keychain
const DEFAULT_HOURS = 6;

const C = {
  bg: Color.dynamic(new Color("#f6f3ea"), new Color("#15152b")),
  ink: Color.dynamic(new Color("#1d1d2c"), new Color("#f2f0ff")),
  muted: Color.dynamic(new Color("#6b6b80"), new Color("#9a98c0")),
  up: Color.dynamic(new Color("#1a8a3a"), new Color("#41e07a")),
  down: Color.dynamic(new Color("#c92a2a"), new Color("#ff5c6c")),
  warn: Color.dynamic(new Color("#b35c00"), new Color("#ffb347")),
  grid: Color.dynamic(new Color("#d8d4c6"), new Color("#34345a")),
};
// The chart is drawn into an image, which doesn't follow light/dark mode by itself
const DARK = Device.isUsingDarkAppearance();
const LINE = {
  up: DARK ? "#41e07a" : "#1a8a3a",
  down: DARK ? "#ff5c6c" : "#c92a2a",
  grid: DARK ? "#34345a" : "#d8d4c6",
};

async function widgetKey() {
  if (KEY) return KEY;
  if (Keychain.contains("kalshi_desk_widget_key")) return Keychain.get("kalshi_desk_widget_key");
  if (config.runsInWidget) return null;
  const a = new Alert();
  a.title = "Kalshi Desk";
  a.message = "Paste your widget key";
  a.addTextField("key");
  a.addAction("Save");
  await a.present();
  const k = a.textFieldValue(0).trim();
  if (k) Keychain.set("kalshi_desk_widget_key", k);
  return k;
}

const money = (v, sign = false) =>
  (sign ? (v >= 0 ? "+" : "−") : v < 0 ? "−" : "") +
  "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (v) => (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(1) + "%";
const clock = (t) => {
  const f = new DateFormatter();
  f.dateFormat = "h:mm a";
  return f.string(new Date(t));
};

function chart(series, w, h, up) {
  const color = up ? LINE.up : LINE.down;
  const ctx = new DrawContext();
  ctx.size = new Size(w, h);
  ctx.opaque = false;
  ctx.respectScreenScale = true;
  const pts = series.length > 1 ? series : [[0, series[0]?.[1] ?? 0], [1, series[0]?.[1] ?? 0]];
  const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
  let lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1]));
  if (hi - lo < 2) { const mid = (hi + lo) / 2; lo = mid - 1; hi = mid + 1; } // a few cents shouldn't look like a cliff
  const pad = 3;
  const x = (t) => pad + ((t - t0) / (t1 - t0 || 1)) * (w - 2 * pad);
  const y = (v) => pad + (1 - (v - lo) / (hi - lo)) * (h - 2 * pad);

  // Where the window started, for reference
  const base = new Path();
  base.move(new Point(pad, y(pts[0][1])));
  base.addLine(new Point(w - pad, y(pts[0][1])));
  ctx.addPath(base);
  ctx.setStrokeColor(new Color(LINE.grid));
  ctx.setLineWidth(1);
  ctx.strokePath();

  const line = new Path();
  line.move(new Point(x(pts[0][0]), y(pts[0][1])));
  for (const [t, v] of pts.slice(1)) line.addLine(new Point(x(t), y(v)));
  const area = new Path();
  area.move(new Point(x(pts[0][0]), h));
  for (const [t, v] of pts) area.addLine(new Point(x(t), y(v)));
  area.addLine(new Point(x(pts[pts.length - 1][0]), h));
  area.closeSubpath();
  ctx.addPath(area);
  ctx.setFillColor(new Color(color, 0.18));
  ctx.fillPath();
  ctx.addPath(line);
  ctx.setStrokeColor(new Color(color));
  ctx.setLineWidth(2);
  ctx.strokePath();
  return ctx.getImage();
}

function text(stack, s, size, color = C.ink, bold = false, mono = false) {
  const t = stack.addText(s);
  t.font = mono ? (bold ? Font.boldMonospacedSystemFont(size) : Font.regularMonospacedSystemFont(size))
    : bold ? Font.boldSystemFont(size) : Font.systemFont(size);
  t.textColor = color;
  t.lineLimit = 1;
  t.minimumScaleFactor = 0.6;
  return t;
}

function header(w, d, hours) {
  const row = w.addStack();
  row.centerAlignContent();
  text(row, "💰 KALSHI DESK", 11, C.muted, true);
  row.addSpacer();
  if (d) text(row, clock(d.updated_at), 11, C.muted);
}

function statusLine(w, d, size) {
  if (d.stale) {
    text(w, `⚠️ Bot quiet since ${clock(d.updated_at)}`, size, C.warn, true);
    return;
  }
  const bits = [d.safety.text];
  if (d.open_bets) bits.push(`${d.open_bets} in play`);
  if (d.window.settled) bits.push(`${d.window.won}/${d.window.settled} won`);
  text(w, bits.join(" · "), size, d.safety.key === "clear" ? C.muted : C.warn);
}

function build(d, hours, family) {
  const w = new ListWidget();
  w.backgroundColor = C.bg;
  w.url = DASHBOARD;
  w.refreshAfterDate = new Date(Date.now() + 15 * 60_000);
  w.setPadding(12, 14, 12, 14);
  header(w, d, hours);
  if (!d || !d.ok) {
    w.addSpacer();
    text(w, d?.error === "unauthorized" ? "Widget key not accepted" : "Can't reach the desk", 14, C.warn, true);
    text(w, "Tap to open the dashboard", 11, C.muted);
    w.addSpacer();
    return w;
  }
  const change = d.window.change;
  const color = change >= 0 ? C.up : C.down;
  const label = `last ${hours < 1 ? Math.round(hours * 60) + "m" : hours + "h"}`;

  if (family === "small") {
    w.addSpacer(6);
    text(w, money(change, true), 26, color, true, true);
    text(w, label, 11, C.muted);
    w.addSpacer(6);
    w.addImage(chart(d.series, 130, 34, change >= 0));
    w.addSpacer(6);
    text(w, `Pool ${money(d.equity)}`, 12, C.ink, true);
    text(w, d.stale ? "⚠️ Bot quiet" : `Today ${pct(d.today)}`, 11, d.stale ? C.warn : C.muted);
    return w;
  }

  w.addSpacer(6);
  const row = w.addStack();
  row.centerAlignContent();
  const left = row.addStack();
  left.layoutVertically();
  text(left, money(change, true), 28, color, true, true);
  text(left, label, 11, C.muted);
  left.addSpacer(4);
  text(left, `Pool ${money(d.equity)}`, 13, C.ink, true);
  text(left, `Today ${pct(d.today)} · Season ${money(d.pnl, true)}`, 11, C.muted);
  row.addSpacer(10);
  const big = family === "large";
  row.addImage(chart(d.series, big ? 150 : 140, big ? 90 : 70, change >= 0));
  w.addSpacer(8);
  statusLine(w, d, 11);

  if (big) {
    w.addSpacer(10);
    const { best, worst } = d.window;
    if (best) text(w, `Best  ${best.name} ${money(best.pnl, true)}`, 12, C.ink);
    if (worst) text(w, `Worst ${worst.name} ${money(worst.pnl, true)}`, 12, C.ink);
    if (!best) text(w, "No bets settled in this window", 12, C.muted);
    w.addSpacer(4);
    text(w, `In play ${money(d.in_play)} · Season ${d.season}`, 11, C.muted);
    w.addSpacer();
  }
  return w;
}

async function main() {
  const param = parseFloat(args.widgetParameter);
  const hours = param > 0 ? param : DEFAULT_HOURS;
  const key = await widgetKey();
  let data = null;
  if (key) {
    try {
      const req = new Request(`${DASHBOARD}/api/widget?key=${encodeURIComponent(key)}&hours=${hours}`);
      req.timeoutInterval = 20;
      data = await req.loadJSON();
    } catch (e) {
      data = null;
    }
  }
  const family = config.widgetFamily || "medium";
  const w = build(data, hours, family);
  if (config.runsInWidget) {
    Script.setWidget(w);
  } else {
    await w.presentMedium(); // tapping Run in the app shows a preview
  }
  Script.complete();
}

await main();
