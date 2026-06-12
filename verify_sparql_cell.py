import json, re, sys
sys.stdout.reconfigure(encoding="utf-8")
with open("bgg_sparql_qa.ipynb", encoding="utf-8-sig") as f:
    nb = json.load(f)
for cell in nb["cells"]:
    if cell.get("id") != "c4034405":
        continue
    text = "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"]
    stale = re.findall(r'"Theme [A-Z][^"]+?"', text)
    print("Stale Theme-prefix quotes:", stale if stale else "none")
    print("Stale note removed:", "threnjen-specific themes use a" not in text)
    print("SpiesSecret fixed:", "SpiesSecret" not in text)
    break
