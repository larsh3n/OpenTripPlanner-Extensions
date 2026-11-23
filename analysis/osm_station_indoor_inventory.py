"""
Bestandsaufnahme: Wie gut sind die Innenräume/Zuwege der Dortmunder Bahn- und U-Bahn-Stationen
in OSM erfasst? Grundlage für die Frage "Sind alle Bahnsteige stufenfrei erreichbar?".

Stationen: public_transport=station oder railway=station|halt innerhalb der Stadtgrenze.
Je Station werden im Umkreis --radius (Standard 150 m, Luftlinie) gezählt:
  - Plattformen (railway=platform / public_transport=platform mit train|subway|light_rail=yes)
    und wie viele davon level=* haben
  - Aufzüge (highway=elevator), Rolltreppen (conveying=*), Treppen (highway=steps)
  - Fußwege mit level=* oder indoor=*, highway=corridor, indoor=* Flächen
  - Eingänge (entrance=* / railway=subway_entrance)
Ein Weg zählt, wenn mindestens ein Node im Umkreis liegt.

Aufruf: analysis/.venv/bin/python analysis/osm_station_indoor_inventory.py [--radius 150]
"""

import argparse
import datetime
import math
from pathlib import Path

import osmium
import pandas as pd
import shapely
from shapely.geometry import Point
from shapely.prepared import prep

from osm_accessibility_audit import DEFAULT_PBF, find_dortmund, to_utm

ROOT = Path(__file__).resolve().parent.parent


def is_station(t):
  return t.get("public_transport") == "station" or t.get("railway") in ("station", "halt")


def is_rail_platform(t):
  return t.get("railway") == "platform" or (
    t.get("public_transport") == "platform"
    and any(t.get(m) == "yes" for m in ("train", "subway", "light_rail"))
  )


def features(t):
  """Liefert die Merkmalsnamen, die ein Objekt erfüllt."""
  f = []
  hw = t.get("highway")
  if is_rail_platform(t):
    f.append("Plattformen")
    if "level" in t:
      f.append("Plattformen mit level")
    if "wheelchair" in t:
      f.append("Plattformen mit wheelchair")
  if hw == "elevator":
    f.append("Aufzüge")
  if "conveying" in t:
    f.append("Rolltreppen")
  if hw == "steps":
    f.append("Treppen")
  if hw in ("footway", "path", "pedestrian", "corridor") and ("level" in t or "indoor" in t):
    f.append("Fußwege mit level/indoor")
  if hw == "corridor":
    f.append("highway=corridor")
  if "indoor" in t and hw is None:
    f.append("indoor-Flächen")
  if "entrance" in t or t.get("railway") == "subway_entrance":
    f.append("Eingänge")
  return f


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--pbf", default=str(DEFAULT_PBF))
  ap.add_argument("--radius", type=float, default=150.0)
  args = ap.parse_args()
  today = datetime.date.today().isoformat()

  city = prep(find_dortmund(args.pbf))
  stations, objs = [], []
  for o in osmium.FileProcessor(str(args.pbf)).with_locations().with_filter(
    osmium.filter.EmptyTagFilter()
  ):
    t = dict(o.tags)
    if o.is_node():
      pts = [(o.location.lon, o.location.lat)]
    elif o.is_way():
      pts = [(n.lon, n.lat) for n in o.nodes if n.location.valid()]
    else:
      continue
    if not pts:
      continue
    if is_station(t):
      lon, lat = pts[0] if len(pts) == 1 else shapely.LineString(pts).centroid.coords[0]
      if city.contains(Point(lon, lat)):
        stations.append(dict(osm=f"{'n' if o.is_node() else 'w'}{o.id}", name=t.get("name"),
                             typ=t.get("railway") or t.get("station") or "",
                             wheelchair=t.get("wheelchair"), geom=to_utm(Point(lon, lat))))
      continue
    f = features(t)
    if f:
      geom = to_utm(shapely.MultiPoint(pts))
      objs.append((f, geom))

  tree = shapely.STRtree([g for _, g in objs])
  rows = []
  for s in stations:
    row = {k: s[k] for k in ("osm", "name", "typ", "wheelchair")}
    for i in tree.query(s["geom"], predicate="dwithin", distance=args.radius):
      for f in objs[i][0]:
        row[f] = row.get(f, 0) + 1
    rows.append(row)
  df = pd.DataFrame(rows)
  cols = ["Plattformen", "Plattformen mit level", "Plattformen mit wheelchair", "Aufzüge",
          "Rolltreppen", "Treppen", "Fußwege mit level/indoor", "highway=corridor",
          "indoor-Flächen", "Eingänge"]
  for c in cols:
    df[c] = df[c].fillna(0).astype(int) if c in df else 0
  df = df[["osm", "name", "typ", "wheelchair"] + cols].sort_values("name")
  out = ROOT / "analysis" / f"osm_station_indoor_{today}.csv"
  df.to_csv(out, index=False)
  pd.set_option("display.width", 250)
  print(df.to_string(index=False))
  print("geschrieben:", out)


if __name__ == "__main__":
  main()
