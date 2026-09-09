"""
Step 2b (optional, needs internet + run once): fetch a real OpenStreetMap
basemap covering the dashboard's area and merge it into build/data.json as a
single embedded raster image (base64 data URI + its exact lat/lon bounds).

Why a raster fetched at build time instead of live map tiles: the published
Artifact runs in a sandbox whose CSP allows scripts only from a short CDN
allowlist and blocks image/network requests to everything else (including
tile.openstreetmap.org) - so a normal Leaflet/slippy map would render blank
tiles. Fetching the tiles once here and embedding the stitched result as a
data: URI sidesteps that entirely; the dashboard just drawImage()s it under
the district polygons and points.

Respects OSM's tile usage policy: this is a one-off, moderate (~150 tile)
fetch with a descriptive User-Agent and a delay between requests - not
something that runs per viewer. If you rerun this often, consider caching
build/basemap.jpg instead of re-fetching.
"""
import io, os, json, math, time
import urllib.request
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")

with io.open(os.path.join(BUILD, "data.json"), "r", encoding="utf-8") as f:
    d = json.load(f)

recs = [r for r in d["records"] if 42.8 <= r["lat"] <= 43.65 and 76.3 <= r["lon"] <= 77.7]
lats = [r["lat"] for r in recs]; lons = [r["lon"] for r in recs]

def flatten(geom):
    pts = []
    if geom["type"] == "Polygon":
        for ring in geom["coordinates"]: pts.extend(ring)
    else:
        for poly in geom["coordinates"]:
            for ring in poly: pts.extend(ring)
    return pts

for feat in d["districts_geo"]["features"]:
    for p in flatten(feat["geometry"]):
        lons.append(p[0]); lats.append(p[1])

latMin, latMax = min(lats), max(lats)
lonMin, lonMax = min(lons), max(lons)
padLat = (latMax - latMin) * 0.06
padLon = (lonMax - lonMin) * 0.06
latMin -= padLat; latMax += padLat; lonMin -= padLon; lonMax += padLon
print("bbox:", latMin, latMax, lonMin, lonMax)

ZOOM = 12

def lon_to_x(lon, z): return (lon + 180.0) / 360.0 * (2**z)
def lat_to_y(lat, z):
    rad = math.radians(lat)
    return (1.0 - math.log(math.tan(rad) + 1.0/math.cos(rad)) / math.pi) / 2.0 * (2**z)

xMinF, xMaxF = lon_to_x(lonMin, ZOOM), lon_to_x(lonMax, ZOOM)
yMinF, yMaxF = lat_to_y(latMax, ZOOM), lat_to_y(latMin, ZOOM)  # y grows southward

xTileMin, xTileMax = math.floor(xMinF), math.floor(xMaxF)
yTileMin, yTileMax = math.floor(yMinF), math.floor(yMaxF)
nx = xTileMax - xTileMin + 1
ny = yTileMax - yTileMin + 1
print("tile grid:", nx, "x", ny, "=", nx*ny, "tiles")

TS = 256
canvas = Image.new("RGB", (nx*TS, ny*TS), (240,240,236))
HEADERS = {"User-Agent": "AlmatyRentalDashboardBuild/1.0 (one-time build-time basemap tile fetch for a private analytics dashboard)"}
opener = urllib.request.build_opener()

for j, ty in enumerate(range(yTileMin, yTileMax+1)):
    for i, tx in enumerate(range(xTileMin, xTileMax+1)):
        url = f"https://tile.openstreetmap.org/{ZOOM}/{tx}/{ty}.png"
        req = urllib.request.Request(url, headers=HEADERS)
        raw = None
        for attempt in range(3):
            try:
                with opener.open(req, timeout=10) as resp:
                    raw = resp.read()
                break
            except Exception as e:
                print("retry", tx, ty, e)
                time.sleep(0.5)
        if raw:
            canvas.paste(Image.open(io.BytesIO(raw)).convert("RGB"), (i*TS, j*TS))
        time.sleep(0.15)
print("fetched grid")

px0, px1 = (xMinF - xTileMin) * TS, (xMaxF - xTileMin) * TS
py0, py1 = (yMinF - yTileMin) * TS, (yMaxF - yTileMin) * TS
crop = canvas.crop((int(px0), int(py0), int(px1), int(py1)))

MAXW = 1600
if crop.width > MAXW:
    ratio = MAXW / crop.width
    crop = crop.resize((MAXW, int(crop.height*ratio)), Image.LANCZOS)
print("final size:", crop.size)

buf = io.BytesIO()
crop.save(buf, "JPEG", quality=82, optimize=True)
jpg_bytes = buf.getvalue()
print("jpeg size KB:", len(jpg_bytes)/1024)

import base64
uri = "data:image/jpeg;base64," + base64.b64encode(jpg_bytes).decode("ascii")

d["basemap"] = {
    "bounds": {"latMin": latMin, "latMax": latMax, "lonMin": lonMin, "lonMax": lonMax},
    "uri": uri,
}
with io.open(os.path.join(BUILD, "data.json"), "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, separators=(",", ":"))

print("merged basemap into build/data.json, new size MB:",
      os.path.getsize(os.path.join(BUILD, "data.json"))/1024/1024)
