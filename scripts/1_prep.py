"""
Step 1: load raw krisha.kz export + district reference, filter to residential
rental only, derive district/rooms/area/floor/amenity fields.
Run from anywhere; paths are resolved relative to this file's location
(expects the raw .xlsx files one level up, in the "аренда" folder).
"""
import sys, io, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
from shapely import wkb
from shapely.geometry import Point

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)              # ...\аренда
BUILD = os.path.join(HERE, "build")       # ...\аренда\scripts\build
os.makedirs(BUILD, exist_ok=True)

ads = pd.read_excel(os.path.join(BASE, "Крыша", "krisha_ads_1.xlsx"), sheet_name="Result 1")
params = pd.read_excel(os.path.join(BASE, "Крыша", "krisha_ad_parameters_1.xlsx"), sheet_name="Result 1")
districts_raw = pd.read_excel(os.path.join(BASE, "address_city_districts.xlsx"), sheet_name="Result 1")

# ---- filter: residential rental only ----
resid = ads[(ads['section_alias']=='arenda') & (ads['category_alias'].isin(['kvartiry','komnaty','doma-dachi']))].copy()
print("Residential rental rows:", len(resid))

# ---- district polygons ----
districts_raw = districts_raw[districts_raw['id'] != 0].copy()  # drop city-level row
districts_raw['geom'] = districts_raw['geometry'].apply(lambda h: wkb.loads(bytes.fromhex(h)))

# ---- extract district from full_address text: "...XXX р-н..." -> "XXX район" ----
def extract_district_text(addr):
    m = re.search(r'([А-Яа-яЁё]+)\s+р-н', str(addr))
    return (m.group(1) + ' район') if m else None

resid['district'] = resid['full_address'].apply(extract_district_text)
missing_mask = resid['district'].isna()
print("Missing district from text:", missing_mask.sum())

# geo fallback for missing: point-in-polygon against the real district boundaries
if missing_mask.sum() > 0:
    def geo_lookup(row):
        pt = Point(row['lon'], row['lat'])
        for _, drow in districts_raw.iterrows():
            if drow['geom'].contains(pt):
                return drow['name_ru']
        return None
    resid.loc[missing_mask, 'district'] = resid.loc[missing_mask].apply(geo_lookup, axis=1)

print("Still missing district after geo fallback:", resid['district'].isna().sum())
print(resid['district'].value_counts(dropna=False))

# ---- parse title: rooms, area, floor ----
def parse_title(title, cat):
    rooms = area = floor = floor_total = None
    if cat == 'kvartiry':
        m = re.search(r'(\d+)-комнатная', title)
        if m: rooms = int(m.group(1))
        elif 'студия' in title.lower(): rooms = 0
    else:
        m = re.search(r'(\d+)\s+комнат', title)
        if m: rooms = int(m.group(1))
    m = re.search(r'([\d.]+)\s*м²', title)
    if m: area = float(m.group(1))
    m = re.search(r'(\d+)/(\d+)\s*этаж', title)
    if m:
        floor = int(m.group(1)); floor_total = int(m.group(2))
    else:
        m = re.search(r'(\d+)\s*этаж', title)
        if m: floor = int(m.group(1))
    return pd.Series([rooms, area, floor, floor_total])

resid[['rooms','area','floor','floor_total']] = resid.apply(lambda r: parse_title(str(r['title']), r['category_alias']), axis=1)

print()
print("rooms nulls:", resid['rooms'].isna().sum(), "/", len(resid))
print("area nulls:", resid['area'].isna().sum())
print("floor nulls (kvartiry+komnaty):", resid[resid.category_alias.isin(['kvartiry','komnaty'])]['floor'].isna().sum())

# ---- owner type ----
resid['owner_type'] = resid['owner_title'].apply(lambda x: 'Хозяин' if x=='Хозяин' else ('Агентство' if pd.notna(x) else None))
print()
print(resid['owner_type'].value_counts(dropna=False))

# ---- params pivot for filters ----
resid_ids = set(resid['source_id'])
p = params[params['ad_id'].isin(resid_ids)]

def agg_param(name):
    return p[p['name']==name].groupby('ad_id')['value'].first()

furniture = agg_param('Мебель')
furnished_flag = agg_param('Квартира меблирована')
suitable = agg_param('Кому подойдет квартира')
balcony = agg_param('Балкон')
bathroom = agg_param('Санузел')

resid = resid.set_index('source_id')
resid['furnished'] = resid.index.map(lambda i: (i in furniture.index) or (i in furnished_flag.index))
resid['pets_ok'] = resid.index.map(lambda i: 'можно с животными' in str(suitable.get(i,'')))
resid['kids_ok'] = resid.index.map(lambda i: 'можно с детьми' in str(suitable.get(i,'')))
resid['non_smoking'] = resid.index.map(lambda i: 'некурящим' in str(suitable.get(i,'')))
resid['balcony'] = resid.index.map(lambda i: str(balcony.get(i,'')).strip() not in ('', 'нет', 'nan'))
resid['bathroom_type'] = resid.index.map(lambda i: bathroom.get(i, None))
resid = resid.reset_index()

print()
print("furnished:", resid['furnished'].sum())
print("pets_ok:", resid['pets_ok'].sum())
print("kids_ok:", resid['kids_ok'].sum())
print("non_smoking:", resid['non_smoking'].sum())
print("balcony:", resid['balcony'].sum())

# ---- price sanity check (outliers are kept, just reported) ----
print()
print("price describe:")
print(resid['price'].describe())
print("price > 5,000,000 count:", (resid['price']>5_000_000).sum())
print("price < 20,000 count:", (resid['price']<20_000).sum())

resid.to_pickle(os.path.join(BUILD, "resid.pkl"))
districts_raw.to_pickle(os.path.join(BUILD, "districts.pkl"))
print("\nSaved pickles to", BUILD)
