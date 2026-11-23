# Daten-Audit Barrierefreiheit Dortmund – Zwischenstand 23.11.2026

**Frage:** Wie gut sind die Dortmunder GTFS- und OSM-Daten für Barrierefreiheit an Haltestellen?

---

# Teil A – Ergebnisse und Schlussfolgerungen

## Befunde

**GTFS (VRR): für Barrierefreiheit unbrauchbar**
- Nur 3 von 997 Dortmunder Haltestellen (0,3 %) haben `wheelchair_boarding`, nur mit dem Wert 1, nie mit 2.
- Es gibt keine `pathways.txt` und keine `levels.txt`, also keine Information über Wege innerhalb von Stationen.
- `wheelchair_accessible` an Trips ist zu 100 % befüllt. DB-Verkehre haben aber pauschal den Wert 2 (nicht barrierefrei); das wirkt wie ein Exportstandard und nicht wie echte Information.

**OSM: brauchbar, aber lückenhaft**

| Merkmal | gesamt | mit Angabe | Anteil |
|---|---|---|---|
| GTFS-Haltestelle in OSM gefunden (über DHID) | 997 | 966 | 96,9 % |
| Haltestelle mit `wheelchair=*` | 997 | 494 | **49,5 %** |
| Steig mit `wheelchair=*` | 2.277 | 876 | **38,5 %** |

- Werte je Haltestelle: 233 yes, 110 no, 59 limited, 92 gemischt, 503 ohne Angabe. Anders als GTFS enthält OSM auch Negativinformation.
- Bei den gemischten Fällen weichen in 50 Fällen die Steige voneinander ab (plausibel), in 30 Fällen widersprechen sich Plattform und Halteposition, und in 13 Fällen ist derselbe Steig doppelt gemappt und widersprüchlich (Datenfehler).

| Für Routing gut nutzbar | Kaum vorhanden |
|---|---|
| Aufzüge (95; `wheelchair` 87 %, `level` 92 %) | **Steigung** als Zahl (0,5 % der Fußweg-Länge, siehe unten) |
| Treppen (`handrail` 62 %, `step_count` 57 %) | Wegbreite (4 %) |
| Oberfläche Fußwege (74 % der Länge) | Bordhöhe an Haltestellen (`kerb` 1 %, `kerb:height` 0 %) |
| Bordsteine an Querungen (`kerb` 71 %) | |

**Steigungen und Höhen: in OSM praktisch nicht vorhanden**

Im Konstanz-Projekt war das Gelände ein zentraler Faktor. In den Dortmunder OSM-Daten ist es kaum erfasst:

| Wegtyp (Dortmund) | Länge | `incline` als Zahl (%) | nur Richtung (up/down) |
|---|---|---|---|
| Fußwege | 2.884 km | 0,5 % der Länge (157 Wege) | 0,9 % |
| Straßen | 3.354 km | 0,1 % (16 Wege) | 0,4 % |
| Radwege | 89 km | 0 % | 0,9 % |
| Treppen | 3.341 Stück | 4 Treppen | 77 % |

- In ganz Dortmund gibt es nur 187 Wege mit einer Steigung als Zahl; 115 davon liegen über 6 %, dem Höchstwert für Rampen nach DIN 18040. Erfasst sind also fast nur auffällige Stellen, keine flächendeckenden Daten.
- An Treppen sagt `incline=up/down` nur aus, in welche Richtung der Weg verläuft, nicht wie steil er ist.
- Höhenangaben (`ele=*`) haben nur 55 Nodes, meist Gipfel. Ein Geländemodell lässt sich daraus nicht ableiten.

**Bahnstationen:** Große Stationen sind in OSM innen detailliert erfasst. Der Hbf hat zum Beispiel 11 Aufzüge, 20 Rolltreppen, 46 Treppen und 139 Wege mit `level`/`indoor`, ähnlich sieht es in Hörde, Möllerbrücke, Dorstfeld und an der Universität aus. Kleine ebenerdige Haltepunkte haben nur die Plattform. Ein einzelner `wheelchair`-Wert pro Station sagt wenig aus; am Hbf steht `limited`, die Details nur als Freitext.

## Schlussfolgerungen

1. **Rollenteilung:** GTFS dient nur dem Fahrplan und der Routenberechnung, die Barrierefreiheit kommt aus OSM. Die beiden Datensätze lassen sich über die DHID (`ref:IFOPT`) zu 97 % verknüpfen.
2. **Prüfpunkte entlang der Reise:** Barrierefreiheit wird dort geprüft, wo die Reise das Fahrzeug verlässt oder betritt:
   - am **Einstieg**: Ist der Bahnsteig von der Straße aus erreichbar?
   - beim **Umstieg**: Gibt es zwischen den Steigen einen stufenfreien Weg?
   - am **Ausstieg**: Kommt man vom Bahnsteig auf die Straße?
3. **Erreichbarkeit berechnen statt ablesen:** An gut gemappten Bahnstationen lässt sich die stufenfreie Erreichbarkeit aus dem OSM-Wegenetz berechnen (Aufzüge, Treppen, Ebenen). An Bushaltestellen genügen dagegen die Tags der Plattform.
4. **Steigungen kommen aus einem Höhenmodell, nicht aus OSM.** OTP kann beim Graph-Build ein digitales Höhenmodell (DEM, GeoTIFF) einlesen. Daraus berechnet es die Steigung jeder Kante und berücksichtigt sie beim Rollstuhl-Routing (`wheelchair.maxSlope`). Der aktuelle Graph ist ohne Höhenmodell gebaut. Mit einem Höhenmodell hätte man die Steigung flächendeckend; aus OSM bleiben nur Treppen, Aufzüge und Oberflächen.
5. **Grenzen:**
   - Etwa die Hälfte der Haltestellen hat keine Angabe. Dafür braucht es eine Regel, z. B. „unbekannt“ als eigenen Wert im Pareto-Kriterium.
   - Ob ein Fahrzeug barrierefrei ist, steht weiterhin nur im GTFS, und bei der DB ist diese Angabe fragwürdig.

## Nächste Schritte
1. In OTP Barrierefreiheit aus OSM an Haltestellen und Umstiegen berücksichtigen (Rollenteilung siehe oben).
2. Ein Höhenmodell für Dortmund beschaffen (z. B. das offene DGM von OpenGeodata.NRW; Verfügbarkeit und Lizenz noch prüfen) und den Graphen damit neu bauen. Danach auswerten, wie steil die Zuwege der Haltestellen sind.
3. Barrierefreiheit als zusätzliches Pareto-Kriterium in McRAPTOR einbauen.
4. Stufenfreie Erreichbarkeit der Bahnsteige an Bahnstationen berechnen und mit den getaggten Werten vergleichen.
5. Eine Stichprobe von 20–30 Haltestellen gegen die Realität prüfen. Externe Quellen prüfen: DB-Aufzugsstatus, DELFI/NRW-Kataster.
6. Klären, auf welchen Daten der Konstanz-Ansatz (Storandt) beruht.

---

# Teil B – Technische Umsetzung

## Daten und Abgrenzung
| Quelle | Datei |
|---|---|
| GTFS VRR (gültig 01.07.–31.12.2026) | `dev-data/08_2026_vrr_gtfs.zip` |
| OSM Reg.-Bez. Arnsberg (06.08.2026) | `dev-data/arnsberg-regbez-260806.osm.pbf` |
| OSM-Auszug Dortmund (Box um die Stadtgrenze + 1 km) | `dev-data/dortmund-260806.osm.pbf` |

- **Dortmund in GTFS:** DHID beginnt mit `de:05913:` (Gemeindeschlüssel).
- **Dortmund in OSM:** innerhalb der Stadtgrenze (`admin_level=6`). Die berechnete Fläche beträgt 280,6 km², amtlich sind es 280,7 km².
- **Verknüpfung:** DHID (GTFS) = `ref:IFOPT` (OSM). Die Schreibweise `de:5913:` wird zu `de:05913:` normalisiert.
- **Zählweise:** „Mit Angabe“ heißt, der Schlüssel ist vorhanden, auch mit dem Wert `no`. Eine Haltestelle hat eine Angabe, sobald mindestens ein OSM-Objekt eine hat.
- **Doppelte Plattformen:** Oft ist dieselbe Plattform als Node und als Weg gemappt. Deshalb gibt es 2.993 OSM-Plattformen, aber nur 2.277 GTFS-Steige. Die Kennzahlen pro Haltestelle sind davon nicht betroffen.

## Skripte (`analysis/`, Umgebung `analysis/.venv`)
| Skript | Zweck | Laufzeit |
|---|---|---|
| `extract_dortmund.py` | Dortmund-Auszug aus der PBF (die Quelldatei bleibt unverändert) | ~4 min |
| `osm_accessibility_audit.py [--radius]` | OSM-Merkmale stadtweit und im Umkreis um Haltestellen | ~4 min |
| `gtfs_osm_stop_join.py` | GTFS-Haltestellen ↔ OSM über DHID | Sekunden |
| `osm_station_indoor_inventory.py [--radius]` | Indoor-Bestand je Bahnstation | ~1 min |
| `osm_incline_elevation.py` | `incline` nach Wegtyp (Zahl / Richtung), `ele` an Nodes | ~20 s |

Aufruf: `analysis/.venv/bin/python analysis/<skript>.py`. Die Ergebnisse liegen als `*_2026-11-23.csv` in `analysis/`.

## Offene technische Punkte
- Die GTFS-Zahlen stammen aus einer Ad-hoc-Zählung; ein Skript dafür fehlt noch.
- Die Trip-Auswertung ist bisher nur für den ganzen VRR gerechnet, nicht für Dortmund.
- Der Umkreis von 300 m um Haltestellen deckt fast die ganze Stadt ab (95 % der Querungen) und unterscheidet nichts. Besser wären 100 m oder eine Distanz über das Fußwegnetz.
- `incline`-Werte als Zahl: Grad wird in Prozent umgerechnet, ausgewertet wird der Betrag. Fußwege umfassen hier auch Querungen (`footway=crossing`); daher 51.668 statt 47.852 Wege im OSM-Audit.
- Der Graph `graph-2026-11-23` ist ohne Höhenmodell gebaut. Das Einbinden eines Höhenmodells erfordert eine Änderung an der Build-Konfiguration und geschieht nur nach Rückfrage.
- Für gemischte Haltestellen fehlt noch eine Regel, z. B. „Plattform vor Halteposition, schlechtester Steig zählt“.
- Einige unterirdische Stadtbahnstationen (z. B. Kampstraße) sind in OSM nicht als `station` getaggt und fehlen deshalb im Indoor-Bestand.
