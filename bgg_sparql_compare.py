"""
SPARQL-Compare agent — runs Q-SQL1 and Q-SQL2 against GraphDB.

Designed to be the SPARQL reference implementation for the SPARQL vs SQL comparison project.
The equivalent SQL agent will run the same questions against a relational database.

Prompts are loaded live from bgg_sparql_qa.ipynb so they stay in sync.
"""
import json, os, sys
from datetime import datetime as _dt
from pathlib import Path
import requests
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
GRAPHDB_URL     = "http://localhost:7200"
SPARQL_ENDPOINT = f"{GRAPHDB_URL}/repositories/bgg"
MODEL           = "claude-sonnet-4-6"
AGENT_NAME      = "sparql_compare"
LOG_FILE        = "qa_log.jsonl"
TIMEOUT         = 60   # seconds for SPARQL execution

# ── API key ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    for line in Path(".env").read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            ANTHROPIC_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
if not ANTHROPIC_API_KEY:
    sys.exit("ANTHROPIC_API_KEY not found — set it in .env")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Load prompts from the existing SPARQL notebook ────────────────────────────
with open("bgg_sparql_qa.ipynb", encoding="utf-8") as f:
    nb = json.load(f)

SYSTEM_SPARQL = SYSTEM_RESULT = None
for cell in nb["cells"]:
    src = "".join(cell["source"])
    if 'SYSTEM_SPARQL = """' in src and SYSTEM_SPARQL is None:
        s1 = src.index('SYSTEM_SPARQL = """') + len('SYSTEM_SPARQL = """')
        s2 = src.index('"""\n\nSYSTEM_RESULT')
        SYSTEM_SPARQL = src[s1:s2]
    if 'SYSTEM_RESULT = """' in src and SYSTEM_RESULT is None:
        s1 = src.index('SYSTEM_RESULT = """') + len('SYSTEM_RESULT = """')
        s2 = src.index('"""\n\nprint')
        SYSTEM_RESULT = src[s1:s2]

assert SYSTEM_SPARQL and SYSTEM_RESULT, "Could not extract prompts from bgg_sparql_qa.ipynb"
print(f"Prompts loaded  (SPARQL: {len(SYSTEM_SPARQL)} chars, RESULT: {len(SYSTEM_RESULT)} chars)")

# ── Questions ─────────────────────────────────────────────────────────────────
QUESTIONS = [
    (
        "QSQL1",
        "Find me a game about the sea — whether it appears as a theme or a category, "
        "and whether the label used is 'Nautical', 'maritime', 'naval', or 'sailing' — "
        "that also features a route-building or network-building mechanic, "
        "and that none of the three of us (Susanne Vejdemo, Gertrude Young, and Maja Brown) already own. "
        "Order by rating and show the top results."
    ),
    (
        "QSQL2",
        "Suggest highly-rated games that I, Susanne Vejdemo, do not own, "
        "but that were designed by the same person who designed a game "
        "that Gertrude Young owns and rates 8 or above."
    ),
    (
        "QSQL3",
        "Find a highly-rated game that neither Susanne Vejdemo nor Gertrude Young owns, "
        "where the game was designed by someone who also designed a game that Susanne rates 8 or higher, "
        "and where the game also features a mechanic found in a game that Gertrude rates 8 or higher."
    ),
    (
        "QSQL4",
        "Who are Susanne Vejdemo's closest 'game neighbors' in this community? "
        "Find the other players who share the most games in common with Susanne, "
        "and show how many games they share. Order by overlap descending."
    ),
    (
        "QSQL5",
        "Recommend a highly-rated game (8 or above) that neither Susanne Vejdemo nor Gertrude Young owns, "
        "found through a three-hop designer chain: start from a game that Gertrude rates 8 or higher, "
        "follow the designer to another game they made, then follow a co-designer on that second game "
        "to find the final recommendation. Show the chain: Gertrude's game, the linking designer, "
        "the bridge game, the co-designer, and the recommended game."
    ),
    (
        "QSQL6",
        "Who is in Susanne Vejdemo's gaming community? "
        "Find ALL players reachable from Susanne through chains of shared game ownership — "
        "where two players are 'connected' if they share at least one game in common, "
        "and the community is the full transitive closure of this connection relationship "
        "(i.e. it includes Susanne's direct game-neighbors, their game-neighbors, and so on "
        "to any depth). List all community members by name and report the total count."
    ),
    (
        "QSQL7",
        "Show me all games in the Ticket to Ride game family — "
        "starting from the original Ticket to Ride (BGG ID 9209), "
        "find every game that reimplements it, every game that reimplements those, "
        "and so on recursively to any depth. "
        "List each game's name and rating, ordered by rating descending."
    ),
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def generate_sparql(question: str, error_context: str = None) -> str:
    user_content = question
    if error_context:
        user_content = "\n\n".join([
            question,
            f"Your previous query failed with this error:\n{error_context}",
            "Please fix the SPARQL query.",
        ])
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM_SPARQL,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    )
    query = response.content[0].text.strip()
    if query.startswith("```"):
        query = "\n".join(l for l in query.splitlines()
                          if not l.startswith("```")).strip()
    # Strip prose preamble: drop any lines before the first PREFIX or SELECT
    lines = query.splitlines()
    for i, line in enumerate(lines):
        if line.strip().upper().startswith(("PREFIX", "SELECT", "ASK", "CONSTRUCT", "DESCRIBE")):
            query = "\n".join(lines[i:])
            break
    # Fix occasional namespace hallucination
    query = query.replace("rdf-design#", "rdf-schema#")
    return query


def execute_sparql(query: str) -> dict:
    resp = requests.post(
        SPARQL_ENDPOINT,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def interpret_results(question: str, query: str, results: dict) -> str:
    bindings = results.get("results", {}).get("bindings", [])
    vars_    = results.get("head", {}).get("vars", [])
    payload  = {
        "question":           question,
        "sparql_query":       query,
        "result_variables":   vars_,
        "result_count":       len(bindings),
        "results_truncated":  len(bindings) > 50,
        "results":            bindings[:50],
    }
    response = client.messages.create(
        model=MODEL,
        max_tokens=768,
        system=SYSTEM_RESULT,
        messages=[{"role": "user",
                   "content": json.dumps(payload, ensure_ascii=False)}],
    )
    return response.content[0].text.strip()


def _log(question_id: str, question: str, answer: str) -> None:
    entry = {
        "timestamp":   _dt.now().isoformat(timespec="seconds"),
        "agent":       AGENT_NAME,
        "question_id": question_id,
        "question":    question,
        "answer":      answer,
        "score":       None,
        "comment":     "",
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ask(question_id: str, question: str, max_retries: int = 2) -> str:
    print(f"\n{'='*70}")
    print(f"[{question_id}]")
    print(f"Q: {question}")
    print()

    query = generate_sparql(question)
    print("Generated SPARQL:")
    print(query)
    print()

    for attempt in range(max_retries + 1):
        try:
            results = execute_sparql(query)
            break
        except requests.HTTPError as e:
            error_msg = e.response.text[:500]
            print(f"  SPARQL error (attempt {attempt+1}): {error_msg[:120]}")
            if attempt < max_retries:
                query = generate_sparql(question, error_msg)
                print("  Retrying with revised query...")
            else:
                print("  All retries exhausted.")
                raise
        except requests.Timeout:
            print(f"  Timeout after {TIMEOUT}s — query too expensive.")
            raise

    n = len(results.get("results", {}).get("bindings", []))
    print(f"Results: {n} binding(s)")
    print()

    answer = interpret_results(question, query, results)
    _log(question_id, question, answer)

    print("Answer:")
    print(answer.encode("ascii", errors="replace").decode())
    return answer


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    for qid, question in QUESTIONS:
        ask(qid, question)
    print(f"\n{'='*70}")
    print("Done. Results logged to", LOG_FILE)
