"""Fix the game count in the explanation cell."""
import json

with open("Practice_SPARQL_local.ipynb", encoding="utf-8") as f:
    nb = json.load(f)

OLD = "- **~33,000 games (over 700,000 triples)** covering ~21,000 board games"
NEW = "- **~33,750 board games** (run the load cell to see the exact triple count)"

cell = nb["cells"][1]
src = "".join(cell["source"])
assert OLD in src, f"Pattern not found:\n{src[:300]}"
cell["source"] = src.replace(OLD, NEW).splitlines(keepends=True)

with open("Practice_SPARQL_local.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print("Fixed.")
