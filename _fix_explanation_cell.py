"""Insert the About-the-data explanation cell into Practice_SPARQL_local.ipynb."""
import json

EXPLANATION = """\
## About the data

This notebook works with two TTL files that together form the knowledge graph:

---

### bgg_main.ttl — real data only

Everything in this file comes directly from [BoardGameGeek](https://boardgamegeek.com/). It contains:

- **~126,000 triples** covering ~21,000 board games
- The **ontology** (T-Box): classes like `bgg:Game`, `bgg:Creator`, `bgg:Mechanic`, `bgg:Category`, \
`bgg:PlayerOpinion`; and properties like `bgg:hasName`, `bgg:hasGeekRating`, `bgg:hasCreator`, \
`bgg:hasMechanic`
- The **game instances** (A-Box): one `bgg:Game` individual per game, \
e.g. `bgg:174430` is *Gloomhaven*, `bgg:9209` is *Catan*
- Designer, expansion, and reimplementation data

---

### fake_players.ttl — synthetic data, kept separate

BoardGameGeek does not publish individual player data. To practice queries about **ownership** and \
**personal ratings**, this file contains 200 fictional players with invented game collections and \
opinions.

It is kept as a separate file — **not merged into bgg_main.ttl** — so the real BGG data stays clean \
and unmodified. Loading it is opt-in.

---

### Namespace prefixes

| Prefix | URI | Used for |
|--------|-----|---------|
| `bgg:` | `https://raw.githubusercontent.com/susvej/bg_ontology/` | Everything: classes, properties, game instances, mechanic/category/mentalload values |
| `fake:` | `https://vejdemo.se/boardgames/fake#` | Fake player individuals (`fake:AkikoDupont`) and opinion nodes (`fake:AkikoDupont_opinion_174430`) |
| `rdf:` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` | `rdf:type`, `rdf:Property` |
| `rdfs:` | `http://www.w3.org/2000/01/rdf-schema#` | `rdfs:label`, `rdfs:subClassOf` |
| `owl:` | `http://www.w3.org/2002/07/owl#` | `owl:Class`, `owl:ObjectProperty`, etc. |
| `xsd:` | `http://www.w3.org/2001/XMLSchema#` | Datatypes: `xsd:integer`, `xsd:decimal`, `xsd:string` |

All SPARQL queries in this notebook include these prefix declarations at the top.\
"""

with open("Practice_SPARQL_local.ipynb", encoding="utf-8") as f:
    nb = json.load(f)

# Replace cell 1 with the corrected explanation
nb["cells"][1] = {
    "cell_type": "markdown",
    "metadata": {},
    "source": EXPLANATION.splitlines(keepends=True),
}

with open("Practice_SPARQL_local.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print(f"Done. Cell 1 is now {len(nb['cells'][1]['source'])} lines.")
