/* The page stays alive for the whole session. It never reloads: figures are
 * diffed in with Plotly.react, and selections are sent back to Python. */

const PLOTS = ["map", "scatter", "cdf", "endurance"];
const CONFIG = { responsive: true, displaylogo: false, scrollZoom: true };

let bridge = null;
const drawn = new Set();

/* ---------- rendering ---------- */

function applyPayload(payload) {
  for (const name of PLOTS) {
    // Skip the plot the user is interacting with, so we never yank their
    // selection box out from under them.
    if (name === payload.source) continue;
    draw(name, payload.figures[name]);
  }
}

function draw(name, fig) {
  const div = document.getElementById(name);
  if (!drawn.has(name)) {
    drawn.add(name);
    Plotly.newPlot(div, fig.data, fig.layout, CONFIG).then(() => attach(name, div));
  } else {
    // The whole point: a diff update. Zoom, pan and hover state survive it
    // because the layouts carry a stable uirevision.
    Plotly.react(div, fig.data, fig.layout, CONFIG);
  }
}

/* ---------- talking back to Python ---------- */

function send(request) {
  if (!bridge) return;
  bridge.select(JSON.stringify(request), (answer) => applyPayload(JSON.parse(answer)));
}

function devicesIn(eventData) {
  const seen = new Set();
  for (const p of eventData.points || []) {
    if (p.customdata) seen.add(p.customdata);
  }
  return [...seen];
}

function attach(name, div) {
  if (name === "map" || name === "scatter") {
    div.on("plotly_selected", (ev) => {
      if (!ev) return;                       // click on empty space
      send({ kind: "devices", source: name, devices: devicesIn(ev) });
    });
    div.on("plotly_deselect", () => send({ kind: "reset", source: name }));
  }

  if (name === "map") {
    div.on("plotly_click", (ev) => {
      const device = ev.points[0] && ev.points[0].customdata;
      if (device) send({ kind: "toggle", source: name, device });
    });
  }

  if (name === "endurance") {
    // The range slider is a filter: dragging it re-queries DuckDB.
    let timer = null;
    div.on("plotly_relayout", (ev) => {
      const lo = ev["xaxis.range[0]"] ?? (ev["xaxis.range"] || [])[0];
      const hi = ev["xaxis.range[1]"] ?? (ev["xaxis.range"] || [])[1];
      if (lo === undefined || hi === undefined) return;
      clearTimeout(timer);
      timer = setTimeout(
        () => send({ kind: "cycles", source: name, cycles: [Math.round(lo), Math.round(hi)] }),
        120
      );
    });
  }
}

/* ---------- startup ---------- */

new QWebChannel(qt.webChannelTransport, (channel) => {
  bridge = channel.objects.bridge;

  // Python can push on its own -- that is how the Qt toolbar updates the plots.
  bridge.figuresChanged.connect((json) => applyPayload(JSON.parse(json)));

  bridge.bootstrap((answer) => {
    document.getElementById("boot").style.display = "none";
    document.getElementById("grid").style.visibility = "visible";
    applyPayload(JSON.parse(answer));
  });
});
