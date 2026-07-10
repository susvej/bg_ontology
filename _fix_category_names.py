"""Fix category/mechanic names in Practice_SPARQL_local.ipynb: snake_case → CamelCase."""
import json

RENAMES = {
    # categories
    "bgg:Party_Game":       "bgg:PartyGame",
    "bgg:Abstract_Strategy":"bgg:AbstractStrategy",
    "bgg:Childrens_Game":   "bgg:ChildrensGame",
    "bgg:Children's_Game":  "bgg:ChildrensGame",
    "bgg:World_War_I":      "bgg:WorldWarI",
    "bgg:World_War_II":     "bgg:WorldWarIi",
    "bgg:Team_Game":        "bgg:TeamBasedGame",
    # mechanics
    "bgg:Card_Drafting":    "bgg:CardDrafting",
    "bgg:Dice_Rolling":     "bgg:DiceRolling",
    "bgg:Solo_Play":        "bgg:SoloSolitaireGame",
    "bgg:Area_Control":     "bgg:AreaControlAreaInfluence",
}

with open("Practice_SPARQL_local.ipynb", encoding="utf-8") as f:
    nb = json.load(f)

total = 0
for cell in nb["cells"]:
    src = "".join(cell["source"])
    for old, new in RENAMES.items():
        count = src.count(old)
        if count:
            src = src.replace(old, new)
            print(f"  {old} -> {new}  ({count}x in cell type={cell['cell_type']})")
            total += count
    cell["source"] = src.splitlines(keepends=True)

with open("Practice_SPARQL_local.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print(f"\nTotal replacements: {total}")
