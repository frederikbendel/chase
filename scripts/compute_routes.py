#!/usr/bin/env python3
"""
compute_routes.py
-----------------
Build-time script that:
  1. Loads SRTM elevation data from a GeoTIFF.
  2. Finds hill peaks within the search radius.
  3. Generates candidate out-and-back waypoints.
  4. Calls the local OpenRouteService instance to obtain real cycling paths
     with accurate elevation profiles.
  5. Ranks every route by the FIETS difficulty score:
         FIETS = (total_ascent_m² / distance_km) × 10
  6. Saves the top N routes to build/routes.json and build/elevation.json.

Usage:
    python compute_routes.py --lat 51.5 --lon 7.0 --radius 80 --top 10

Prerequisites:
    - Local ORS container running on http://localhost:8080
    - build/elevation.tif produced by download_elevation.py
"""

import argparse
import json
import math
import os
import sys
from typing import Any

import numpy as np
import requests
import rasterio
from geopy.distance import geodesic
from scipy.ndimage import maximum_filter, label

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ORS_BASE = "http://localhost:8080/ors/v2/directions/cycling-mountain/geojson"
BUILD_DIR = os.path.join(os.path.dirname(__file__), "..", "build")
DEFAULT_ELEVATION_TIF = os.path.join(BUILD_DIR, "elevation.tif")

# Minimum prominence (metres) for a grid cell to be considered a peak
PEAK_MIN_PROMINENCE = 30
# Neighbourhood size for local-maximum detection (grid cells)
PEAK_NEIGHBOURHOOD = 15
# Number of boundary sample points per candidate direction
BOUNDARY_SAMPLES = 16
# Maximum ORS request retries
ORS_RETRIES = 2


# ---------------------------------------------------------------------------
# Elevation helpers
# ---------------------------------------------------------------------------


def load_elevation(tif_path: str) -> tuple[np.ndarray, Any]:
    """Return (elevation_array, dataset) from a GeoTIFF."""
    ds = rasterio.open(tif_path)
    elev = ds.read(1).astype(float)
    # Replace nodata with NaN
    if ds.nodata is not None:
        elev[elev == ds.nodata] = float("nan")
    return elev, ds


def pixel_to_latlon(ds: Any, row: int, col: int) -> tuple[float, float]:
    x, y = ds.xy(row, col)
    return y, x  # (lat, lon)


def find_peaks(elev: np.ndarray, ds: Any, centre_lat: float, centre_lon: float,
               radius_km: float) -> list[dict]:
    """Detect local elevation peaks within the search circle."""
    neighbourhood = PEAK_NEIGHBOURHOOD
    local_max = maximum_filter(elev, size=neighbourhood)
    peak_mask = (elev == local_max) & (~np.isnan(elev))

    peaks = []
    rows, cols = np.where(peak_mask)
    for r, c in zip(rows, cols):
        lat, lon = pixel_to_latlon(ds, int(r), int(c))
        dist_km = geodesic((centre_lat, centre_lon), (lat, lon)).km
        if dist_km > radius_km:
            continue
        elev_val = float(elev[r, c])
        # Simple prominence check: compare to surrounding mean
        r0 = max(0, r - neighbourhood)
        r1 = min(elev.shape[0], r + neighbourhood + 1)
        c0 = max(0, c - neighbourhood)
        c1 = min(elev.shape[1], c + neighbourhood + 1)
        neighbourhood_mean = float(np.nanmean(elev[r0:r1, c0:c1]))
        prominence = elev_val - neighbourhood_mean
        if prominence >= PEAK_MIN_PROMINENCE:
            peaks.append({
                "lat": lat,
                "lon": lon,
                "elevation": elev_val,
                "prominence": prominence,
                "distance_km": dist_km,
            })

    # Sort by prominence descending, keep distinct peaks (min 2 km apart)
    peaks.sort(key=lambda p: -p["prominence"])
    filtered: list[dict] = []
    for peak in peaks:
        too_close = any(
            geodesic((peak["lat"], peak["lon"]), (p["lat"], p["lon"])).km < 2.0
            for p in filtered
        )
        if not too_close:
            filtered.append(peak)
    return filtered


# ---------------------------------------------------------------------------
# ORS routing helpers
# ---------------------------------------------------------------------------


def ors_route(start_lat: float, start_lon: float,
              waypoints: list[tuple[float, float]]) -> dict | None:
    """
    Call ORS cycling-mountain directions.
    ``waypoints`` is a list of (lat, lon) tuples that the route must pass through.
    Returns the GeoJSON feature dict or None on failure.
    """
    # ORS expects [[lon, lat], …]
    coordinates = [[start_lon, start_lat]] + [[lon, lat] for lat, lon in waypoints]
    # Close the loop back to start
    coordinates.append([start_lon, start_lat])

    payload = {
        "coordinates": coordinates,
        "elevation": True,
        "instructions": False,
    }

    for attempt in range(ORS_RETRIES + 1):
        try:
            resp = requests.post(
                ORS_BASE,
                json=payload,
                timeout=30,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            if features:
                return features[0]
        except requests.RequestException as exc:
            if attempt == ORS_RETRIES:
                print(f"  ORS request failed after {ORS_RETRIES + 1} attempts: {exc}",
                      file=sys.stderr)
            else:
                print(f"  ORS attempt {attempt + 1} failed: {exc} – retrying…",
                      file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# FIETS score
# ---------------------------------------------------------------------------


def fiets_score(total_ascent_m: float, distance_km: float) -> float:
    """
    FIETS difficulty score used by Dutch cycling federations:
        score = ascent_m² / (distance_km × 10)
    Higher is harder / more rewarding.
    """
    if distance_km <= 0:
        return 0.0
    return (total_ascent_m ** 2) / (distance_km * 10.0)


def parse_route(feature: dict) -> dict:
    """Extract distance, total ascent and coordinate list from an ORS GeoJSON feature."""
    props = feature.get("properties", {})
    summary = props.get("summary", {})
    distance_m = summary.get("distance", 0.0)
    distance_km = distance_m / 1000.0

    geometry = feature.get("geometry", {})
    coords = geometry.get("coordinates", [])  # [[lon, lat, ele], …]

    # Calculate total ascent from the coordinate elevations
    total_ascent_m = 0.0
    for i in range(1, len(coords)):
        if len(coords[i]) >= 3 and len(coords[i - 1]) >= 3:
            delta = coords[i][2] - coords[i - 1][2]
            if delta > 0:
                total_ascent_m += delta

    return {
        "distance_km": round(distance_km, 2),
        "total_ascent_m": round(total_ascent_m, 1),
        "coordinates": coords,  # [lon, lat, ele]
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def compute(
    centre_lat: float,
    centre_lon: float,
    radius_km: float,
    top_n: int,
    elevation_tif: str,
) -> None:
    os.makedirs(BUILD_DIR, exist_ok=True)

    # 1. Load elevation data
    print(f"Loading elevation data from {elevation_tif} …")
    elev, ds = load_elevation(elevation_tif)

    # 2. Find peaks
    print("Finding hill peaks …")
    peaks = find_peaks(elev, ds, centre_lat, centre_lon, radius_km)
    print(f"  Found {len(peaks)} candidate peaks.")
    ds.close()

    if not peaks:
        print("No peaks found – check your elevation file and radius.", file=sys.stderr)
        sys.exit(1)

    # 3. Generate candidate routes (out-and-back through each peak)
    routes_raw: list[dict] = []
    for idx, peak in enumerate(peaks[:40]):  # limit API calls
        print(
            f"  Routing via peak {idx + 1}/{min(len(peaks), 40)}: "
            f"({peak['lat']:.4f}, {peak['lon']:.4f}) "
            f"elev={peak['elevation']:.0f} m"
        )
        feature = ors_route(
            centre_lat, centre_lon,
            [(peak["lat"], peak["lon"])],
        )
        if feature is None:
            continue

        info = parse_route(feature)
        if info["distance_km"] <= 0:
            continue

        score = fiets_score(info["total_ascent_m"], info["distance_km"])
        routes_raw.append({
            "id": idx + 1,
            "peak_lat": peak["lat"],
            "peak_lon": peak["lon"],
            "peak_elevation_m": round(peak["elevation"], 1),
            "peak_prominence_m": round(peak["prominence"], 1),
            "distance_km": info["distance_km"],
            "total_ascent_m": info["total_ascent_m"],
            "fiets_score": round(score, 2),
            "coordinates": info["coordinates"],
        })

    if not routes_raw:
        print("No routable peaks found. Is ORS running?", file=sys.stderr)
        sys.exit(1)

    # 4. Rank by FIETS score
    routes_raw.sort(key=lambda r: -r["fiets_score"])
    top_routes = routes_raw[:top_n]

    # Re-number after ranking
    for rank, route in enumerate(top_routes, 1):
        route["rank"] = rank

    # 5. Split into routes.json (metadata) and elevation.json (profiles)
    routes_meta = []
    elevation_profiles: dict[str, list] = {}

    for route in top_routes:
        coords = route.pop("coordinates")
        routes_meta.append(route)

        # Build elevation profile: list of {distance_km, elevation_m}
        profile: list[dict] = []
        cumulative_dist = 0.0
        prev = coords[0] if coords else None
        for pt in coords:
            if prev is not None and pt != prev:
                seg_m = geodesic(
                    (prev[1], prev[0]),  # (lat, lon)
                    (pt[1], pt[0]),
                ).m
                cumulative_dist += seg_m / 1000.0
            ele = pt[2] if len(pt) >= 3 else 0
            profile.append({"d": round(cumulative_dist, 3), "e": round(ele, 1)})
            prev = pt

        elevation_profiles[str(route["rank"])] = {
            "coordinates": coords,
            "profile": profile,
        }

    # 6. Write output files
    routes_path = os.path.join(BUILD_DIR, "routes.json")
    elevation_path = os.path.join(BUILD_DIR, "elevation.json")

    with open(routes_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "centre": {"lat": centre_lat, "lon": centre_lon},
                "radius_km": radius_km,
                "routes": routes_meta,
            },
            f,
            indent=2,
        )
    print(f"Routes saved to {routes_path}")

    with open(elevation_path, "w", encoding="utf-8") as f:
        json.dump(elevation_profiles, f, indent=2)
    print(f"Elevation profiles saved to {elevation_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute and rank cycling routes")
    parser.add_argument("--lat", type=float, required=True, help="Start latitude")
    parser.add_argument("--lon", type=float, required=True, help="Start longitude")
    parser.add_argument(
        "--radius",
        type=float,
        default=80.0,
        help="Search radius in km (default: 80)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of top routes to save (default: 10)",
    )
    parser.add_argument(
        "--elevation-tif",
        type=str,
        default=DEFAULT_ELEVATION_TIF,
        help="Path to the SRTM elevation GeoTIFF",
    )
    args = parser.parse_args()
    compute(args.lat, args.lon, args.radius, args.top, args.elevation_tif)


if __name__ == "__main__":
    main()
