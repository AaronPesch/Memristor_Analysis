# Tests fuer den Prototyp

```
pytest prototype_live_channel/tests          # alles, rund 90 s
pytest prototype_live_channel/tests -m "not gui"     # ohne Qt-Fenster
pytest prototype_live_channel/tests -m "not slow"    # ohne Bildexport
```

67 Tests. Sie brauchen **keine** Messdaten: `conftest.py` erzeugt einmal pro Lauf
einen synthetischen 4x4-Stack ueber `tools/make_fixtures.py` und importiert ihn
mit dem echten `BatchConverter`. Damit laufen sie auf jedem Rechner und in der CI.

## Marker

| Marker | Bedeutung |
|---|---|
| `gui` | baut ein echtes Qt-Fenster samt `QWebEngineView` |
| `slow` | rendert Bilder ueber kaleido (braucht eine Chrome-Installation) |
| `realdata` | nur mit `MEMRISTOR_TEST_DATA=<Stack-Ordner>`, sonst uebersprungen |

Bildexport-Tests ueberspringen sich selbst, wenn kaleido nicht rendern kann —
in der CI faellt dann der Rest trotzdem durch.

## Was abgedeckt ist

| Datei | Inhalt |
|---|---|
| `test_live_pipeline.py` | Import, Kategorien, und dass **keine Dateien geschrieben werden** |
| `test_dashboard.py` | Kennzahlen, alle Qualitaetspruefungen, Rendering, Sprachpruefung |
| `test_yield_and_3d.py` | Yield-Map, Overview-Kachel, 3D-Ansicht |
| `test_drilldown.py` | Klickaufloesung, Hervorhebung, Rohkurve |
| `test_exporters.py` | sieben Formate, kombiniertes PDF, PPTX |
| `test_channel.py` | der Live-Kanal: Fenster, Seite, Bridge, Import-Thread |

## Regressionen, die hier festgenagelt sind

Jeder dieser Fehler ist im Lauf der Entwicklung einmal aufgetreten:

- **Deadlock am Importende.** `worker.finished` an ein Lambda gehaengt; Qt kann
  fuer ein gewoehnliches Callable keinen Empfaengerthread bestimmen, faellt auf
  eine direkte Verbindung zurueck, und `_stop_thread()` wartet auf den Thread,
  der gerade wartet. → `test_import_through_the_worker_thread`
- **Stack-ID als Device missdeutet.** `T25098` passt auf `<Buchstaben><Ziffern>`,
  ist aber kein Device. → `test_stack_id_is_not_mistaken_for_a_device`
- **`PASS` als Device missdeutet.** Die Yield-Heatmap fuehrt `PASS`/`FAIL` in
  `customdata`. → `test_customdata_is_validated_against_the_known_devices`
- **Dark Mode nur halb.** Qt-Palette, Web-View-Hintergrund und Seiteninhalt sind
  drei getrennte Flaechen. → `test_dark_mode_reaches_every_surface`
- **Export sah die Hervorhebung.** Das Dimmen gehoert aufs Payload, nicht auf die
  Figure. → `test_highlight_does_not_touch_the_stored_figure`
- **EPS-Export an `KeyError('Verdana')`.** Plotlys Standard-Schriftstack laesst
  sich von svglib nicht aufloesen. → `test_eps_survives_the_font_substitution`
- **Kachel widersprach der Yield-Map.** → `test_tile_matches_the_yield_figure`

## Zwei Fallstricke, die beim Schreiben auffielen

**Session-Fixtures sind veraenderlich.** `stack_categories` wird einmal gebaut
und weitergereicht. Die GUI-Tests veraendern die Kategorien (`on_yield_changed`
ersetzt eine Figure), was in spaetere Tests durchschlug. Deshalb arbeiten sie
ueber `categories_copy` auf einer eigenen Kopie.

**Die Fixtures sind nicht so reichhaltig wie echte Messungen.** Fuer `V_reset`
und `I_reset_max` liefern sie keine gueltigen Werte pro Device, deshalb kennen
Stack Map und Yield Map dort nur vier statt sechs Metriken. Tests duerfen das
nicht als Anforderung festschreiben — mit echten Daten sind es sechs.

## Hinweis zum Gesamtlauf

`pytest` aus dem Repo-Wurzelverzeichnis sammelt auch `tests/` ein. Dort schlagen
derzeit 16 Tests fehl und einer bricht ab — **unabhaengig vom Prototyp**, siehe
die Notiz im Projekt-README bzw. die Diskussion zur CI.
