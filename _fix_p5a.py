"""Fix P5a query (non-pirate games) and update triple count in explanation cell."""
import json

with open("Practice_SPARQL_local.ipynb", encoding="utf-8") as f:
    nb = json.load(f)

fixes = 0
for cell in nb["cells"]:
    src = "".join(cell["source"])

    # Fix P5a: hasMinPlayers -> hasMaxPlayers, variable name + filter
    if "P5a" in src and "hasMinPlayers" in src:
        src = src.replace(
            "bgg:hasMinPlayers ?minplayers .\n        FILTER(?minplayers > 2",
            "bgg:hasMaxPlayers ?maxplayers .\n        FILTER(?maxplayers > 2",
        )
        cell["source"] = src.splitlines(keepends=True)
        fixes += 1
        print("Fixed P5a query")

    # Update triple count in explanation cell
    if "~126,000 triples" in src:
        src = src.replace("~126,000 triples", "~33,000 games (over 700,000 triples)")
        cell["source"] = src.splitlines(keepends=True)
        fixes += 1
        print("Updated triple count in explanation")

with open("Practice_SPARQL_local.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print(f"Done. {fixes} fixes applied.")
