// Kalshi Desk home-screen widget for Scriptable (https://scriptable.app): the loader.
//
// This is the only part that lives on the phone. It fetches the widget's
// design from the dashboard (web/public/widget/kalshi-desk.js) and runs it,
// keeping the last copy for when the network is down, so design changes
// never need pasting again. KEY is the dashboard's WIDGET_TOKEN.
//
// Setup: paste into a new Scriptable script, add a Scriptable widget to the
// home screen (long-press > Edit > Add Widget), and pick this script. The
// widget's Parameter sets how many days the chart covers (default 7).

const DASHBOARD = "https://kalshi-desk-nu.vercel.app";
const KEY = "";

const fm = FileManager.local();
const cache = fm.joinPath(fm.documentsDirectory(), "kalshi-desk-widget.js");
let code = null;
try {
  const req = new Request(`${DASHBOARD}/widget/kalshi-desk.js?v=${Date.now()}`);
  req.timeoutInterval = 15;
  const body = await req.loadString();
  if (req.response.statusCode === 200 && body.includes("ListWidget")) {
    code = body;
    fm.writeString(cache, code);
  }
} catch (e) {}
if (!code && fm.fileExists(cache)) code = fm.readString(cache);

if (code) {
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction("DASHBOARD", "KEY", code)(DASHBOARD, KEY);
} else {
  const w = new ListWidget();
  w.backgroundColor = new Color("#000000");
  const t = w.addText("KALSHI DESK\n> CAN'T REACH THE DESK");
  t.font = Font.boldMonospacedSystemFont(12);
  t.textColor = new Color("#ffb000");
  w.url = DASHBOARD;
  Script.setWidget(w);
  Script.complete();
}
