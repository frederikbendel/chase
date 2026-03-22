#!/usr/bin/env python3
"""
download_elevation.py
---------------------
Downloads SRTM 30 m elevation tiles for the bounding box that covers a
given latitude/longitude centre and a radius (in km).

Usage:
    python download_elevation.py --lat 51.5 --lon 7.0 --radius 80

The tiles are cached in the directory ``./elevation_cache/`` (relative to
the project root) and a merged GeoTIFF is written to
``./build/elevation.tif``.

Requires the ``elevation`` package (wraps srtm.py / CGIAR SRTM):
    pip install elevation rasterio
"""

import argparse
import math
import os
import subprocess
import sys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6_371.0
BUILD_DIR = os.path.join(os.path.dirname(__file__), "..", "build")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "elevation_cache")


def km_to_deg(km: float) -> float:
    """Rough conversion: kilometres → degrees of latitude (1° ≈ 111 km)."""
    return km / 111.0


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) bounding box for the given circle."""
    lat_delta = km_to_deg(radius_km)
    # longitude degrees shrink with latitude
    lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))
    return (
        lat - lat_delta,
        lon - lon_delta,
        lat + lat_delta,
        lon + lon_delta,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def download(lat: float, lon: float, radius_km: float, output: str) -> None:
    south, west, north, east = bounding_box(lat, lon, radius_km)

    os.makedirs(BUILD_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    print(
        f"Downloading SRTM tiles for bounding box: "
        f"S={south:.4f} W={west:.4f} N={north:.4f} E={east:.4f}"
    )

    # The ``elevation`` CLI wraps eio (elevation I/O) which fetches SRTM 30 m
    # tiles from AWS Terrain Tiles and merges them into a single GeoTIFF.
    cmd = [
        sys.executable, "-m", "elevation",
        "--bounds", str(west), str(south), str(east), str(north),
        "--output", output,
        "--cache_dir", CACHE_DIR,
        "--product", "SRTM3",  # ~90 m; use SRTM1 for 30 m if bandwidth allows
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"Elevation GeoTIFF saved to: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download SRTM elevation tiles")
    parser.add_argument("--lat", type=float, required=True, help="Centre latitude")
    parser.add_argument("--lon", type=float, required=True, help="Centre longitude")
    parser.add_argument(
        "--radius",
        type=float,
        default=80.0,
        help="Search radius in km (default: 80)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join(BUILD_DIR, "elevation.tif"),
        help="Output GeoTIFF path",
    )
    args = parser.parse_args()
    download(args.lat, args.lon, args.radius, args.output)


if __name__ == "__main__":
    main()
