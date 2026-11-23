"""
Schreibt einen Dortmund-Auszug aus der OSM-PBF-Datei als neue Datei (Quelle bleibt unverändert).

Gebiet: Bounding-Box der Stadtgrenze Dortmund (boundary=administrative, admin_level=6),
        erweitert um --buffer Meter (Standard 1000 m), damit Umkreis-Auswertungen am
        Stadtrand nicht abgeschnitten werden.
Inhalt: alle Nodes in der Box, alle Ways mit mindestens einem Node in der Box (vollständig,
        inkl. der Nodes außerhalb), alle Relationen mit mindestens einem Mitglied davon.
        Relationen werden nicht rekursiv vervollständigt (Mitglieder außerhalb fehlen).

Aufruf: analysis/.venv/bin/python analysis/extract_dortmund.py [--buffer 1000] [--out PFAD]
"""

import argparse
import math
from pathlib import Path

import osmium

from osm_accessibility_audit import DEFAULT_PBF_SOURCE, find_dortmund

ROOT = Path(__file__).resolve().parent.parent


def main():
  ap = argparse.ArgumentParser()
  ap.add_argument("--pbf", default=str(DEFAULT_PBF_SOURCE))
  ap.add_argument("--buffer", type=float, default=1000.0, help="Puffer um die Box in m")
  ap.add_argument("--out", default=str(ROOT / "dev-data" / "dortmund-260806.osm.pbf"))
  args = ap.parse_args()
  if Path(args.out).exists():
    raise SystemExit(f"{args.out} existiert bereits, wird nicht überschrieben")

  minx, miny, maxx, maxy = find_dortmund(args.pbf).bounds
  dlat = args.buffer / 111_320
  dlon = args.buffer / (111_320 * math.cos(math.radians((miny + maxy) / 2)))
  box = (minx - dlon, miny - dlat, maxx + dlon, maxy + dlat)
  print("Box (lon/lat):", [round(v, 4) for v in box])

  def inside(loc):
    return loc.valid() and box[0] <= loc.lon <= box[2] and box[1] <= loc.lat <= box[3]

  node_ids, way_ids, rel_ids = set(), set(), set()
  with osmium.BackReferenceWriter(args.out, ref_src=args.pbf, remove_tags=False) as writer:
    for o in osmium.FileProcessor(args.pbf).with_locations():
      if o.is_node():
        if inside(o.location):
          node_ids.add(o.id)
          writer.add_node(o)
      elif o.is_way():
        if any(inside(n.location) for n in o.nodes):
          way_ids.add(o.id)
          writer.add_way(o)
      elif o.is_relation():
        sets = {"n": node_ids, "w": way_ids, "r": rel_ids}
        if any(m.ref in sets[m.type] for m in o.members):
          rel_ids.add(o.id)
          writer.add_relation(o)
  print(f"Nodes in Box: {len(node_ids)}, Ways: {len(way_ids)}, Relationen: {len(rel_ids)}")
  print("geschrieben:", args.out)


if __name__ == "__main__":
  main()
