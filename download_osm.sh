#!/usr/bin/env bash
# Download OpenStreetMap data for North Rhine-Westphalia from Geofabrik
# into the ./docker/data folder expected by the ORS container.

set -euo pipefail

DEST_DIR="$(dirname "$0")/docker/data"
FILE="nordrhein-westfalen-latest.osm.pbf"
URL="https://download.geofabrik.de/europe/germany/nordrhein-westfalen-latest.osm.pbf"

mkdir -p "$DEST_DIR"

echo "Downloading $FILE → $DEST_DIR ..."
wget --progress=bar:force:noscroll -O "$DEST_DIR/$FILE" "$URL"
echo "Done. File saved to $DEST_DIR/$FILE"
