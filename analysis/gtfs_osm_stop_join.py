"""
Verknüpft Dortmunder GTFS-Haltestellen (VRR) mit OSM-Haltestellen-Objekten über die DHID.

GTFS: stops.txt, Spalte NVBW_HST_DHID beginnt mit "de:05913:" (Gemeindeschlüssel Dortmund);
      die stop_id ist die DHID des Steigs (z. B. de:05913:131:1:01).
OSM:  analysis/osm_stops_dortmund_<Datum>.csv aus osm_accessibility_audit.py, Schlüssel ref:IFOPT.
      Normalisierung: "de:5913:" -> "de:05913:"; mehrere Werte mit ";" werden aufgeteilt.

Zwei Ebenen:
  Haltestelle (DHID, 3 Teile):  Gibt es ein OSM-Objekt dieser Haltestelle mit wheelchair=*?
                                Zusammenfassung: alle yes / alle no / gemischt (inkl. limited).
  Steig (stop_id, 5 Teile):     Gibt es eine OSM-Plattform mit genau dieser IFOPT und wheelchair=*?

Aufruf: analysis/.venv/bin/python analysis/gtfs_osm_stop_join.py [--date 2026-11-23]
"""

import argparse
import datetime
import io
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GTFS = ROOT / "dev-data" / "08_2026_vrr_gtfs.zip"


def norm_ifopt(v):
  v = v.strip()
  return "de:05913:" + v[len("de:5913:"):] if v.startswith("de:5913:") else v


def summarize(values):
  vals = set(values)
  if not vals:
    return "keine Angabe"
  if vals == {"yes"}:
    return "yes"
  if vals == {"no"}:
    return "no"
  if vals == {"limited"}:
    return "limited"
  return "gemischt"


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--date", default=datetime.date.today().isoformat())
  args = ap.parse_args()

  with zipfile.ZipFile(GTFS) as z:
    stops = pd.read_csv(io.TextIOWrapper(z.open("stops.txt"), "utf-8-sig"), dtype=str)
  do = stops[stops.NVBW_HST_DHID.fillna("").str.startswith("de:05913:")]
  gtfs_dhids = set(do.NVBW_HST_DHID)
  gtfs_steige = set(do[do.location_type.fillna("0") == "0"].stop_id)

  osm = pd.read_csv(ROOT / "analysis" / f"osm_stops_dortmund_{args.date}.csv", dtype=str)
  osm = osm[osm["ref:IFOPT"].notna()].copy()
  osm["ifopt"] = osm["ref:IFOPT"].str.split(";")
  osm = osm.explode("ifopt")
  osm["ifopt"] = osm.ifopt.map(norm_ifopt)
  osm["dhid"] = osm.ifopt.str.split(":").str[:3].str.join(":")

  rows = []

  # Ebene Haltestelle
  wc = osm[osm.wheelchair.notna()].groupby("dhid").wheelchair.agg(summarize)
  per_dhid = pd.Series({d: wc.get(d, "keine Angabe") for d in gtfs_dhids})
  in_osm = sum(d in set(osm.dhid) for d in gtfs_dhids)
  rows.append(("Haltestelle in OSM gefunden (ref:IFOPT)", len(gtfs_dhids), in_osm))
  n_with = int((per_dhid != "keine Angabe").sum())
  rows.append(("Haltestelle mit OSM-wheelchair=* (mind. ein Objekt)", len(gtfs_dhids), n_with))
  dist_dhid = per_dhid.value_counts()

  # Ebene Steig
  plat = osm[osm.klasse == "Plattform"]
  wc_steig = plat[plat.wheelchair.notna()].groupby("ifopt").wheelchair.agg(summarize)
  found = sum(s in set(plat.ifopt) for s in gtfs_steige)
  with_wc = sum(s in wc_steig.index for s in gtfs_steige)
  rows.append(("Steig in OSM gefunden (Plattform mit gleicher IFOPT)", len(gtfs_steige), found))
  rows.append(("Steig mit OSM-wheelchair=* an der Plattform", len(gtfs_steige), with_wc))
  dist_steig = pd.Series([wc_steig.get(s, "keine Angabe") for s in gtfs_steige]).value_counts()

  out = pd.DataFrame(rows, columns=["Merkmal", "Anzahl gesamt", "Anzahl mit Angabe"])
  out.insert(1, "Quelle", "GTFS+OSM")
  out["Anteil in %"] = (100 * out["Anzahl mit Angabe"] / out["Anzahl gesamt"]).round(1)
  out.to_csv(ROOT / "analysis" / f"gtfs_osm_stop_join_{args.date}.csv", index=False)
  print(out.to_string(index=False))
  print("\nwheelchair je Haltestelle (DHID):\n" + dist_dhid.to_string())
  print("\nwheelchair je Steig:\n" + dist_steig.to_string())


if __name__ == "__main__":
  main()
