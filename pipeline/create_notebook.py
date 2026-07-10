"""Generate the SPARQL Q&A notebook."""
import json

SCHEMA = (
    "## Board Game Knowledge Graph — Ontology Schema\n\n"
    "### Namespaces (include in every query)\n"
    "    PREFIX bgg:   <https://raw.githubusercontent.com/susvej/bg_ontology/>\n"
    "    PREFIX trenj: <https://vejdemo.se/boardgames/threnjen#>\n"
    "    PREFIX svj:   <https://vejdemo.se/boardgames#>\n"
    "    PREFIX fake:  <https://vejdemo.se/boardgames/fake#>\n"
    "    PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
    "    PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>\n"
    "    PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>\n\n"
    "### Classes\n"
    "- `bgg:Game` — A board game listed on BoardGameGeek (126,266 total)\n"
    "- `bgg:Creator` — A person who designed or created a board game (3,205 total)\n"
    "- `bgg:Category` — A thematic grouping as defined by BGG (84 total, e.g. 'Fantasy', 'Card Game')\n"
    "- `bgg:Mechanic` — A game-play mechanism (173 total, e.g. 'Worker Placement', 'Deck, Bag, and Pool Building')\n"
    "- `bgg:Publisher` — A company or individual that publishes board games\n"
    "- `bgg:Size` — Physical box size (values: `bgg:small` weight<2.0, `bgg:medium` 2-3, `bgg:large` >=3.0)\n"
    "- `bgg:MentalLoad` — Cognitive difficulty (values: `bgg:easy`, `bgg:moderate`, `bgg:difficult`)\n"
    "- `bgg:Player` — A person who plays board games (1 real + 200 fake players)\n"
    "- `bgg:PlayerOpinion` — One player's opinion of one game\n"
    "- `trenj:Theme` — A thematic tag from the threnjen dataset (217 total, e.g. 'Fantasy', 'Space Exploration')\n\n"
    "### Datatype Properties on bgg:Game\n"
    "- `bgg:hasName` xsd:string — game title (e.g. 'Catan', 'Wingspan')\n"
    "- `bgg:hasID` xsd:int — BGG numeric ID\n"
    "- `bgg:hasDescription` xsd:string — prose description from BGG\n"
    "- `bgg:hasYearPublished` xsd:int — year first published\n"
    "- `bgg:hasRating` xsd:double — average community rating (1-10)\n"
    "- `bgg:hasGeekRating` xsd:double — BGG Geek Rating (adjusted for vote count)\n"
    "- `bgg:ratingFromTime` xsd:int — year rating was collected (2022 or 2025)\n"
    "- `bgg:hasMinPlayers` xsd:int — minimum players required\n"
    "- `bgg:hasMaxPlayers` xsd:int — maximum players supported\n"
    "- `bgg:hasBestNumPlayers` xsd:int — optimal player count per community vote\n"
    "- `bgg:hasMinGameTime` xsd:int — minimum playtime in minutes\n"
    "- `bgg:hasMaxGameTime` xsd:int — maximum playtime in minutes\n"
    "- `bgg:hasMinRecAge` xsd:int — minimum recommended age in years\n"
    "- `bgg:isFullyEnriched` xsd:boolean — true if game has mechanics/categories/themes/creators/publishers (21,379 games only)\n\n"
    "### Object Properties on bgg:Game\n"
    "- `bgg:hasURL` URI — BGG page URL\n"
    "- `bgg:hasThumbnail` URI — thumbnail image URL\n"
    "- `bgg:hasCategory` bgg:Category — (use rdfs:label to filter by name)\n"
    "- `bgg:hasMechanic` bgg:Mechanic — (use rdfs:label to filter by name)\n"
    "- `bgg:hasCreator` bgg:Creator — (use rdfs:label to filter by name)\n"
    "- `bgg:hasPublisher` bgg:Publisher — (use rdfs:label to filter by name)\n"
    "- `bgg:hasSize` bgg:Size — box size (bgg:small / bgg:medium / bgg:large)\n"
    "- `trenj:hasTheme` trenj:Theme — thematic tag (use rdfs:label to filter by name)\n\n"
    "### Object Properties on bgg:Player / bgg:PlayerOpinion\n"
    "- `bgg:hasOwnershipOf` — Player -> Game they own\n"
    "- `bgg:hasOpinionHolder` — PlayerOpinion -> Player\n"
    "- `bgg:hasOpinionOf` — PlayerOpinion -> Game\n"
    "- `bgg:hasMentalLoad` — PlayerOpinion -> bgg:easy / bgg:moderate / bgg:difficult\n"
    "- `bgg:hasPlayerRatingOpinion` xsd:decimal — personal rating 1-10\n"
    "- `bgg:likesCategory` — Player -> Category (declared preference)\n"
    "- `bgg:likesMechanic` — Player -> Mechanic (declared preference)\n\n"
    "### IMPORTANT DATA NOTES\n"
    "1. Only 21,379 games have `bgg:isFullyEnriched true` and carry mechanics/categories/themes/creators/publishers.\n"
    "   The other ~105k games have only: name, description, year, ratings, thumbnail, URL.\n"
    "2. All controlled-vocab labels (Category, Mechanic, Theme, Creator, Publisher) use `rdfs:label`@en.\n"
    "   Match with: `?vocab rdfs:label \"Name\"@en` or FILTER(str(?label) = \"Name\").\n"
    "3. `bgg:hasName` values are xsd:string -- match with \"Catan\"^^xsd:string or FILTER(str(?name) = \"Catan\").\n"
    "4. For case-insensitive name search: FILTER(CONTAINS(LCASE(str(?name)), \"catan\")).\n"
    "5. Fake player data (200 players, namespace fake:) and Susanne's data (namespace svj:) are in the same graph.\n\n"
    "### Example SPARQL Queries\n\n"
    "Find a game by exact name:\n"
    "    PREFIX bgg: <https://raw.githubusercontent.com/susvej/bg_ontology/>\n"
    "    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
    "    SELECT ?game ?year ?rating WHERE {\n"
    "      ?game a bgg:Game ;\n"
    "            bgg:hasName \"Catan\"^^xsd:string ;\n"
    "            bgg:hasYearPublished ?year ;\n"
    "            bgg:hasRating ?rating .\n"
    "    }\n\n"
    "Top-rated games for 2 players:\n"
    "    PREFIX bgg: <https://raw.githubusercontent.com/susvej/bg_ontology/>\n"
    "    SELECT ?name ?rating WHERE {\n"
    "      ?game a bgg:Game ;\n"
    "            bgg:hasName ?name ;\n"
    "            bgg:hasRating ?rating ;\n"
    "            bgg:hasMinPlayers ?min ;\n"
    "            bgg:hasMaxPlayers ?max .\n"
    "      FILTER(?min <= 2 && ?max >= 2)\n"
    "    }\n"
    "    ORDER BY DESC(?rating) LIMIT 10\n\n"
    "Games with Worker Placement mechanic:\n"
    "    PREFIX bgg: <https://raw.githubusercontent.com/susvej/bg_ontology/>\n"
    "    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "    SELECT ?name ?rating WHERE {\n"
    "      ?game a bgg:Game ;\n"
    "            bgg:hasName ?name ;\n"
    "            bgg:hasMechanic ?mech ;\n"
    "            bgg:hasRating ?rating .\n"
    "      ?mech rdfs:label \"Worker Placement\"@en .\n"
    "    }\n"
    "    ORDER BY DESC(?rating) LIMIT 10\n\n"
    "Games in Fantasy theme (trenj data):\n"
    "    PREFIX bgg: <https://raw.githubusercontent.com/susvej/bg_ontology/>\n"
    "    PREFIX trenj: <https://vejdemo.se/boardgames/threnjen#>\n"
    "    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "    SELECT ?name ?rating WHERE {\n"
    "      ?game a bgg:Game ;\n"
    "            bgg:hasName ?name ;\n"
    "            bgg:hasRating ?rating ;\n"
    "            trenj:hasTheme ?theme .\n"
    "      ?theme rdfs:label \"Fantasy\"@en .\n"
    "    }\n"
    "    ORDER BY DESC(?rating) LIMIT 10\n\n"
    "Fake player opinions:\n"
    "    PREFIX bgg: <https://raw.githubusercontent.com/susvej/bg_ontology/>\n"
    "    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "    SELECT ?playerName ?gameName ?personalRating WHERE {\n"
    "      ?op a bgg:PlayerOpinion ;\n"
    "          bgg:hasOpinionHolder ?player ;\n"
    "          bgg:hasOpinionOf ?game ;\n"
    "          bgg:hasPlayerRatingOpinion ?personalRating .\n"
    "      ?player rdfs:label ?playerName .\n"
    "      ?game bgg:hasName ?gameName .\n"
    "      FILTER(?personalRating = 10)\n"
    "    } LIMIT 20\n"
)

SYSTEM_SPARQL = (
    "You are a SPARQL expert for a BoardGameGeek (BGG) knowledge graph stored in GraphDB.\n"
    "Given a natural-language question, generate a single SPARQL 1.1 SELECT query that answers it.\n\n"
    + SCHEMA +
    "\nRules:\n"
    "- Always include all required PREFIX declarations.\n"
    "- Return ONLY the raw SPARQL query with no explanation, no markdown fences, no commentary.\n"
    "- Use OPTIONAL { } for properties that may not exist on all games.\n"
    "- Use ORDER BY DESC(?rating) and LIMIT when asked for 'best', 'top', or 'most popular'.\n"
    "- When filtering by category/mechanic/theme/creator/publisher name, match via rdfs:label.\n"
    "- For free-text game name search: FILTER(CONTAINS(LCASE(str(?name)), LCASE(\"term\"))).\n"
    "- For exact game name: bgg:hasName \"Title\"^^xsd:string.\n"
    "- Do not use DESCRIBE or CONSTRUCT — only SELECT queries.\n"
    "- Avoid Cartesian products; use FILTER close to the relevant triple pattern.\n"
)

SYSTEM_RESULT = (
    "You are a helpful assistant explaining SPARQL query results about board games.\n"
    "Given a question and the raw SPARQL results (as JSON), write a clear, concise natural-language answer.\n"
    "Focus on answering the question directly. If the results are empty, say so and suggest why.\n"
    "Format lists nicely. Round numbers to 2 decimal places. Keep your answer under 200 words."
)

# ---- Build notebook cells ----

def md(src):
    return {
        "cell_type": "markdown",
        "id": "md" + str(abs(hash(src[:30])))[:7],
        "metadata": {},
        "source": src,
    }

def code(src):
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": "c" + str(abs(hash(src[:30])))[:7],
        "metadata": {},
        "outputs": [],
        "source": src,
    }

cells = []

cells.append(md(
    "# BGG Ontology — Natural Language to SPARQL\n\n"
    "Two-call Claude pipeline:\n"
    "1. User question → Claude generates SPARQL\n"
    "2. Execute SPARQL against GraphDB\n"
    "3. Claude interprets results → natural-language answer\n\n"
    "**Prerequisites:** GraphDB running locally with the BGG ontology loaded (see Setup section below).\n"
    "Set the `ANTHROPIC_API_KEY` environment variable before starting Jupyter.\n"
))

cells.append(md("## Setup\n\n"
    "Load data into GraphDB before running queries:\n"
    "1. Create a repository named `bgg` (or change `REPO_NAME` below)\n"
    "2. Import `bgg_kaggle2025.ttl` into the default graph (126k games, 1.3M triples)\n"
    "3. Optionally import `fake_players.ttl` into the same default graph (200 fake players)\n"
))

cells.append(md("## Configuration"))
cells.append(code(
    "import os\n"
    "import json\n"
    "import textwrap\n"
    "import requests\n"
    "import anthropic\n"
    "\n"
    "# --- GraphDB ---\n"
    'GRAPHDB_URL     = "http://localhost:7200"\n'
    'REPO_NAME       = "bgg"                     # change to match your repository name\n'
    "SPARQL_ENDPOINT = f\"{GRAPHDB_URL}/repositories/{REPO_NAME}\"\n"
    "\n"
    "# --- Anthropic ---\n"
    'ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")\n'
    'assert ANTHROPIC_API_KEY, "Set the ANTHROPIC_API_KEY environment variable"\n'
    "\n"
    "client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)\n"
    'MODEL  = "claude-opus-4-7"\n'
    "\n"
    "print(f\"GraphDB endpoint: {SPARQL_ENDPOINT}\")\n"
    "print(f\"Model: {MODEL}\")\n"
))

cells.append(md("## System Prompts"))
cells.append(code(
    "SYSTEM_SPARQL = " + json.dumps(SYSTEM_SPARQL) + "\n"
    "SYSTEM_RESULT = " + json.dumps(SYSTEM_RESULT) + "\n"
    "\n"
    "print(f\"SPARQL system prompt: {len(SYSTEM_SPARQL)} chars\")\n"
    "print(f\"Result system prompt: {len(SYSTEM_RESULT)} chars\")\n"
))

cells.append(md("## Pipeline Functions"))
cells.append(code(
    "def generate_sparql(question: str) -> str:\n"
    "    \"\"\"Call 1: natural language -> SPARQL query.\"\"\"\n"
    "    response = client.messages.create(\n"
    "        model=MODEL,\n"
    "        max_tokens=1024,\n"
    "        system=[\n"
    "            {\n"
    '                "type": "text",\n'
    '                "text": SYSTEM_SPARQL,\n'
    '                "cache_control": {"type": "ephemeral"},\n'
    "            }\n"
    "        ],\n"
    '        messages=[{"role": "user", "content": question}],\n'
    "    )\n"
    "    query = response.content[0].text.strip()\n"
    "    # Strip markdown fences if present\n"
    '    if query.startswith("```"):\n'
    '        query = "\\n".join(\n'
    '            l for l in query.splitlines() if not l.startswith("```")\n'
    "        ).strip()\n"
    "    return query\n"
    "\n"
    "\n"
    "def execute_sparql(query: str) -> dict:\n"
    "    \"\"\"Execute a SPARQL SELECT against GraphDB; return parsed JSON results.\"\"\"\n"
    "    resp = requests.post(\n"
    "        SPARQL_ENDPOINT,\n"
    '        data={"query": query},\n'
    '        headers={"Accept": "application/sparql-results+json"},\n'
    "        timeout=30,\n"
    "    )\n"
    "    resp.raise_for_status()\n"
    "    return resp.json()\n"
    "\n"
    "\n"
    "def interpret_results(question: str, query: str, results: dict) -> str:\n"
    "    \"\"\"Call 2: SPARQL results -> natural-language answer.\"\"\"\n"
    '    bindings = results.get("results", {}).get("bindings", [])\n'
    '    vars_    = results.get("head",    {}).get("vars",     [])\n'
    "\n"
    "    payload = {\n"
    '        "question": question,\n'
    '        "sparql_query": query,\n'
    '        "result_variables": vars_,\n'
    '        "result_count": len(bindings),\n'
    '        "results": bindings[:50],\n'
    "    }\n"
    "\n"
    "    response = client.messages.create(\n"
    "        model=MODEL,\n"
    "        max_tokens=512,\n"
    "        system=SYSTEM_RESULT,\n"
    "        messages=[\n"
    "            {\n"
    '                "role": "user",\n'
    '                "content": json.dumps(payload, ensure_ascii=False),\n'
    "            }\n"
    "        ],\n"
    "    )\n"
    "    return response.content[0].text.strip()\n"
    "\n"
    "\n"
    "def ask(question: str, show_query: bool = True) -> str:\n"
    "    \"\"\"Full pipeline: question -> SPARQL -> execute -> natural-language answer.\"\"\"\n"
    "    print(f\"Question: {question}\")\n"
    "    print()\n"
    "\n"
    "    query = generate_sparql(question)\n"
    "    if show_query:\n"
    '        print("Generated SPARQL:")\n'
    '        print("-" * 60)\n'
    "        print(query)\n"
    '        print("-" * 60)\n'
    "        print()\n"
    "\n"
    "    try:\n"
    "        results = execute_sparql(query)\n"
    "    except requests.HTTPError as e:\n"
    "        print(f\"SPARQL execution error: {e}\")\n"
    "        print(e.response.text[:500])\n"
    '        return ""\n'
    "\n"
    '    n = len(results.get("results", {}).get("bindings", []))\n'
    "    print(f\"Results: {n} row(s)\")\n"
    "    print()\n"
    "\n"
    "    answer = interpret_results(question, query, results)\n"
    '    print("Answer:")\n'
    "    print(textwrap.fill(answer, width=80))\n"
    "    print()\n"
    "    return answer\n"
))

cells.append(md("## Test GraphDB Connectivity"))
cells.append(code(
    "test_query = \"SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }\"\n"
    "try:\n"
    "    result = execute_sparql(test_query)\n"
    '    count = result["results"]["bindings"][0]["n"]["value"]\n'
    "    print(f\"GraphDB is reachable. Total triples: {count}\")\n"
    "except Exception as e:\n"
    "    print(f\"Cannot reach GraphDB: {e}\")\n"
    "    print(f\"Make sure GraphDB is running at {GRAPHDB_URL}\")\n"
    "    print(f\"and a repository named '{REPO_NAME}' exists with the TTL loaded.\")\n"
))

cells.append(md(
    "## Example Queries\n\n"
    "Run any cell below, or write your own at the bottom.\n"
))

examples = [
    "What are the top 10 highest-rated board games of all time?",
    "Which games use the Worker Placement mechanic and have a rating above 8?",
    "What games can be played by exactly 2 players and take less than 30 minutes?",
    "What games did Uwe Rosenberg design?",
    "Which categories have the most games?",
    "What games are in the Fantasy category with a geek rating above 7.5?",
    "Which fake players gave a rating of 10 to any game, and what games did they rate?",
]

for q in examples:
    cells.append(code("ask(" + json.dumps(q) + ")"))

cells.append(md("## Your Question"))
cells.append(code(
    "# Change this and run\n"
    "ask(\"What are the best cooperative games?\")\n"
))

nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12.13",
        },
    },
    "cells": cells,
}

with open("bgg_sparql_qa.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print("Written: bgg_sparql_qa.ipynb")
