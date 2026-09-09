"""
Step 3: splice build/data.json into dashboard_template.html and write the
final, self-contained dashboard to the аренда folder.
"""
import io, os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build")

with io.open(os.path.join(HERE, "dashboard_template.html"), "r", encoding="utf-8") as f:
    tpl = f.read()
with io.open(os.path.join(BUILD, "data.json"), "r", encoding="utf-8") as f:
    data = f.read()

out = tpl.replace("__DATA_JSON__", data)
out_path = os.path.join(BASE, "almaty_rent_dashboard.html")
with io.open(out_path, "w", encoding="utf-8") as f:
    f.write(out)

print("Wrote", out_path, "-", round(len(out.encode("utf-8"))/1024/1024, 2), "MB")
