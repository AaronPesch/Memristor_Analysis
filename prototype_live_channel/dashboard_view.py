"""Render the overview tab as an HTML fragment.

Kept apart from the data collection so the checks stay testable without a
browser. The fragment is pushed over the same channel as the figures; it just
carries `kind: "html"` instead of a Plotly payload.
"""

from __future__ import annotations

import html
from datetime import datetime

from dashboard_data import Overview, Stat

SEVERITY_STYLE = {
    "error": ("#c8493f", "Problem"),
    "warning": ("#d08b2c", "Warnung"),
    "info": ("#4c8dff", "Hinweis"),
}


def _fmt(value: float) -> str:
    if value != value:  # NaN
        return "–"
    if value == 0:
        return "0"
    if 1e-3 <= abs(value) < 1e5:
        return f"{value:,.4g}"
    return f"{value:.3e}"


def _tile(label: str, value: str, hint: str = "") -> str:
    hint_html = f'<div class="hint">{html.escape(hint)}</div>' if hint else ""
    return (
        f'<div class="tile"><div class="tile-value">{html.escape(value)}</div>'
        f'<div class="tile-label">{html.escape(label)}</div>{hint_html}</div>'
    )


def _stat_row(stat: Stat) -> str:
    cv = (
        f"{stat.cv:.1%}"
        if stat.cv_is_meaningful
        else f'<span class="muted" title="Dominated by outliers on a '
        f'decade-spanning parameter – read p10–p90 instead">{stat.cv:.0%}</span>'
    )
    return (
        f'<tr data-param="{html.escape(stat.label)}">'
        f'<td class="name">{html.escape(stat.label)}</td>'
        f'<td class="unit">{html.escape(stat.unit)}</td>'
        f"<td>{stat.n:,}</td>"
        f"<td>{_fmt(stat.median)}</td>"
        f"<td>{_fmt(stat.mean)}</td>"
        f"<td>{_fmt(stat.std)}</td>"
        f"<td>{cv}</td>"
        f"<td>{_fmt(stat.p10)}</td>"
        f"<td>{_fmt(stat.p90)}</td>"
        f"<td>{_fmt(stat.minimum)}</td>"
        f"<td>{_fmt(stat.maximum)}</td>"
        "</tr>"
    )


def _finding_card(finding) -> str:
    color, word = SEVERITY_STYLE[finding.severity]
    chips = ""
    if finding.devices:
        shown = finding.devices[:14]
        rest = len(finding.devices) - len(shown)
        chips = "".join(
            f'<button class="chip" data-device="{html.escape(d)}" '
            f'title="Rohkurven von {html.escape(d)} ansehen">{html.escape(d)}</button>'
            for d in shown
        )
        if rest:
            chips += f'<span class="muted">+{rest} weitere</span>'
        chips = f'<div class="chips">{chips}</div>'
    return (
        f'<div class="finding" style="border-left-color:{color}">'
        f'<div class="finding-head"><span class="badge" style="background:{color}">'
        f"{word}</span> {html.escape(finding.title)}</div>"
        f'<div class="finding-detail">{html.escape(finding.detail)}</div>{chips}</div>'
    )


def _stack_block(stack, muted: str) -> str:
    """Stack-map thumbnail plus the yield headline, both as jump-off points."""
    if stack is None:
        return ""

    header = "".join(f"<th>{c}</th>" for c in stack.cols)
    body = ""
    for row in stack.rows:
        body += f'<tr><th class="rowlab">{html.escape(row)}</th>'
        for col in stack.cols:
            cell = stack.cell_at(row, col)
            if cell is None:
                body += '<td class="empty"></td>'
                continue
            verdict = "pass" if cell.passed else "fail"
            body += (
                f'<td><button class="cell {verdict}" data-device="{html.escape(cell.device)}"'
                f' style="background:{cell.color}"'
                f' title="{html.escape(cell.device)} · {html.escape(stack.label)} '
                f'{cell.value:.4g} · {verdict.upper()} — Rohkurve öffnen">'
                f"{html.escape(cell.device)}</button></td>"
            )
        body += "</tr>"

    return f"""
  <h2>Stack auf einen Blick</h2>
  <div class="stack-row">
    <div class="map-card">
      <div class="card-head">
        <span>{html.escape(stack.label)} je Position</span>
        <button class="link" data-goto="spatial_maps_stack_level">Stack Map öffnen →</button>
      </div>
      <table class="minimap">
        <thead><tr><th></th>{header}</tr></thead>
        <tbody>{body}</tbody>
      </table>
      <div class="legend">dunkel = niedrig, hell = hoch · roter Rahmen = fail</div>
    </div>
    <div class="yield-card">
      <div class="card-head">
        <span>Yield</span>
        <button class="link" data-goto="yield_map_stack_level">Yield Map öffnen →</button>
      </div>
      <div class="yield-value">{stack.percent:.1f}&thinsp;%</div>
      <div class="yield-sub">{stack.passed} von {stack.tested} Devices</div>
      <div class="yield-rule">{html.escape(stack.label)} {html.escape(stack.operator)}
        {stack.threshold:.4g}</div>
      <div class="hint" style="color:{muted}">Schwelle = Median über alle Devices;
        in der Yield Map frei einstellbar</div>
    </div>
  </div>"""


def render(overview: Overview, dark: bool) -> str:
    bg = "#1e1e1e" if dark else "#ffffff"
    panel = "#262626" if dark else "#f6f7f9"
    text = "#e0e0e0" if dark else "#2a3f5f"
    muted = "#8b8b8b"
    border = "#3a3a3a" if dark else "#dde0e6"

    types = " · ".join(
        f"{html.escape(k)} ({v:,})"
        for k, v in sorted(overview.measurement_types.items())
    )
    tiles = (
        _tile("Devices", str(len(overview.devices)))
        + _tile("Endurance-Sets", str(overview.n_sets), f"{overview.n_resets} Resets")
        + _tile("Zyklen", f"{overview.cycles_total:,}")
        + _tile("Zeilen in der DB", f"{overview.db_rows:,}")
        + _tile("v_read", f"{overview.v_read:.3g} V", "Basis für R_LRS / R_HRS")
    )

    if overview.findings:
        cards = "".join(_finding_card(f) for f in overview.findings)
        quality = f'<div class="findings">{cards}</div>'
    else:
        quality = '<div class="ok">Keine Auffälligkeiten gefunden.</div>'

    rows = "".join(_stat_row(s) for s in overview.stats)

    return f"""
<style>
  .dash {{ padding: 18px 22px 40px; color: {text}; background: {bg};
           font: 13px/1.5 system-ui, sans-serif; min-height: 100%; box-sizing: border-box; }}
  .dash h1 {{ font-size: 20px; margin: 0 0 2px; font-weight: 600; }}
  .dash h2 {{ font-size: 13px; margin: 26px 0 10px; text-transform: uppercase;
              letter-spacing: .08em; color: {muted}; font-weight: 600; }}
  .sub {{ color: {muted}; font-size: 12px; margin-bottom: 4px; }}
  .path {{ color: {muted}; font-size: 11px; font-family: ui-monospace, monospace;
           word-break: break-all; }}
  .tiles {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
  .tile {{ background: {panel}; border: 1px solid {border}; border-radius: 8px;
           padding: 12px 16px; min-width: 120px; }}
  .tile-value {{ font-size: 21px; font-weight: 600; }}
  .tile-label {{ color: {muted}; font-size: 11px; margin-top: 2px; }}
  .hint {{ color: {muted}; font-size: 10px; margin-top: 3px; font-style: italic; }}
  .finding {{ background: {panel}; border: 1px solid {border}; border-left-width: 4px;
              border-radius: 6px; padding: 11px 14px; margin-bottom: 8px; }}
  .finding-head {{ font-weight: 600; }}
  .finding-detail {{ color: {muted}; margin-top: 3px; }}
  .badge {{ color: #fff; border-radius: 4px; padding: 1px 7px; font-size: 10px;
            text-transform: uppercase; letter-spacing: .05em; margin-right: 7px; }}
  .chips {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }}
  .chip {{ background: transparent; color: {text}; border: 1px solid {border};
           border-radius: 11px; padding: 2px 9px; font: inherit; font-size: 11px;
           cursor: pointer; }}
  .chip:hover {{ border-color: #4c8dff; color: #4c8dff; }}
  .ok {{ background: {panel}; border: 1px solid {border}; border-left: 4px solid #2e9e5b;
         border-radius: 6px; padding: 11px 14px; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 1100px; }}
  th, td {{ text-align: right; padding: 6px 10px; border-bottom: 1px solid {border};
            white-space: nowrap; }}
  th {{ color: {muted}; font-weight: 600; font-size: 11px; text-transform: uppercase;
        letter-spacing: .04em; }}
  td.name, th.name {{ text-align: left; font-weight: 600; }}
  td.unit, th.unit {{ text-align: left; color: {muted}; font-size: 11px; }}
  tbody tr:hover {{ background: {panel}; }}
  .muted {{ color: {muted}; }}
  .stack-row {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-start; }}
  .map-card, .yield-card {{ background: {panel}; border: 1px solid {border};
                            border-radius: 8px; padding: 12px 14px; }}
  .yield-card {{ min-width: 190px; }}
  .card-head {{ display: flex; gap: 16px; align-items: baseline;
                justify-content: space-between; margin-bottom: 9px;
                font-size: 11px; color: {muted}; text-transform: uppercase;
                letter-spacing: .05em; }}
  .link {{ background: none; border: none; color: #4c8dff; cursor: pointer;
           font: inherit; text-transform: none; letter-spacing: 0; padding: 0; }}
  .link:hover {{ text-decoration: underline; }}
  .minimap {{ border-collapse: separate; border-spacing: 2px; width: auto; }}
  .minimap th {{ color: {muted}; font-size: 10px; padding: 0 2px; border: none;
                 text-align: center; }}
  .minimap th.rowlab {{ text-align: right; padding-right: 5px; }}
  .minimap td {{ padding: 0; border: none; }}
  .minimap td.empty {{ width: 34px; height: 24px; }}
  .cell {{ width: 36px; height: 24px; border-radius: 3px; border: 2px solid transparent;
           color: #fff; font: 600 9px/1 system-ui, sans-serif; cursor: pointer;
           text-shadow: 0 1px 2px rgba(0,0,0,.65); }}
  .cell.fail {{ border-color: #c8493f; }}
  .cell:hover {{ outline: 2px solid #4c8dff; }}
  .legend {{ color: {muted}; font-size: 10px; margin-top: 8px; }}
  .yield-value {{ font-size: 32px; font-weight: 600; line-height: 1.1; }}
  .yield-sub {{ color: {muted}; font-size: 12px; }}
  .yield-rule {{ margin-top: 7px; font-size: 11px; font-family: ui-monospace, monospace; }}
  .foot {{ color: {muted}; font-size: 11px; margin-top: 22px; }}
</style>
<div class="dash">
  <h1>{html.escape(overview.stack_id)}</h1>
  <div class="sub">{html.escape(overview.mode)}-Import · {types}</div>
  <div class="path">{html.escape(overview.source)}</div>
  <div class="tiles">{tiles}</div>
{_stack_block(overview.stack, muted)}

  <h2>Datenqualität</h2>
  {quality}

  <h2>Kennzahlen je Parameter</h2>
  <table>
    <thead><tr>
      <th class="name">Parameter</th><th class="unit">Einheit</th><th>N</th>
      <th>Median</th><th>Mittel</th><th>Std</th><th>CV</th>
      <th>p10</th><th>p90</th><th>Min</th><th>Max</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>

  <div class="foot">
    Tabellen in der Datenbank: {html.escape(" · ".join(overview.db_tables))}
    &nbsp;|&nbsp; erstellt {datetime.now():%Y-%m-%d %H:%M}
    &nbsp;|&nbsp; Device anklicken öffnet dessen Rohkurve
  </div>
</div>
"""
