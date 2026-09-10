"""
Step 2: turn the prepared dataframe (from 1_prep.py) into the compact JSON
blob the dashboard embeds - one record per listing plus simplified district
boundaries as GeoJSON.
"""
import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import numpy as np
from shapely.geometry import mapping

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")

resid = pd.read_pickle(os.path.join(BUILD, "resid.pkl"))
districts_raw = pd.read_pickle(os.path.join(BUILD, "districts.pkl"))

resid = resid[resid['district'].notna()].copy()  # drop listings outside the 8 known districts (was "Пригород/другое")

cat_ru = {'kvartiry':'Квартира','komnaty':'Комната','doma-dachi':'Дом/дача'}
resid['category_ru'] = resid['category_alias'].map(cat_ru)

def wc_bucket(v):
    s = str(v).lower()
    if 'раздел' in s: return 'Раздельный'
    if 'совмещ' in s: return 'Совмещённый'
    return None

def clean(v):
    if pd.isna(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        if np.isnan(v): return None
        return round(float(v), 6)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v

records = []
for _, r in resid.iterrows():
    records.append({
        'id': int(r['source_id']),
        'cat': r['category_ru'],
        'district': r['district'],
        'dconf': bool(r['district_confirmed']),
        'addr': str(r['full_address']).replace('Алматы, ', '', 1),
        'lat': clean(r['lat']),
        'lon': clean(r['lon']),
        'price': int(r['price']),
        'pm2': clean(r['price_m2']),
        'rooms': clean(r['rooms']),
        'area': clean(r['area']),
        'floor': clean(r['floor']),
        'floorT': clean(r['floor_total']),
        'owner': r['owner_type'] if pd.notna(r['owner_type']) else None,
        'furn': bool(r['furnished']),
        'pets': bool(r['pets_ok']),
        'kids': bool(r['kids_ok']),
        'nosmk': bool(r['non_smoking']),
        'balc': bool(r['balcony']),
        'wcType': wc_bucket(r['bathroom_type']) if pd.notna(r['bathroom_type']) else None,
        'created': str(r['created_at'])[:10],
        'houseType': ('Часть дома' if 'Часть дома' in str(r['title']) else ('Отдельный дом' if 'Отдельный дом' in str(r['title']) else None)) if r['category_alias']=='doma-dachi' else None,
    })

print("records:", len(records))

# district geojson (simplified)
features = []
for _, row in districts_raw.iterrows():
    geom = row['geom'].simplify(0.0008, preserve_topology=True)
    features.append({
        'type': 'Feature',
        'properties': {'name': row['name_ru']},
        'geometry': mapping(geom)
    })
geojson = {'type': 'FeatureCollection', 'features': features}

out = {'records': records, 'districts_geo': geojson}
out_path = os.path.join(BUILD, "data.json")
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

size = os.path.getsize(out_path)
print("JSON size bytes:", size, "=", round(size/1024/1024,2), "MB")

# quick aggregate sanity
df = pd.DataFrame(records)
print()
print(df.groupby('district')['price'].agg(['count','mean','median']).sort_values('count', ascending=False))
print()
print(df.groupby('cat')['price'].agg(['count','mean','median']))
