"""
Wie gut sind Steigungen und Höhen in den Dortmunder OSM-Daten erfasst?

Zählt innerhalb der Stadtgrenze Dortmund:
  - incline=* an Wegen, getrennt nach Wegtyp (Fußweg, Treppe, Radweg, Straße, ...),
    nach Anzahl und Länge. Werte werden eingeteilt in:
      numerisch  (z. B. "6%", "-10%", "3°", "0")  -> nutzbar für Routing
      Richtung   ("up", "down")                   -> nur Richtung, keine Größe
      sonstiges  ("yes", "no", ...)
  - Verteilung der numerischen Werte (Betrag in %), Schwelle 6 % = Höchstwert für
    Rampen nach DIN 18040.
  - ele=* an Nodes (Höhenangaben), nach Objektart.

Aufruf: analysis/.venv/bin/python analysis/osm_incline_elevation.py
"""

import collections
import datetime
import math
import re
from pathlib import Path

import osmium
import pandas as pd
import shapely
from shapely.prepared import prep

from osm_accessibility_audit import DEFAULT_PBF, find_dortmund, to_utm

ROOT = Path(__file__).resolve().parent.parent
NUM_RE = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*(%|°)?\s*$")

WAY_GROUPS = {
  "Fußweg (footway/path/pedestrian)": {"footway", "path", "pedestrian"},
  "Treppe (steps)": {"steps"},
  "Radweg (cycleway)": {"cycleway"},
  "Wirtschafts-/Feldweg (track)": {"track"},
  "Straße (residential … primary, living_street, service)": {
    "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
    "service", "primary_link", "secondary_link", "tertiary_link"},
}


def incline_kind(v):
  if v is None:
    return None, None
  m = NUM_RE.match(v)
  if m:
    x = float(m.group(1).replace(",", "."))
    pct = math.tan(math.radians(x)) * 100 if m.group(2) == "°" else x
    return "numerisch", abs(pct)
  if v in ("up", "down"):
    return "Richtung (up/down)", None
  return "sonstiges", None


def group_of(hw):
  for g, s in WAY_GROUPS.items():
    if hw in s:
      return g
  return None


def main():
  today = datetime.date.today().isoformat()
  city_geom = find_dortmund(DEFAULT_PBF)
  city = prep(city_geom)
  minx, miny, maxx, maxy = city_geom.bounds

  ways = []  # group, kind, pct, length
  ele = collections.Counter()
  ele_total = 0
  for o in osmium.FileProcessor(str(DEFAULT_PBF)).with_locations().with_filter(
    osmium.filter.EmptyTagFilter()
  ):
    if o.is_node():
      if "ele" in o.tags:
        lon, lat = o.location.lon, o.location.lat
        if minx <= lon <= maxx and miny <= lat <= maxy and city.contains(shapely.Point(lon, lat)):
          t = o.tags
          kind = next((f"{k}={t[k]}" for k in ("natural", "railway", "public_transport",
                                                "highway", "man_made", "amenity", "tourism")
                       if k in t), "sonstiges")
          ele[kind] += 1
          ele_total += 1
    elif o.is_way():
      g = group_of(o.tags.get("highway"))
      if not g:
        continue
      coords = [(n.lon, n.lat) for n in o.nodes if n.location.valid()]
      if len(coords) < 2:
        continue
      line = shapely.LineString(coords)
      if not city.intersects(line):
        continue
      kind, pct = incline_kind(o.tags.get("incline"))
      ways.append((g, kind, pct, to_utm(line).length))

  df = pd.DataFrame(ways, columns=["gruppe", "art", "pct", "laenge"])
  rows = []
  for g, sub in df.groupby("gruppe"):
    total_len = sub.laenge.sum()
    for art in ["numerisch", "Richtung (up/down)", "sonstiges"]:
      s = sub[sub.art == art]
      rows.append({
        "Merkmal": f"incline {art}", "Quelle": "OSM", "Objektklasse": g,
        "Anzahl gesamt": len(sub), "Anzahl mit Angabe": len(s),
        "Anteil in %": round(100 * len(s) / len(sub), 2),
        "Länge gesamt km": round(total_len / 1000, 1),
        "Anteil nach Länge %": round(100 * s.laenge.sum() / total_len, 2),
      })
  out = pd.DataFrame(rows)
  out.to_csv(ROOT / "analysis" / f"osm_incline_{today}.csv", index=False)
  pd.set_option("display.width", 250)
  print(out.drop(columns=["Quelle"]).to_string(index=False))

  num = df[df.art == "numerisch"]
  bins = [-0.01, 0, 3, 6, 10, 20, 1000]
  labels = ["0 %", "≤3 %", "3–6 %", "6–10 %", "10–20 %", ">20 %"]
  print("\nNumerische incline-Werte (Betrag), alle Wegtypen:")
  print(pd.cut(num.pct, bins=bins, labels=labels).value_counts().sort_index().to_string())
  print(f"\nNodes mit ele=* in Dortmund: {ele_total}")
  for k, n in ele.most_common(10):
    print(f"  {k}: {n}")


if __name__ == "__main__":
  main()
