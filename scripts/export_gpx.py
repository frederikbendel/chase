#!/usr/bin/env python3
"""
export_gpx.py
-------------
Converts the high-resolution route coordinates stored in build/elevation.json
into individual GPX files written to build/gpx/.

Usage:
    python export_gpx.py                     # export all routes
    python export_gpx.py --route 1           # export a single route by rank
    python export_gpx.py --input /path/to/elevation.json --output /path/to/gpx/

Each GPX file contains:
  - A <trk>/<trkseg> with one <trkpt> per coordinate, including elevation.
  - A route name derived from the rank and peak elevation (read from routes.json).
"""

import argparse
import json
import os
from datetime import datetime, timezone

import gpxpy
import gpxpy.gpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BUILD_DIR = os.path.join(os.path.dirname(__file__), "..", "build")
DEFAULT_ELEVATION_JSON = os.path.join(BUILD_DIR, "elevation.json")
DEFAULT_ROUTES_JSON = os.path.join(BUILD_DIR, "routes.json")
DEFAULT_GPX_DIR = os.path.join(BUILD_DIR, "gpx")


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def load_route_metadata(routes_path: str) -> dict[str, dict]:
    """Return a mapping of str(rank) → route metadata dict."""
    if not os.path.isfile(routes_path):
        return {}
    with open(routes_path, encoding="utf-8") as f:
        data = json.load(f)
    return {str(r["rank"]): r for r in data.get("routes", [])}


def coords_to_gpx(
    rank: str,
    coordinates: list,
    metadata: dict,
    created_at: datetime,
) -> gpxpy.gpx.GPX:
    """Build a gpxpy.gpx.GPX object from a coordinate list."""
    gpx = gpxpy.gpx.GPX()
    gpx.creator = "Chase Wildcard Route Optimizer"

    # Metadata
    peak_elev = metadata.get("peak_elevation_m", "?")
    distance = metadata.get("distance_km", "?")
    ascent = metadata.get("total_ascent_m", "?")
    fiets = metadata.get("fiets_score", "?")

    name = (
        f"Chase Route #{rank} – "
        f"Peak {peak_elev} m | {distance} km | ↑{ascent} m | FIETS {fiets}"
    )

    track = gpxpy.gpx.GPXTrack(name=name)
    track.description = (
        f"Rank #{rank} | Distance: {distance} km | "
        f"Total Ascent: {ascent} m | FIETS Score: {fiets}"
    )
    track.type = "cycling"
    gpx.tracks.append(track)

    segment = gpxpy.gpx.GPXTrackSegment()
    track.segments.append(segment)

    for pt in coordinates:
        lon, lat = pt[0], pt[1]
        ele = pt[2] if len(pt) >= 3 else None
        trkpt = gpxpy.gpx.GPXTrackPoint(
            latitude=lat,
            longitude=lon,
            elevation=ele,
            time=None,
        )
        segment.points.append(trkpt)

    return gpx


def export_routes(
    elevation_path: str,
    routes_path: str,
    gpx_dir: str,
    filter_rank: int | None = None,
) -> None:
    os.makedirs(gpx_dir, exist_ok=True)

    with open(elevation_path, encoding="utf-8") as f:
        elevation_data: dict = json.load(f)

    meta_map = load_route_metadata(routes_path)
    created_at = datetime.now(tz=timezone.utc)

    exported = 0
    for rank_str, route_data in elevation_data.items():
        if filter_rank is not None and int(rank_str) != filter_rank:
            continue

        coords = route_data.get("coordinates", [])
        if not coords:
            print(f"  Route #{rank_str}: no coordinates, skipping.")
            continue

        metadata = meta_map.get(rank_str, {})
        gpx = coords_to_gpx(rank_str, coords, metadata, created_at)

        out_path = os.path.join(gpx_dir, f"route_{rank_str.zfill(2)}.gpx")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(gpx.to_xml())

        print(f"  Exported route #{rank_str} → {out_path}")
        exported += 1

    print(f"Done. {exported} GPX file(s) written to {gpx_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Export routes to GPX files")
    parser.add_argument(
        "--input",
        type=str,
        default=DEFAULT_ELEVATION_JSON,
        help="Path to elevation.json",
    )
    parser.add_argument(
        "--routes",
        type=str,
        default=DEFAULT_ROUTES_JSON,
        help="Path to routes.json (for metadata)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_GPX_DIR,
        help="Output directory for GPX files",
    )
    parser.add_argument(
        "--route",
        type=int,
        default=None,
        help="Export only the route with this rank number",
    )
    args = parser.parse_args()
    export_routes(args.input, args.routes, args.output, args.route)


if __name__ == "__main__":
    main()
