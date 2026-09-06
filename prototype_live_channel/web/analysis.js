/* One page for the whole session. Figures arrive as JSON over the channel and
 * are diffed in with Plotly.react; selections travel back the same way. */

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

function devicesIn(ev) {
  const seen = new Set();
  for (const p of (ev && ev.points) || []) {
    const d = p.customdata;
    if (typeof d === "string" && /^[A-Za-z]+\d+$/.test(d)) seen.add(d);
    else if (p.y !== undefined && p.x !== undefined && /^[A-Za-z]+$/.test(String(p.y)))
      seen.add(String(p.y) + String(p.x));   // heatmap cell -> device id
  }
  return [...seen];
}

function attach() {
  plotDiv.on("plotly_selected", (ev) => {
    if (!ev) return;
    const devices = devicesIn(ev);
    if (devices.length) send({ kind: "select_devices", devices });
  });
  plotDiv.on("plotly_click", (ev) => {
    const devices = devicesIn(ev);
    if (devices.length === 1) send({ kind: "toggle_device", device: devices[0] });
  });
  plotDiv.on("plotly_deselect", () => send({ kind: "clear_selection" }));
}

new QWebChannel(qt.webChannelTransport, (channel) => {
  bridge = channel.objects.bridge;
  bridge.figureChanged.connect((json) => show(JSON.parse(json)));
  bridge.bootstrap((answer) => show(JSON.parse(answer)));
});
