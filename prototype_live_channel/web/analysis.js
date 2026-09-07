/* One page for the whole session. Figures arrive as JSON over the channel and
 * are diffed in with Plotly.react; selections and drill-downs travel back.
 *
 * The page deliberately does not try to work out which device a point belongs
 * to. Only the Python side knows the device list and the stack id, and source
 * file names like `<stack_id>_<device>_<NN>_<type>` cannot be split reliably
 * here -- a stack id may contain underscores itself. So we send what we saw and
 * let the other side resolve it. */

const CONFIG = { responsive: true, displaylogo: false, scrollZoom: true };
const plotDiv = document.getElementById("plot");
const placeholder = document.getElementById("placeholder");

let bridge = null;
let drawn = false;
let currentKey = null;

function show(payload) {
  if (!payload || !payload.figure) {
    drawn = false;
    currentKey = null;
    Plotly.purge(plotDiv);
    placeholder.textContent = (payload && payload.message) || "No plot.";
    placeholder.style.display = "flex";
    return;
  }
  placeholder.style.display = "none";
  const fig = payload.figure;

  // A different plot must not inherit the previous one's zoom, so start fresh
  // when the key changes; the same plot re-pushed keeps its view via react.
  if (!drawn || payload.key !== currentKey) {
    currentKey = payload.key;
    drawn = true;
    Plotly.newPlot(plotDiv, fig.data, fig.layout, CONFIG).then(attach);
  } else {
    Plotly.react(plotDiv, fig.data, fig.layout, CONFIG);
  }
}

function send(request) {
  if (!bridge) return;
  bridge.event(JSON.stringify(request), (answer) => show(JSON.parse(answer)));
}

/* What Python needs to identify a point: the trace name, and for heatmap cells
 * the row/column the click landed on. */
function pointRef(point) {
  if (!point) return null;
  return {
    name: (point.data && point.data.name) || null,
    x: point.x !== undefined ? point.x : null,
    y: point.y !== undefined ? point.y : null,
  };
}

function pointRefs(ev) {
  const seen = new Set();
  const refs = [];
  for (const p of (ev && ev.points) || []) {
    const ref = pointRef(p);
    if (!ref) continue;
    const id = `${ref.name}|${ref.x}|${ref.y}`;
    if (seen.has(id)) continue;      // a lasso can cover thousands of points
    seen.add(id);
    refs.push(ref);
  }
  return refs;
}

/* Endurance plots put the cycle number on the x-axis, so a click there names
 * the exact cycle. A CDF sorts its values and a boxplot groups them, so the
 * point index there says nothing about which cycle it came from. Rather than
 * guess, those drill down to the device and show all of its cycles. */
function cycleOf(point) {
  if (!currentKey || !currentKey.startsWith("endurance")) return null;
  const x = point && point.x;
  return typeof x === "number" && isFinite(x) ? Math.round(x) : null;
}

function attach() {
  plotDiv.on("plotly_selected", (ev) => {
    if (!ev) return;
    const points = pointRefs(ev);
    if (points.length) send({ kind: "select_devices", points });
  });
  plotDiv.on("plotly_deselect", () => send({ kind: "clear_selection" }));

  // Plain click highlights the device; ctrl/cmd-click drills to the raw sweep.
  plotDiv.on("plotly_click", (ev) => {
    const point = ev && ev.points && ev.points[0];
    const ref = pointRef(point);
    if (!ref) return;
    if (ev.event && (ev.event.ctrlKey || ev.event.metaKey)) {
      send({ kind: "drill", point: ref, cycle: cycleOf(point) });
    } else {
      send({ kind: "toggle_device", point: ref });
    }
  });
}

new QWebChannel(qt.webChannelTransport, (channel) => {
  bridge = channel.objects.bridge;
  bridge.figureChanged.connect((json) => show(JSON.parse(json)));
  bridge.bootstrap((answer) => show(JSON.parse(answer)));
});
