"""
OSM-Accessibility-Audit für Haltestellen in Dortmund.

Liest die OSM-PBF-Datei (nur lesend), bestimmt die Stadtgrenze Dortmund
(boundary=administrative, admin_level=6, name=Dortmund) und wertet aus:

  1. Haltestellen-Objekte (Plattformen, Stationen, Halteposition, stop_area-Relationen):
     Anteil mit wheelchair=*, tactile_paving=*, kerb, Bank, Unterstand, DHID (ref:IFOPT) ...
  2. Infrastruktur im Umkreis r um Plattformen/Stationen: Aufzüge, Querungen,
     Bordsteine, Fußwege, Treppen, Straßen mit Gehweg-Angaben.
     Für Wege: Anteil nach Anzahl und nach Länge (Länge innerhalb des Umkreises).
  3. Häufigkeit aller Accessibility-bezogenen Schlüssel an allen Objekten in Dortmund.

"Mit Angabe" heißt: der Schlüssel ist vorhanden (beliebiger Wert, auch "no").
Die Werteverteilung steht in der Spalte "Werte".

Ausgabe (Datum = heute):
  analysis/osm_accessibility_audit_<Datum>.csv     Haupttabelle
  analysis/osm_stop_keys_<Datum>.csv               alle Schlüssel an Haltestellen-Objekten
  analysis/osm_a11y_keys_dortmund_<Datum>.csv      Accessibility-Schlüssel an allen Objekten
  analysis/osm_stops_dortmund_<Datum>.csv          Haltestellen-Objekte einzeln (für GTFS-Join)

Aufruf:
  analysis/.venv/bin/python analysis/osm_accessibility_audit.py [--radius 300] [--pbf PFAD]
"""

import argparse
import collections
import datetime
import re
from pathlib import Path

import osmium
import pandas as pd
import pyproj
from shapely import wkb
from shapely.geometry import LineString, Point
import shapely
from shapely.ops import unary_union
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PBF_SOURCE = ROOT / "dev-data" / "arnsberg-regbez-260806.osm.pbf"
DEFAULT_PBF_EXTRACT = ROOT / "dev-data" / "dortmund-260806.osm.pbf"  # aus extract_dortmund.py
DEFAULT_PBF = DEFAULT_PBF_EXTRACT if DEFAULT_PBF_EXTRACT.exists() else DEFAULT_PBF_SOURCE
OUT_DIR = ROOT / "analysis"

_TRANSFORMER = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)


def to_utm(geom):
  return shapely.transform(geom, lambda xy: list(zip(*_TRANSFORMER.transform(xy[:, 0], xy[:, 1]))))

# Schlüssel, die an der jeweiligen Objektklasse ausgewertet werden.
STOP_KEYS = [
  "wheelchair", "wheelchair:description", "tactile_paving", "kerb", "kerb:height",
  "shelter", "bench", "lit", "departures_board", "passenger_information_display",
  "surface", "width", "level", "ref:IFOPT",
]
KEYS_BY_CLASS = {
  "Aufzug (highway=elevator)": ["wheelchair", "level", "door", "width", "opening_hours",
                                "handrail", "tactile_writing", "speech_output"],
  "Querung (highway=crossing)": ["crossing", "kerb", "tactile_paving",
                                 "traffic_signals:sound", "traffic_signals:vibration",
                                 "wheelchair"],
  "Bordstein (barrier=kerb)": ["kerb", "kerb:height", "tactile_paving", "wheelchair"],
  "Fußweg (footway/path/pedestrian)": ["surface", "smoothness", "incline", "width", "lit",
                                       "tactile_paving", "wheelchair"],
  "Treppe (highway=steps)": ["step_count", "handrail", "ramp", "ramp:wheelchair",
                             "ramp:stroller", "incline", "conveying", "tactile_paving",
                             "wheelchair"],
  "Straße (mit möglichem Gehweg)": ["sidewalk*"],
}

FOOTWAYS = {"footway", "path", "pedestrian"}
ROADS = {"primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
         "primary_link", "secondary_link", "tertiary_link"}
A11Y_KEY_RE = re.compile(
  r"^(wheelchair|tactile_paving|kerb|ramp|step_count|handrail|incline|smoothness|"
  r"toilets:wheelchair|sidewalk|traffic_signals:(sound|vibration)|tactile_writing|"
  r"speech_output|step:|door|entrance|width|surface)"
)


def find_dortmund(pbf):
  """Pass 1: Stadtgrenze Dortmund als Polygon in WGS84."""
  fab = osmium.geom.WKBFactory()
  fp = (
    osmium.FileProcessor(str(pbf))
    .with_areas(osmium.filter.TagFilter(("boundary", "administrative")))
    .with_filter(osmium.filter.EntityFilter(osmium.osm.AREA))
  )
  for a in fp:
    if a.tags.get("name") == "Dortmund" and a.tags.get("admin_level") == "6":
      return wkb.loads(fab.create_multipolygon(a), hex=True)
  raise SystemExit("Stadtgrenze Dortmund nicht gefunden")


def classify(tags):
  """Ordnet ein OSM-Objekt genau einer Klasse zu (oder None)."""
  pt, hw, rw = tags.get("public_transport"), tags.get("highway"), tags.get("railway")
  if pt == "platform" or hw == "bus_stop" or rw == "platform":
    return "Plattform"
  if pt == "station" or rw in ("station", "halt"):
    return "Station"
  if pt == "stop_position" or rw == "tram_stop":
    return "Halteposition"
  if hw == "elevator":
    return "Aufzug (highway=elevator)"
  if hw == "crossing" or (hw == "footway" and tags.get("footway") == "crossing"):
    return "Querung (highway=crossing)"
  if tags.get("barrier") == "kerb":
    return "Bordstein (barrier=kerb)"
  if hw == "steps":
    return "Treppe (highway=steps)"
  if hw in FOOTWAYS:
    return "Fußweg (footway/path/pedestrian)"
  if hw in ROADS:
    return "Straße (mit möglichem Gehweg)"
  return None


def platform_mode(tags):
  """Grobe Verkehrsmittel-Zuordnung von Plattformen."""
  if tags.get("railway") == "platform" or tags.get("train") == "yes":
    return "Bahn"
  if tags.get("subway") == "yes" or tags.get("light_rail") == "yes":
    return "Stadtbahn"
  if tags.get("tram") == "yes":
    return "Straßenbahn"
  if tags.get("highway") == "bus_stop" or tags.get("bus") == "yes":
    return "Bus"
  return "unbekannt"


def collect(pbf, city):
  """Pass 2: alle relevanten Objekte innerhalb Dortmunds einsammeln."""
  city_p = prep(city)
  minx, miny, maxx, maxy = city.bounds
  objs = []  # dicts: osm, cls, tags, geom (UTM)
  stop_ids = set()
  key_count = collections.Counter()
  key_values = collections.defaultdict(collections.Counter)

  def in_bbox(lon, lat):
    return minx <= lon <= maxx and miny <= lat <= maxy

  def count_keys(tags):
    for k, v in tags.items():
      if A11Y_KEY_RE.match(k):
        key_count[k] += 1
        key_values[k][v] += 1

  for o in osmium.FileProcessor(str(pbf)).with_locations():
    if len(o.tags) == 0:
      continue
    if o.is_node():
      lon, lat = o.location.lon, o.location.lat
      if not in_bbox(lon, lat) or not city_p.contains(Point(lon, lat)):
        continue
      tags = dict(o.tags)
      count_keys(tags)
      cls = classify(tags)
      if cls:
        objs.append(dict(osm=f"n{o.id}", cls=cls, tags=tags,
                         geom=to_utm(Point(lon, lat))))
        if cls in ("Plattform", "Station", "Halteposition"):
          stop_ids.add(("n", o.id))
    elif o.is_way():
      coords = [(n.lon, n.lat) for n in o.nodes if n.location.valid()]
      if len(coords) < 2 or not any(in_bbox(*c) for c in coords):
        continue
      line = LineString(coords)
      if not city_p.intersects(line):
        continue
      tags = dict(o.tags)
      count_keys(tags)
      cls = classify(tags)
      if cls:
        objs.append(dict(osm=f"w{o.id}", cls=cls, tags=tags, geom=to_utm(line)))
        if cls in ("Plattform", "Station", "Halteposition"):
          stop_ids.add(("w", o.id))
    elif o.is_relation():
      tags = dict(o.tags)
      if tags.get("public_transport") != "stop_area":
        continue
      if any((m.type, m.ref) in stop_ids for m in o.members):
        objs.append(dict(osm=f"r{o.id}", cls="stop_area-Relation", tags=tags, geom=None))
  return objs, key_count, key_values


def has_key(tags, key):
  if key.endswith("*"):
    return any(k.startswith(key[:-1]) for k in tags)
  return key in tags


def value_summary(series, top=6):
  c = collections.Counter(series)
  return "; ".join(f"{v}={n}" for v, n in c.most_common(top))


def audit_rows(df, cls, keys, scope, length_col=None):
  rows = []
  sub = df[df.cls == cls]
  for key in keys:
    mask = sub.tags.map(lambda t: has_key(t, key))
    if key.endswith("*"):
      vals = sub[mask].tags.map(
        lambda t: ",".join(sorted(f"{k}={v}" for k, v in t.items() if k.startswith(key[:-1]))))
    else:
      vals = sub[mask].tags.map(lambda t: t[key])
    row = {
      "Merkmal": key, "Quelle": "OSM", "Objektklasse": cls, "Bezug": scope,
      "Anzahl gesamt": len(sub), "Anzahl mit Angabe": int(mask.sum()),
      "Anteil in %": round(100 * mask.mean(), 1) if len(sub) else None,
      "Werte (Top)": value_summary(vals),
    }
    if length_col:
      total = sub[length_col].sum()
      row["Länge gesamt km"] = round(total / 1000, 1)
      row["Anteil nach Länge %"] = round(100 * sub[mask][length_col].sum() / total, 1) if total else None
    rows.append(row)
  return rows


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--pbf", default=str(DEFAULT_PBF))
  ap.add_argument("--radius", type=float, default=300.0, help="Umkreis um Haltestellen in m")
  args = ap.parse_args()
  today = datetime.date.today().isoformat()

  city = find_dortmund(args.pbf)
  print(f"Dortmund-Polygon: {to_utm(city).area / 1e6:.1f} km²")
  objs, key_count, key_values = collect(args.pbf, city)
  df = pd.DataFrame(objs)
  print(df.cls.value_counts().to_string())

  rows = []
  # 1. Haltestellen-Objekte, gesamtes Stadtgebiet
  for cls in ["Plattform", "Station", "Halteposition", "stop_area-Relation"]:
    rows += audit_rows(df, cls, STOP_KEYS, "Dortmund")
  plat = df[df.cls == "Plattform"].copy()
  plat["mode"] = plat.tags.map(platform_mode)
  for mode, g in plat.groupby("mode"):
    g = g.assign(cls=f"Plattform – {mode}")
    rows += audit_rows(g, f"Plattform – {mode}", ["wheelchair", "tactile_paving", "kerb",
                                                   "kerb:height", "ref:IFOPT"], "Dortmund")

  # 2. Infrastruktur im Umkreis um Plattformen und Stationen
  anchors = df[df.cls.isin(["Plattform", "Station"])].geom
  zone = prep(unary_union([g.buffer(args.radius) for g in anchors]))
  zone_geom = unary_union([g.buffer(args.radius) for g in anchors])
  infra = df[df.cls.isin(KEYS_BY_CLASS)].copy()
  infra["near"] = infra.geom.map(zone.intersects)
  infra["len_all"] = infra.geom.map(lambda g: g.length)
  near = infra[infra.near].copy()
  near["len_near"] = near.geom.map(lambda g: g.intersection(zone_geom).length)
  scope = f"≤ {args.radius:.0f} m um Plattform/Station"
  for cls, keys in KEYS_BY_CLASS.items():
    is_way = cls.startswith(("Fußweg", "Treppe", "Straße"))
    rows += audit_rows(near, cls, keys, scope, "len_near" if is_way else None)
    rows += audit_rows(infra, cls, keys, "Dortmund", "len_all" if is_way else None)

  # Haltestellen-Objekte einzeln, für die Verknüpfung mit GTFS über ref:IFOPT (= DHID)
  stop_df = df[df.cls.isin(["Plattform", "Station", "Halteposition", "stop_area-Relation"])]
  pd.DataFrame({
    "osm": stop_df.osm, "klasse": stop_df.cls,
    **{k: stop_df.tags.map(lambda t, k=k: t.get(k)) for k in ["name"] + STOP_KEYS},
  }).to_csv(OUT_DIR / f"osm_stops_dortmund_{today}.csv", index=False)

  out = pd.DataFrame(rows)
  out.to_csv(OUT_DIR / f"osm_accessibility_audit_{today}.csv", index=False)

  # Alle Schlüssel an Haltestellen-Objekten (zur Entdeckung weiterer Merkmale)
  stops = df[df.cls.isin(["Plattform", "Station", "Halteposition"])]
  kc = collections.Counter(k for t in stops.tags for k in t)
  pd.DataFrame(
    [(k, n, round(100 * n / len(stops), 1)) for k, n in kc.most_common()],
    columns=["Schlüssel", "Anzahl", "Anteil an Haltestellen-Objekten %"],
  ).to_csv(OUT_DIR / f"osm_stop_keys_{today}.csv", index=False)

  pd.DataFrame(
    [(k, n, value_summary(key_values[k].elements())) for k, n in key_count.most_common()],
    columns=["Schlüssel", "Objekte in Dortmund", "Werte (Top)"],
  ).to_csv(OUT_DIR / f"osm_a11y_keys_dortmund_{today}.csv", index=False)

  print(f"geschrieben: analysis/*_{today}.csv")


if __name__ == "__main__":
  main()
