"""
Patch fake_players.ttl to add bgg:likesCategory and bgg:likesMechanic to each player.

For each player, looks at every game they own, counts how often each category
and mechanic appears across their collection (via bgg.db), and assigns the top
4-6 of each as the player's stated preferences.

Run from the repo root:
    python pipeline/bgg_add_player_likes.py
"""
import re, sqlite3, sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH  = "bgg.db"
TTL_PATH = "data/fake_players.ttl"

# ── Load player→games from TTL (regex; no rdflib dep) ─────────────────────────
# Player blocks look like:
#   fake:AkikoDupont a bgg:Player ;
#       rdfs:label "Akiko Dupont"@en ;
#       bgg:hasOwnershipOf bgg:483,
#           bgg:492, ...
#           bgg:272599 .

text = Path(TTL_PATH).read_text(encoding="utf-8")

# Split into blank-line-separated blocks
blocks = re.split(r"\n{2,}", text.strip())

def parse_player_block(block: str) -> tuple[str, list[int]] | None:
    """Return (iri_suffix, [game_ids]) if this is a bgg:Player block, else None."""
    first = block.strip().split("\n")[0]
    m = re.match(r"fake:(\w+) a bgg:Player\b", first)
    if not m:
        return None
    iri = m.group(1)
    game_ids = [int(x) for x in re.findall(r"bgg:(\d+)", block)]
    return iri, game_ids

player_games: dict[str, list[int]] = {}
for block in blocks:
    result = parse_player_block(block)
    if result:
        iri, gids = result
        player_games[iri] = gids

print(f"Parsed {len(player_games)} player blocks from TTL")

# ── Query bgg.db for category/mechanic counts ─────────────────────────────────
con = sqlite3.connect(DB_PATH)

def top_likes(game_ids: list[int], table: str, col: str,
              n_min: int = 4, n_max: int = 6) -> list[str]:
    if not game_ids:
        return []
    ph = ",".join("?" * len(game_ids))
    rows = con.execute(
        f"SELECT {col} FROM {table} WHERE game_id IN ({ph})",
        game_ids,
    ).fetchall()
    counts = Counter(r[0] for r in rows if r[0])
    if not counts:
        return []
    # Take between n_min and n_max entries; cap at actual distinct count
    top = counts.most_common(n_max)
    # Minimum: take at least n_min if available
    n = max(n_min, min(n_max, len(top)))
    return [name for name, _ in top[:n]]

player_likes: dict[str, tuple[list[str], list[str]]] = {}
for iri, gids in player_games.items():
    cats  = top_likes(gids, "game_categories", "category_id")
    mechs = top_likes(gids, "game_mechanics",  "mechanic_id")
    player_likes[iri] = (cats, mechs)

con.close()

# Sanity check
sample = list(player_likes.items())[:3]
for iri, (cats, mechs) in sample:
    print(f"  {iri}: cats={cats}, mechs={mechs[:3]}...")

# ── Build Turtle lines for the two properties ─────────────────────────────────
def format_prop_lines(prop: str, names: list[str], terminal: str) -> list[str]:
    """Return Turtle lines for a property with a list of bgg: IRIs."""
    if not names:
        return []
    iris = [f"bgg:{n}" for n in names]
    if len(iris) == 1:
        return [f"    {prop} {iris[0]} {terminal}"]
    lines = [f"    {prop} {iris[0]},"]
    for iri in iris[1:-1]:
        lines.append(f"        {iri},")
    lines.append(f"        {iris[-1]} {terminal}")
    return lines

# ── Patch each player block ────────────────────────────────────────────────────
def patch_block(block: str) -> str:
    result = parse_player_block(block)
    if result is None:
        return block
    iri, _ = result
    cats, mechs = player_likes.get(iri, ([], []))
    if not cats and not mechs:
        return block

    lines = block.strip().split("\n")

    # The block already ends with '.' — we need to change that last '.' to ';'
    # and append the likes.
    # Find the last line that ends with ' .' or '.'
    last_idx = len(lines) - 1
    while last_idx >= 0 and not lines[last_idx].strip().endswith("."):
        last_idx -= 1
    if last_idx < 0:
        return block  # unexpected format; leave unchanged

    last = lines[last_idx]
    # Already has likes? Skip (idempotent re-run guard)
    if "likesCategory" in block or "likesMechanic" in block:
        return block

    # Replace terminal '.' with ';'
    lines[last_idx] = last.rstrip()[:-1] + ";"

    # Append likes lines; last property closes with '.'
    if mechs:
        lines.extend(format_prop_lines("bgg:likesCategory", cats, ";"))
        lines.extend(format_prop_lines("bgg:likesMechanic", mechs, "."))
    else:
        lines.extend(format_prop_lines("bgg:likesCategory", cats, "."))

    return "\n".join(lines)

patched_blocks = [patch_block(b) for b in blocks]
new_text = "\n\n".join(patched_blocks) + "\n"
Path(TTL_PATH).write_text(new_text, encoding="utf-8")

n_patched = sum(
    1 for iri in player_likes
    if player_likes[iri][0] or player_likes[iri][1]
)
print(f"\nPatched {n_patched} player blocks")
print(f"Wrote {TTL_PATH}")
