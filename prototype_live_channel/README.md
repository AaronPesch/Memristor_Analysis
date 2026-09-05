# Live-Channel-Demo

Zeigt die Architektur aus der Diskussion an einem synthetischen 6x6-Stack
(36 Devices, je 200 Zyklen): **PySide6 + QWebChannel + Plotly, ohne eine
einzige HTML-Datei auf der Platte.**

Getestet mit Python 3.12.10, PySide6 6.11.2, plotly 7.0.0 (plotly.js 4.0.0),
DuckDB 1.5.5 auf Windows.

## Starten

```
pip install -r requirements.txt
python demo.py
```

Kein weiterer Schritt noetig. `demo.py` kopiert beim Start `plotly.min.js`
(aus dem plotly-Paket) und `qwebchannel.js` (aus den Qt-Ressourcen) nach `web/`.
Die App laeuft damit komplett offline und die plotly.js-Version passt immer zu
der plotly.py-Version, mit der die Figures gebaut werden. Genau das ist der
Unterschied zu `include_plotlyjs="cdn"` in eurem `PlotViewer.render_plot()`.

## Was du ausprobieren solltest

| Aktion | Was passiert |
|---|---|
| Auf ein Feld der Stack-Map klicken | Device wird zur Auswahl hinzugefuegt/entfernt, **alle anderen Plots ziehen mit** |
| Rechteck ueber mehrere Felder aufziehen | Mehrfachauswahl, ein DuckDB-Query, drei aktualisierte Plots |
| Im Korrelations-Scatter lassoen | Umgekehrte Richtung: Punktauswahl -> Devices -> Map und CDF filtern |
| Range-Slider unter dem Endurance-Plot ziehen | Zyklusbereich als Filter, wird nach 120 ms debounced an DuckDB geschickt |
| In einen Plot zoomen, dann Dark Mode umschalten | **Der Zoom bleibt.** Das ist `Plotly.react` + `uirevision` |
| Log-Skala umschalten | Nur die y-Achse skaliert neu, der x-Zoom bleibt stehen |
| Statuszeile unten | Zeigt die tatsaechliche DuckDB-Query-Zeit pro Interaktion |

## Wo das zu eurem Code steht

| Datei hier | Entspricht bei euch |
|---|---|
| `data.py` | `plotting/repository.py` + `plotting/db.py` |
| `figures.py` | `plotting/fig_*.py` |
| `demo.py` (Bridge) | **hat kein Gegenstueck** — das ist das neue Teil |
| `demo.py` (MainWindow) | `ui/main_window.py` + `ui/plot_viewer.py` |
| `web/` | ersetzt `plotting/run.py::_write` und `_write_json` |

Beachte, was in `figures.py` *fehlt*: kein `write_html`, kein `_write_json`,
kein `output_dir`. Ein Builder gibt eine Figure zurueck, der Transport ist nicht
sein Problem. Eure `fig_*.py` muessten dafuer praktisch nicht angefasst werden.

## Die drei Stellen, auf die es ankommt

1. **`demo.py::Bridge`** — ein `QObject` mit `@Slot`-Methoden (JS ruft Python)
   und einem `Signal` (Python ruft JS). Das ist der komplette Ersatz fuer den
   Umweg ueber das Dateisystem.

2. **`web/app.js::draw()`** — beim ersten Mal `Plotly.newPlot`, danach immer
   `Plotly.react`. Letzteres ist ein Diff-Update statt eines Neuaufbaus.

3. **`figures.py::_style()`** — `uirevision`. Ohne diesen Schluessel wirft
   `Plotly.react` den Zoom des Nutzers weg. Getrennte Revisions fuer x und y
   sorgen dafuer, dass ein Log/Linear-Wechsel nur die y-Achse zuruecksetzt.

## Was die Demo bewusst weglaesst

Export (PNG/PDF/PPTX), Tabs, Mode-Umschaltung Device/Stack, Preferences.
Das sind alles Dinge, die ihr schon habt und die von der Umstellung nicht
betroffen sind — der Export arbeitet weiterhin auf dem Figure-Objekt in Python
und braucht die Sidecar-`.json` dann nicht mehr.
