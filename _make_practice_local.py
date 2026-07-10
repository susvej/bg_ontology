"""Generate Practice_SPARQL_local.ipynb — VS Code-friendly version."""
import json, os

PFX = """    PREFIX bgg: <https://raw.githubusercontent.com/susvej/bg_ontology/>
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>"""

def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src.splitlines(keepends=True)}

def code(src):
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": src.splitlines(keepends=True)}

cells = [

md("""\
# Practice SPARQL with the Boardgame Knowledge Graph

This notebook loads `bgg_main.ttl` from your local copy of the repository into an \
in-memory rdflib graph, then lets you practice SPARQL queries against it.

**First-time load takes ~60 seconds** (parsing 28 MB / ~126k triples). \
After that, all queries run locally — no internet required.

Run the three setup cells first, then work through the practice problems in any order.\
"""),

code("""\
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL
from rdflib.plugins.sparql import prepareQuery
import pandas as pd
import os

print("Imports ok.")\
"""),

code("""\
# Load the graph from the local TTL file (same folder as this notebook)
g = Graph()

ttl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bgg_main.ttl")
print(f"Loading {ttl_path} ...")
g.parse(ttl_path, format="ttl")

bgg = Namespace("https://raw.githubusercontent.com/susvej/bg_ontology/")
g.namespace_manager.bind("bgg", bgg, override=True)

print(f"Done. Graph has {len(g):,} triples.")\
"""),

code("""\
# Explore schema: classes and properties
qname = g.qname

print("CLASSES:")
for s in sorted(g.subjects(RDF.type, OWL.Class), key=str):
    try: print(" -", qname(s))
    except: pass

print("\\nOBJECT PROPERTIES:")
for p in sorted(g.subjects(RDF.type, OWL.ObjectProperty), key=str):
    dom = [qname(d) for d in g.objects(p, RDFS.domain)]
    ran = [qname(r) for r in g.objects(p, RDFS.range)]
    print(f"  {qname(p)}  domain={dom}  range={ran}")

print("\\nDATATYPE PROPERTIES:")
for p in sorted(g.subjects(RDF.type, OWL.DatatypeProperty), key=str):
    ran = [qname(r) for r in g.objects(p, RDFS.range)]
    print(f"  {qname(p)}  range={ran}")\
"""),

code("""\
# Explore all Category and Mechanic instances
print("MECHANICS:")
for s in sorted(g.subjects(RDF.type, bgg.Mechanic), key=str):
    print(" -", qname(s))

print("\\nCATEGORIES:")
for s in sorted(g.subjects(RDF.type, bgg.Category), key=str):
    print(" -", qname(s))\
"""),

code("""\
# Helper: show SPARQL results as a pandas table
def pretty(results):
    data = [{str(k): str(v) for k, v in row.asdict().items()} for row in results]
    return pd.DataFrame(data)

print("pretty() ready.")\
"""),

md("---\n# Practice problems\n\nRun the cells in order the first time. Some later cells depend on data inserted by earlier ones."),

# P1
code("""\
# P1: Show 10 party games
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name WHERE {
        ?game bgg:hasCategory bgg:Party_Game ;
              bgg:hasName ?name .
    }
    ORDER BY ?name
    LIMIT 10
\"\"\")
pretty(g.query(myquery))\
"""),

# P2
code("""\
# P2: 10 games with Geek Rating above 7.0, highest first
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name ?rating WHERE {
        ?game bgg:hasGeekRating ?rating ;
              bgg:hasName ?name .
        FILTER(?rating > 7.0)
    }
    ORDER BY DESC(?rating)
    LIMIT 10
\"\"\")
pretty(g.query(myquery))\
"""),

# P3
code("""\
# P3: Count party games with Geek Rating above 7.0
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (COUNT(?game) AS ?count) WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasGeekRating ?rating ;
              bgg:hasCategory bgg:Party_Game .
        FILTER(?rating > 7)
    }
\"\"\")
pretty(g.query(myquery))\
"""),

# P4
code("""\
# P4: Games suitable for 3 to 8 players
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name ?minplay ?maxplay WHERE {
        ?game bgg:hasName ?name ;
              bgg:hasMinPlayers ?minplay ;
              bgg:hasMaxPlayers ?maxplay .
        FILTER(?minplay > 2 && ?maxplay < 8 && ?maxplay > 2)
    }
\"\"\")
pretty(g.query(myquery))\
"""),

# P5a
code("""\
# P5a: Count games for more than 2 players without "pirate" in the title
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (COUNT(?name) AS ?nonpirategames) WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasName ?name ;
              bgg:hasMinPlayers ?minplayers .
        FILTER(?minplayers > 2 && !regex(?name, "pirate", "i"))
    }
\"\"\")
pretty(g.query(myquery))\
"""),

# P5b
code("""\
# P5b: 5 games with Card Drafting mechanic in Fantasy category, Z to A
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name WHERE {
        ?game bgg:hasName ?name ;
              bgg:hasMechanic bgg:Card_Drafting ;
              bgg:hasCategory bgg:Fantasy .
    }
    ORDER BY DESC(?name)
    LIMIT 5
\"\"\")
pretty(g.query(myquery))\
"""),

# P6
code("""\
# P6: Card games 2 people can play in under 30 minutes
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (?name AS ?GameName) (?maxtime AS ?GameTime) WHERE {
        ?game bgg:hasName ?name ;
              bgg:hasMinPlayers 2 ;
              bgg:hasMaxGameTime ?maxtime .
        FILTER(?maxtime <= 30)
    }
    ORDER BY ?name
    LIMIT 10
\"\"\")
pretty(g.query(myquery))\
"""),

# P7
code("""\
# P7: Games that do NOT have a playtime specified (FILTER NOT EXISTS)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasName ?name .
        FILTER NOT EXISTS { ?game bgg:hasMaxGameTime ?t }
    }
    LIMIT 50
\"\"\")
pretty(g.query(myquery))\
"""),

# P8
code("""\
# P8: SELECT games rated above 7.5
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name ?rating WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasName ?name ;
              bgg:hasGeekRating ?rating .
        FILTER(?rating > 7.5)
    }
    ORDER BY DESC(?rating)
    LIMIT 20
\"\"\")
pretty(g.query(myquery))\
"""),

# P8 insert
code("""\
# P8 INSERT: add bgg:hasQuality bgg:High_Quality to all games rated above 7.5
g.update(\"\"\"
""" + PFX + """
    INSERT {
        bgg:High_Quality rdf:type rdfs:Class .
        ?game bgg:hasQuality bgg:High_Quality .
    } WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasGeekRating ?rating .
        FILTER(?rating > 7.5)
    }
\"\"\")
print("Insert done.")\
"""),

# P8 verify
code("""\
# P8 verify: query the newly inserted quality data
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name ?quality WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasName ?name ;
              bgg:hasQuality ?quality .
    }
    LIMIT 20
\"\"\")
pretty(g.query(myquery))\
"""),

# P9
code("""\
# P9: MIN and MAX geek rating across all games
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (MAX(?rating) AS ?maxrating) (MIN(?rating) AS ?minrating) WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasGeekRating ?rating .
    }
\"\"\")
pretty(g.query(myquery))\
"""),

# P10
code("""\
# P10: Name of the highest AND lowest rated games (subqueries + UNION)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name ?rating WHERE {
        {
            { SELECT (MAX(?r) AS ?target) WHERE { ?g bgg:hasGeekRating ?r } }
            ?game bgg:hasName ?name ; bgg:hasGeekRating ?rating .
            FILTER(?rating = ?target)
        }
        UNION
        {
            { SELECT (MIN(?r) AS ?target) WHERE { ?g bgg:hasGeekRating ?r } }
            ?game bgg:hasName ?name ; bgg:hasGeekRating ?rating .
            FILTER(?rating = ?target)
        }
    }
\"\"\")
pretty(g.query(myquery))\
"""),

# P11
code("""\
# P11: BIND a rating label — <=6 "bad", 6-7 "ok", >7 "good"
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name ?rating ?label WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasName ?name ;
              bgg:hasGeekRating ?rating .
        BIND(IF(?rating <= 6, "bad",
              IF(?rating <= 7, "ok", "good")) AS ?label)
    }
    ORDER BY ?rating
    LIMIT 20
\"\"\")
pretty(g.query(myquery))\
"""),

# P12
code("""\
# P12: Compare each game to the average play time (subquery + BIND)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name ?t ?timerating WHERE {
        { SELECT (AVG(?time) AS ?avgtime) WHERE {
            ?game rdf:type bgg:Game ; bgg:hasMaxGameTime ?time } }
        ?game rdf:type bgg:Game ;
              bgg:hasName ?name ;
              bgg:hasMaxGameTime ?t .
        BIND(IF(?t < ?avgtime, "short", "long") AS ?timerating)
    }
    LIMIT 20
\"\"\")
pretty(g.query(myquery))\
"""),

# P13
code("""\
# P13: Count games per max-player count (GROUP BY)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (COUNT(?game) AS ?numgames) ?maxplayers WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasMaxPlayers ?maxplayers .
    }
    GROUP BY ?maxplayers
    ORDER BY ASC(?maxplayers)
\"\"\")
pretty(g.query(myquery))\
"""),

# P14
code("""\
# P14: 5 games without "war" but with "soldier" in the title (REGEX)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name WHERE {
        ?game bgg:hasName ?name .
        FILTER(!regex(?name, "war", "i") && regex(?name, "soldier", "i"))
    }
    LIMIT 5
\"\"\")
pretty(g.query(myquery))\
"""),

# P15
code("""\
# P15: Average geek rating per category, 2 decimals, descending
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (ROUND(AVG(?rating)*100)/100 AS ?avg) (COUNT(?game) AS ?n) ?cat WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasGeekRating ?rating ;
              bgg:hasCategory ?cat .
    }
    GROUP BY ?cat
    ORDER BY DESC(?avg)
\"\"\")
pretty(g.query(myquery))\
"""),

# P16
code("""\
# P16: Average playtime for games with exactly 4 max players
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (ROUND(AVG(?time)) AS ?avgtime) WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasMaxPlayers 4 ;
              bgg:hasMaxGameTime ?time .
    }
\"\"\")
pretty(g.query(myquery))\
"""),

# P17
code("""\
# P17: Average rating per category — only categories with more than 20 games (HAVING)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (AVG(?rating) AS ?avgrating) (COUNT(?game) AS ?n) ?category WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasGeekRating ?rating ;
              bgg:hasCategory ?category .
    }
    GROUP BY ?category
    HAVING (COUNT(?game) > 20)
    ORDER BY ASC(?n)
\"\"\")
pretty(g.query(myquery))\
"""),

# P18
code("""\
# P18: Mechanics used by 5+ games, with average and max play time
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?mechanic (ROUND(AVG(?time)) AS ?avgtime) (MAX(?time) AS ?maxtime)
           (COUNT(?game) AS ?n) WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasMechanic ?mechanic ;
              bgg:hasMaxGameTime ?time .
    }
    GROUP BY ?mechanic
    HAVING (COUNT(?game) > 5)
    ORDER BY DESC(?n)
    LIMIT 20
\"\"\")
pretty(g.query(myquery))\
"""),

# P19
code("""\
# P19: Creators with more than 5 games AND average rating above 7.0
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?creator (ROUND(AVG(?rating)*100)/100 AS ?avgrating) (COUNT(?game) AS ?n) WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasCreator ?creator ;
              bgg:hasGeekRating ?rating .
    }
    GROUP BY ?creator
    HAVING (AVG(?rating) > 7 && COUNT(?game) > 5)
    ORDER BY DESC(?avgrating)
\"\"\")
pretty(g.query(myquery))\
"""),

# P20
code("""\
# P20: Count games per play-time bucket: <=30, 31-60, >60 min
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (COUNT(?game) AS ?n) ?bucket WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasMaxGameTime ?t .
        BIND(IF(?t <= 30, "<=30 min",
              IF(?t <= 60, "31-60 min", ">60 min")) AS ?bucket)
    }
    GROUP BY ?bucket
\"\"\")
pretty(g.query(myquery))\
"""),

# P21
code("""\
# P21: Player-count ranges (min+max) with average rating — CONCAT for display
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (CONCAT(STR(?min), " to ", STR(?max)) AS ?range)
           (ROUND(AVG(?rating)*100)/100 AS ?avgrating) WHERE {
        ?game rdf:type bgg:Game ;
              bgg:hasMinPlayers ?min ;
              bgg:hasMaxPlayers ?max ;
              bgg:hasGeekRating ?rating .
    }
    GROUP BY ?min ?max
    ORDER BY ?min ?max
\"\"\")
pretty(g.query(myquery))\
"""),

# P22
code("""\
# P22: Games with animal names in the title (REGEX alternation)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name WHERE {
        ?game bgg:hasName ?name .
        FILTER(regex(?name, "(^| )(animal|cat|dog|horse|cow|bear|fox|wolf|penguin)( |$)", "i"))
    }
    ORDER BY ?name
\"\"\")
pretty(g.query(myquery))\
"""),

# P23
code("""\
# P23: Count games with no category at all (FILTER NOT EXISTS)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (COUNT(?game) AS ?n) WHERE {
        ?game rdf:type bgg:Game .
        FILTER NOT EXISTS { ?game bgg:hasCategory ?cat }
    }
\"\"\")
pretty(g.query(myquery))\
"""),

# P24
code("""\
# P24: How many games have 1, 2, 3 ... mechanics? (nested GROUP BY)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT (COUNT(?game) AS ?numgames) ?numMechanics WHERE {
        SELECT DISTINCT ?game (COUNT(?mech) AS ?numMechanics) WHERE {
            ?game rdf:type bgg:Game ;
                  bgg:hasMechanic ?mech .
        }
        GROUP BY ?game
    }
    GROUP BY ?numMechanics
    ORDER BY ?numMechanics
\"\"\")
pretty(g.query(myquery))\
"""),

# P25
code("""\
# P25: UNION — games by Reiner Knizia OR in the Abstract_Strategy category
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT DISTINCT ?name WHERE {
        { ?game bgg:hasCreator "Reiner Knizia" ; bgg:hasName ?name }
        UNION
        { ?game bgg:hasCategory bgg:Abstract_Strategy ; bgg:hasName ?name }
    }
    LIMIT 10
\"\"\")
pretty(g.query(myquery))\
"""),

# P26
code("""\
# P26: XOR — games in Humor OR Party_Game, but NOT both
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name WHERE {
        {   ?game bgg:hasCategory bgg:Humor ; bgg:hasName ?name .
            FILTER NOT EXISTS { ?game bgg:hasCategory bgg:Party_Game } }
        UNION
        {   ?game bgg:hasCategory bgg:Party_Game ; bgg:hasName ?name .
            FILTER NOT EXISTS { ?game bgg:hasCategory bgg:Humor } }
    }
    ORDER BY ?name
    LIMIT 20
\"\"\")
pretty(g.query(myquery))\
"""),

# P27
code("""\
# P27: Creators with avg rating + game count, only those with >5 games
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?creator (ROUND(AVG(?rating)*100)/100 AS ?avgrating) (COUNT(?game) AS ?n) WHERE {
        ?game bgg:hasCreator ?creator ;
              bgg:hasGeekRating ?rating .
    }
    GROUP BY ?creator
    HAVING (COUNT(?game) > 5)
    ORDER BY DESC(?n)
\"\"\")
pretty(g.query(myquery))\
"""),

# P28
code("""\
# P28: For each game, is its rating above or below the overall average? (subquery + BIND)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?name ?rating ?vs WHERE {
        { SELECT (AVG(?r) AS ?avg) WHERE { ?g bgg:hasGeekRating ?r } }
        ?game bgg:hasGeekRating ?rating ;
              bgg:hasName ?name .
        BIND(IF(?rating >= ?avg, "above avg", "below avg") AS ?vs)
    }
    ORDER BY DESC(?rating)
    LIMIT 20
\"\"\")
pretty(g.query(myquery))\
"""),

md("---\n# Property paths and UPDATE\n\nThese problems use SPARQL UPDATE (INSERT) and property path expressions (`+`, `^`)."),

# P29
code("""\
# P29: INSERT a transitive bgg:expands property with 4 test games
g.update(\"\"\"
""" + PFX + """
    INSERT {
        bgg:expands rdf:type owl:ObjectProperty, owl:TransitiveProperty ;
                    rdfs:domain bgg:Game ; rdfs:range bgg:Game .
        bgg:Game1 rdf:type bgg:Game .
        bgg:Game2 rdf:type bgg:Game ; bgg:expands bgg:Game1 .
        bgg:Game3 rdf:type bgg:Game ; bgg:expands bgg:Game2 .
        bgg:Game4 rdf:type bgg:Game ; bgg:expands bgg:Game3 .
    } WHERE {}
\"\"\")

myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT ?s ?o WHERE { ?s bgg:expands ?o }
\"\"\")
pretty(g.query(myquery))\
"""),

# P30
code("""\
# P30: Property path + — all (game, expandsTo) pairs, including transitive
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT DISTINCT ?game ?expandsTo WHERE {
        ?game rdf:type bgg:Game ;
              bgg:expands+ ?expandsTo .
    }
\"\"\")
pretty(g.query(myquery))\
"""),

# P31
code("""\
# P31: Inverse path ^ — all games that expand Game1 (directly or via chain)
myquery = prepareQuery(\"\"\"
""" + PFX + """
    SELECT DISTINCT ?game WHERE {
        bgg:Game1 ^bgg:expands+ ?game .
    }
\"\"\")
pretty(g.query(myquery))\
"""),

md("""\
---
# OWL modeling exercises

The cells below are **write-your-own** exercises. There is no runnable code — \
each problem asks you to write an OWL class expression in Turtle syntax.\
"""),

md("""\
### OWL 1: Define GameDesigner
A class of individuals that have created at least one Game.

```turtle
bgg:GameDesigner rdf:type owl:Class ;
  owl:equivalentClass [
    rdf:type owl:Restriction ;
    owl:onProperty bgg:hasCreated ;
    owl:someValuesFrom bgg:Game
  ] .
```\
"""),

md("""\
### OWL 2: FamilyGame — union of categories
A FamilyGame is any game with category Party_Game OR Trivia.

```turtle
bgg:FamilyGame a owl:Class ;
  owl:equivalentClass [
    owl:unionOf (
      [ a owl:Restriction ; owl:onProperty bgg:hasCategory ; owl:hasValue bgg:Party_Game ]
      [ a owl:Restriction ; owl:onProperty bgg:hasCategory ; owl:hasValue bgg:Trivia ]
    )
  ] .
```\
"""),

md("""\
### OWL 3: DiceAndCardGame — intersection of mechanics
Must have BOTH Dice_Rolling AND Card_Drafting.

```turtle
bgg:DiceAndCardGame a owl:Class ;
  owl:equivalentClass [
    owl:intersectionOf (
      [ a owl:Restriction ; owl:onProperty bgg:hasMechanic ; owl:hasValue bgg:Dice_Rolling ]
      [ a owl:Restriction ; owl:onProperty bgg:hasMechanic ; owl:hasValue bgg:Card_Drafting ]
    )
  ] .
```\
"""),

md("""\
### OWL 4: KidFriendlyGame — intersection with datatype restriction
Must be in Childrens_Game category AND have max playtime <= 30 minutes.

```turtle
bgg:KidFriendlyGame a owl:Class ;
  owl:equivalentClass [
    owl:intersectionOf (
      [ a owl:Restriction ; owl:onProperty bgg:hasCategory ; owl:hasValue bgg:Childrens_Game ]
      [ a owl:Restriction ; owl:onProperty bgg:hasMaxGameTime ;
        owl:allValuesFrom [ a rdfs:Datatype ; owl:onDatatype xsd:integer ;
          owl:withRestrictions ( [ xsd:maxInclusive 30 ] ) ] ]
    )
  ] .
```\
"""),

md("""\
### OWL 5: WarGame / PeaceGame — complement
WarGame has a conflict-based category. PeaceGame is its complement.

```turtle
bgg:WarGame a owl:Class ;
  owl:equivalentClass [
    a owl:Restriction ;
    owl:onProperty bgg:hasCategory ;
    owl:someValuesFrom [ a owl:Class ; owl:oneOf (bgg:World_War_I bgg:World_War_II bgg:Wargame) ]
  ] .

bgg:PeaceGame a owl:Class ;
  owl:complementOf bgg:WarGame .
```\
"""),

md("""\
### OWL 6: Transitive property — game expansions
Create a property that means "this game is an expansion of another", \
transitively (if A expands B and B expands C, then A expands C).

```turtle
bgg:expands a owl:ObjectProperty, owl:TransitiveProperty ;
  rdfs:domain bgg:Game ;
  rdfs:range  bgg:Game .
```

Then run P29–P31 above to see this in action with SPARQL property paths.\
"""),

]

nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12.0"},
    },
    "cells": cells,
}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Practice_SPARQL_local.ipynb")
with open(out, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print(f"Written {len(cells)} cells to {out}")
