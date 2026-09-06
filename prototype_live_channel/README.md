# Prototype: Live-Channel-Architektur

Die Anwendung auf einem **Live-Kanal** statt auf generierten HTML-Dateien.
Import, Transforms und alle zwoelf `fig_*.py`-Builder sind **euer bestehender
Code, unveraendert** — der Prototyp tauscht ausschliesslich den Transportweg:

```
vorher   DuckDB -> Figure -> write_html() + .json -> QWebEngineView.load(file://)
         pro Plot ein toter Schnappschuss, ~4 MB plotly.js in jeder Datei

jetzt    DuckDB <-> Bridge (QWebChannel) <-> eine Seite, die die Session ueberlebt
         plotly.js einmal geladen, Figures als JSON gepusht, Plotly.react() diffed
```

Getestet mit Python 3.12.10, PySide6 6.11.2, plotly 7.0.0 (plotly.js 4.0.0),
DuckDB 1.5.5, polars 1.44.1 auf Windows.

## Starten

Einmalig, im Repo-Wurzelverzeichnis:

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r prototype_live_channel\requirements.txt
```

Danach, aus diesem Ordner heraus:

```
..\.venv\Scripts\python.exe analysis_app.py
```

Der volle Pfad zum Interpreter spart das Aktivieren des venv; `python
analysis_app.py` funktioniert nur nach `.venv\Scripts\activate`.

`--smoke-test` baut das Fenster auf und beendet sofort (fuer CI).
Kein Vendoring-Schritt: `analysis_app.py` kopiert beim Start `plotly.min.js`
(aus dem plotly-Paket) und `qwebchannel.js` (aus den Qt-Ressourcen) nach `web/`.
Damit laeuft alles offline, und die plotly.js-Version kann nicht von der
plotly.py-Version abdriften.

## Testdaten

Es lagen keine echten Messdaten vor, deshalb erzeugt

```
python tools/make_fixtures.py <zielordner> --cycles 30
```

16 Devices x 4 Messdateien exakt nach den Konventionen aus IMPORT.md
(`<stack>/<device>/<NN typ>.xlsx`, `Run1..RunN`-Sheets, Spalten `AV`, `AI`,
`VSET`, `ILRS`, `IHRS`, `VRESET`, `IRESET`, `NORM_COND`, `VFORM`, `ILEAKAGE`).
Den Stack-Ordner dann mit Ctrl+Shift+O importieren.

## Feature-Abdeckung gegen FEATURES.md

| Bereich | Stand |
|---|---|
| Import Device / Stack, Glob-Level | uebernommen (`BatchConverter`, `path_to_glob`) |
| QThread + Fortschrittsdialog | ja |
| ProcessPool, Traceback-Meldung | uebernommen; Traceback im Detailbereich der Fehlerbox |
| Retry beim Loeschen des Temp-Ordners | **entfaellt** — es gibt keinen Temp-Ordner und keine Datei-Locks mehr |
| Device-Plots (Characteristic, Endurance, Boxplots, CDF, Correlation, Matrix) | alle, ueber eure Builder |
| Stack-Plots (Boxplots, CDF, Correlation, Matrix, Stack Map) | alle, ueber eure Builder |
| Combined-Vergleichsplots | enthalten (`combined_box_fig` / `combined_cdf_fig`) |
| **Yield-/Pass-Fail-Map** | **neu gebaut** (`fig_yield.py`) — im Repo gab es sie nirgends |
| Log/Linear je Plot, persistente Defaults | ja, ueber euer `core/preferences.py` |
| Legenden-Filterung | unveraendert, kommt aus den Figures |
| Dark Mode | ja, ueber euer `core/theme.py` |
| Export aktuell: PNG/JPEG/SVG/PDF/EPS/CSV/TXT | alle sieben |
| Export alle: PNG/JPEG/SVG/PDF | ja |
| Kombiniertes PDF, PowerPoint | ja |
| Legenden beim Export vergroessern | ja |
| Session-Memory (Groesse, Modus, Tab, Sub-Tab) | ja |
| Statusleiste, Memory Window, Wiki (F1), AppData | ja |
| `--smoke-test` | ja |

### Bewusst anders

- **Ein** `QWebEngineView` fuer die ganze Anwendung statt einer Instanz je Tab.
  Tabs waehlen nur noch aus, welche Figure gepusht wird.
- Die Yield-Steuerung sind Qt-Widgets, nicht in die Seite eingebettetes
  JavaScript. Der Schwellwert ist damit ein normaler Parameter: Python rechnet
  Pass/Fail neben den Daten, und die Exporter sehen dieselben Zahlen.
- **Neu hinzugekommen:** Devices im Plot per Lasso/Klick auswaehlen und mit
  *Filter to selection* die Builder auf die Teilmenge neu laufen lassen. Das
  ging vorher prinzipiell nicht — es braucht den Rueckkanal.

### Was noch offen ist

- Der Startbildschirm ist ein Hinweistext; die Knoepfe *Continue Device/Stack
  Level Analysis* aus `navigation_bar.py` fehlen. Sie setzen vorhandene
  HTML-Dateien voraus, brauchen hier also ein anderes Kriterium.
- Getestet ausschliesslich gegen die synthetischen Fixtures. Mit ihnen liefern
  `V_reset` und `I_reset_max` keine gueltigen Werte pro Device, weshalb Stack
  Map und Yield Map dafuer je vier statt sechs Metriken zeigen. Das ist eine
  Schwaeche der Fixtures, kein Fehler im Code — mit echten Messdaten
  nachpruefen.

## Dateien

| Datei | Rolle |
|---|---|
| `analysis_app.py` | Fenster, Menues, Tabs, Steuerung, Export-Aktionen |
| `channel.py` | Figure-Serialisierung, `Bridge`, `ImportWorker` |
| `live_pipeline.py` | `run.py` ohne Dateisystem: gibt Figures zurueck |
| `fig_yield.py` | die fehlende Yield-Map |
| `exporters.py` | Bild-, Daten-, PDF- und PPTX-Export |
| `web/analysis.html`, `web/analysis.js` | die Seite, die die Session ueberlebt |
| `tools/make_fixtures.py` | synthetische Messdaten |
| `demo.py`, `data.py`, `figures.py`, `web/index.html`, `web/app.js` | die urspruengliche Demo mit synthetischen Daten, weiterhin lauffaehig |

## Die drei Stellen, auf die es ankommt

1. **`channel.py::Bridge`** — ein `QObject` mit `@Slot`-Methoden (JS ruft Python)
   und einem `Signal` (Python ruft JS). Ersetzt den kompletten Umweg ueber das
   Dateisystem in rund 40 Zeilen.
2. **`web/analysis.js::show()`** — beim ersten Mal `Plotly.newPlot`, danach
   `Plotly.react`: ein Diff-Update statt eines Neuaufbaus.
3. **`channel.py::figure_payload()`** — `uirevision`. Ohne diesen Schluessel
   wirft `Plotly.react` den Zoom des Nutzers weg. Er wird auf dem JSON gesetzt,
   nicht auf der Figure, damit die Exporter genau das sehen, was die Builder
   erzeugt haben.
