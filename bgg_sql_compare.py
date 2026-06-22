"""
SQL-Compare agent — runs Q-SQL1 and Q-SQL2 against bgg.db (SQLite).

Counterpart to bgg_sparql_compare.py for the SPARQL-vs-SQL comparison project.
Uses the same two questions; results are logged to qa_log.jsonl for side-by-side scoring.
"""
import json, os, sqlite3, sys
from datetime import datetime as _dt
from pathlib import Path
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH    = "bgg.db"
MODEL      = "claude-sonnet-4-6"
AGENT_NAME = "sql_compare"
LOG_FILE   = "qa_log.jsonl"

# ── API key ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    for line in Path(".env").read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            ANTHROPIC_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
if not ANTHROPIC_API_KEY:
    sys.exit("ANTHROPIC_API_KEY not found")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── System prompts ────────────────────────────────────────────────────────────
SYSTEM_SQL = """You are an expert SQL assistant for a board game database (SQLite).
Your job is to write a single, correct SQL SELECT query that answers the user's question.
Output ONLY the SQL query — no explanation, no markdown, no code fences.

## Schema

```
games (
    id               INTEGER PRIMARY KEY,   -- numeric BGG game ID
    name             TEXT,
    year             INTEGER,
    rating           REAL,                  -- community rating 1-10
    geek_rating      REAL,                  -- BGG Bayesian-adjusted "geek rating"
    min_players      INTEGER,
    max_players      INTEGER,
    best_num_players INTEGER,               -- optimal player count
    min_time         INTEGER,               -- minutes
    max_time         INTEGER,
    min_rec_age      INTEGER,               -- minimum recommended age in years
    size             TEXT,                  -- "Small", "Medium", or "Large" (weight proxy)
    description      TEXT                   -- prose description (~half of games have one)
)

mechanics (
    id    TEXT PRIMARY KEY,                 -- camelCase local name, e.g. "HandManagement"
    label TEXT                              -- human-readable, e.g. "Hand Management"
)

categories (
    id    TEXT PRIMARY KEY,
    label TEXT
)

themes (
    id    TEXT PRIMARY KEY,
    label TEXT                              -- e.g. "Pirates", "Fantasy", "Space Exploration"
)

creators (
    id    TEXT PRIMARY KEY,                 -- camelCase local name, e.g. "UweRosenberg"
    label TEXT                              -- full name, e.g. "Uwe Rosenberg"
)

publishers (
    id    TEXT PRIMARY KEY,
    label TEXT
)

players (
    id        TEXT PRIMARY KEY,             -- camelCase local name, e.g. "GertrudeYoung"
    label     TEXT,                         -- full name, e.g. "Gertrude Young"
    namespace TEXT                          -- "svj" (Susanne Vejdemo) or "fake" (fake players)
)

-- Alternative labels for mechanics, categories, and themes (e.g. "Nautical" has altLabel "maritime")
alt_labels (
    entity_id TEXT NOT NULL,               -- matches id in mechanics/categories/themes
    label     TEXT NOT NULL,
    PRIMARY KEY (entity_id, label)
)

game_mechanics  (game_id INTEGER → games.id,   mechanic_id  TEXT → mechanics.id)
game_categories (game_id INTEGER → games.id,   category_id  TEXT → categories.id)
game_themes     (game_id INTEGER → games.id,   theme_id     TEXT → themes.id)
game_creators   (game_id INTEGER → games.id,   creator_id   TEXT → creators.id)
game_publishers (game_id INTEGER → games.id,   publisher_id TEXT → publishers.id)
player_owns     (player_id TEXT → players.id,  game_id      INTEGER → games.id)
player_opinions (
    player_id   TEXT → players.id,
    game_id     INTEGER → games.id,
    rating      REAL,                       -- player's personal rating 1-10
    mental_load TEXT                        -- "Light", "Medium", or "Heavy"
)
```

## Key facts
- Match players by their `label` column (full name, e.g. `label = 'Gertrude Young'`).
- Susanne Vejdemo is the user asking questions (namespace = 'svj').
- To match a theme by name OR altLabel, join both tables:
    JOIN game_themes gt ON gt.game_id = g.id
    JOIN themes t ON t.id = gt.theme_id
    LEFT JOIN alt_labels al ON al.entity_id = t.id
    WHERE LOWER(t.label) LIKE '%pirat%' OR LOWER(al.label) LIKE '%pirat%'
- Same pattern applies for mechanics/categories searched by altLabel.
- "Mechanic familiar from a game they own" means: the player owns a game that has that mechanic.
- "Mechanic that both players know" means: the mechanic exists in at least one game owned by EACH player.
- Use EXISTS subqueries or CTEs for multi-player mechanic intersection — avoid cartesian joins.
- Always ORDER BY g.rating DESC and use LIMIT 20 unless otherwise specified.

## Example — games matching a concept in EITHER theme OR category, via label or altLabel:
-- Use UNION to search both tables; LEFT JOIN alt_labels once per table.
SELECT DISTINCT g.name, g.rating
FROM games g
WHERE (
    EXISTS (
        SELECT 1 FROM game_themes gt
        JOIN themes t ON t.id = gt.theme_id
        LEFT JOIN alt_labels al ON al.entity_id = t.id
        WHERE gt.game_id = g.id
          AND (LOWER(t.label) LIKE '%nautical%' OR LOWER(COALESCE(al.label,'')) IN ('maritime','naval','sailing'))
    )
    OR EXISTS (
        SELECT 1 FROM game_categories gc
        JOIN categories c ON c.id = gc.category_id
        LEFT JOIN alt_labels al ON al.entity_id = c.id
        WHERE gc.game_id = g.id
          AND (LOWER(c.label) LIKE '%nautical%' OR LOWER(COALESCE(al.label,'')) IN ('maritime','naval','sailing'))
    )
)
ORDER BY g.rating DESC LIMIT 20;

## Example — count shared games between two players (ownership overlap):
SELECT p2.label, COUNT(*) AS shared
FROM player_owns po1
JOIN players p1 ON p1.id = po1.player_id AND p1.label = 'Susanne Vejdemo'
JOIN player_owns po2 ON po2.game_id = po1.game_id
JOIN players p2 ON p2.id = po2.player_id
WHERE p2.label != 'Susanne Vejdemo'
GROUP BY p2.id, p2.label
ORDER BY shared DESC LIMIT 20;

## Example — transitive community detection (players reachable through shared ownership chains):
-- WITH RECURSIVE is required for arbitrary-depth graph traversal in SQLite.
-- IMPORTANT: Use UNION (not UNION ALL) so SQLite deduplicates automatically and halts
-- when no new rows are added. Do NOT reference the recursive CTE more than once per
-- recursive SELECT body (no 'NOT IN community' subqueries) — that causes an error.
WITH RECURSIVE community(player_id) AS (
    -- Seed: players who share at least one game with Susanne
    SELECT DISTINCT po2.player_id
    FROM player_owns po1
    JOIN players seed ON seed.id = po1.player_id AND seed.label = 'Susanne Vejdemo'
    JOIN player_owns po2 ON po2.game_id = po1.game_id
    WHERE po2.player_id != seed.id
    UNION
    -- Recurse: UNION (not UNION ALL) stops automatically when no new rows appear
    SELECT po2.player_id
    FROM community c
    JOIN player_owns po1 ON po1.player_id = c.player_id
    JOIN player_owns po2 ON po2.game_id = po1.game_id
)
SELECT p.label
FROM community c JOIN players p ON p.id = c.player_id
ORDER BY p.label;

## game_reimplements schema (mirrors game_expansions):
--   newer_id INTEGER (the reimplementation) → games.id
--   older_id INTEGER (the original)         → games.id
-- Use WITH RECURSIVE for transitive traversal (same pattern as community detection above).
-- Example — all games in a reimplementation family (starting from original game ID 9209):
WITH RECURSIVE family(game_id) AS (
    SELECT 9209  -- root: the original game
    UNION
    SELECT gr.newer_id
    FROM family f
    JOIN game_reimplements gr ON gr.older_id = f.game_id
)
SELECT g.name, g.rating
FROM family f JOIN games g ON g.id = f.game_id
ORDER BY g.rating DESC NULLS LAST;

## Example — games by a creator of something a player rates highly:
-- player_opinions.rating holds the personal rating; JOIN via hasOpinionOf (game_id).
SELECT DISTINCT g2.name, g2.rating FROM player_opinions pop
JOIN players p ON p.id = pop.player_id AND p.label = 'Susanne Vejdemo'
JOIN game_creators gc1 ON gc1.game_id = pop.game_id   -- creator of the liked game
JOIN game_creators gc2 ON gc2.creator_id = gc1.creator_id  -- other games by same creator
JOIN games g2 ON g2.id = gc2.game_id
WHERE pop.rating >= 8
  AND NOT EXISTS (SELECT 1 FROM player_owns po2 JOIN players p2 ON p2.id = po2.player_id
                  WHERE p2.label = 'Susanne Vejdemo' AND po2.game_id = g2.id)
ORDER BY g2.rating DESC LIMIT 20;
"""

SYSTEM_RESULT = """You are a helpful board game assistant. The user asked a question about board games. \
A database query was run and returned the following results. \
Answer the user's question naturally and helpfully based on these results. \
If there are no results, explain what that means. \
Include game names and ratings in your answer where relevant."""

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
def generate_sql(question: str, error_context: str = None) -> str:
    user_content = question
    if error_context:
        user_content = "\n\n".join([
            question,
            f"Your previous query failed:\n{error_context}",
            "Please write a corrected SQL query.",
        ])
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM_SQL,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_content}],
    )
    sql = response.content[0].text.strip()
    # Strip any accidental code fences
    if sql.startswith("```"):
        sql = "\n".join(l for l in sql.splitlines()
                        if not l.startswith("```")).strip()
    return sql


def execute_sql(sql: str) -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        con.close()
    return rows


def interpret_results(question: str, sql: str, rows: list[dict]) -> str:
    payload = {
        "question":     question,
        "sql_query":    sql,
        "result_count": len(rows),
        "results":      rows[:50],
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

    sql = generate_sql(question)
    print("Generated SQL:")
    print(sql)
    print()

    for attempt in range(max_retries + 1):
        try:
            rows = execute_sql(sql)
            break
        except Exception as e:
            error_msg = str(e)
            print(f"  SQL error (attempt {attempt+1}): {error_msg}")
            if attempt < max_retries:
                sql = generate_sql(question, error_msg)
                print("  Retrying with revised query:")
                print(sql)
                print()
            else:
                print("  All retries exhausted.")
                raise

    print(f"Results: {len(rows)} row(s)")
    print()

    answer = interpret_results(question, sql, rows)
    _log(question_id, question, answer)

    print("Answer:")
    print(answer.encode("ascii", errors="replace").decode())
    return answer


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not Path(DB_PATH).exists():
        sys.exit(f"{DB_PATH} not found — run bgg_build_sqlite.py first")
    for qid, question in QUESTIONS:
        ask(qid, question)
    print(f"\n{'='*70}")
    print("Done. Results logged to", LOG_FILE)
