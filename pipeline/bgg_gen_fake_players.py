"""
Generate a new fake_players.ttl with taste-clustered fake players.

5 clusters x 40 players = 200 new fake players with structured ownership.
Gertrude Young and Maja Brown are preserved verbatim from the existing file.
Susanne Vejdemo lives in bgg_main.ttl and is NOT touched here.

Expected result: same-cluster player pairs share ~3-4 games on average,
creating a real social graph structure for QSQL6 (transitive neighbor query).

Usage:
    python bgg_gen_fake_players.py
"""
import io, random, re, sqlite3, sys, unicodedata
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

random.seed(42)

DB_PATH  = "bgg.db"
SRC_PATH = "fake_players.ttl"
OUT_PATH = "fake_players.ttl"

# ── Cluster definitions ────────────────────────────────────────────────────────
CLUSTER_DEFS = {
    "Strategy": {"categories": ["AbstractStrategy", "Economic"],           "pool_size": 200},
    "Coop":     {"mechanics":  ["CooperativeGame"],                        "pool_size": 150},
    "Party":    {"categories": ["PartyGame", "Bluffing"],                  "pool_size": 150},
    "Family":   {"categories": ["ChildrensGame"],                          "pool_size": 150},
    "Thematic": {"categories": ["Adventure", "Fantasy", "ScienceFiction"], "pool_size": 200},
}

PLAYERS_PER_CLUSTER = 40
CLUSTER_GAMES       = 24   # games per player from their cluster pool
RANDOM_GAMES        = 6    # extra games from the general pool
MIN_RATING          = 6.0  # floor for general random pool

MENTAL_LOADS = ["bgg:easy", "bgg:moderate", "bgg:difficult"]

# Cluster-specific base rating tendencies (players tend to rate within-cluster games higher)
CLUSTER_RATING_BIAS = {
    "Strategy": (7, 10),
    "Coop":     (7, 10),
    "Party":    (6, 10),
    "Family":   (6, 9),
    "Thematic": (6, 10),
}
RANDOM_RATING_RANGE = (4, 9)

# ── Name pools (diverse international) ────────────────────────────────────────
FIRST_NAMES = [
    "Akiko", "Alejandro", "Anders", "Andrei", "Anna", "Arjun", "Astrid", "Barbara",
    "Betty", "Björn", "Britta", "Carlos", "Carmen", "Charles", "Claire", "Céline",
    "Daniel", "David", "Diego", "Emma", "Erik", "Fatima", "François", "Friedrich",
    "Gertrude", "Gunnar", "Gustav", "Hana", "Hans", "Helga", "Henri", "Hildegard",
    "Hiroshi", "Ingrid", "Isabel", "Isabelle", "James", "Jean", "Jessica", "Johan",
    "John", "José", "Karen", "Kenji", "Klaus", "Kristina", "Kwame", "Lars",
    "Leila", "Lena", "Linda", "Lisa", "Louis", "Lucia", "Maja", "Margaret",
    "Maria", "Marie", "Mark", "Mary", "Matthew", "Mei", "Mika", "Monika",
    "Nancy", "Naomi", "Natasha", "Oskar", "Paul", "Pierre", "Priya", "Rafael",
    "Richard", "Robert", "Ryo", "Sandra", "Sara", "Sarah", "Sigrid", "Sofia",
    "Susan", "Sven", "Tariq", "Thomas", "Ulf", "Ursula", "Walter", "Wei",
    "William", "Wolfgang", "Yuki", "Amara", "Fatou", "Kofi", "Nadia", "Omar",
    "Zara", "Elif", "Min", "Nour", "Takeshi", "Valentina", "Miriam", "Lorenzo",
]

LAST_NAMES = [
    "Petit", "Martinez", "Patel", "Torres", "Dubois", "Lopez", "Okafor", "Sato",
    "Schneider", "Johansson", "Lindqvist", "Adams", "Ito", "Schmidt", "Smith",
    "Baker", "Bergstrom", "Fischer", "Rodriguez", "Lindberg", "Jones", "Chen",
    "Svensson", "Larsson", "Harris", "Nkrumah", "Hassan", "Yamamoto", "Allen",
    "Lewis", "Miller", "Sanchez", "Magnusson", "Tanaka", "Watanabe", "Sharma",
    "Singh", "Bernard", "Nilsson", "Hernandez", "Perez", "Martin", "Nakamura",
    "Becker", "Roux", "Laurent", "Garcia", "Gustafsson", "Williams", "Kobayashi",
    "Koch", "Lee", "Muller", "Olsson", "King", "Moreau", "Girard", "Taylor",
    "White", "Wilson", "Thompson", "Clark", "Ivanov", "Persson", "Eriksson",
    "Hoffmann", "Kato", "Kim", "Weber", "Schulz", "Suzuki", "Pettersson",
    "Robinson", "Gonzalez", "Mensah", "Axelsson", "Dupont", "Nguyen", "Yoshida",
    "Lundgren", "Ekstrom", "Lindahl", "Hansson", "Carlsson", "Petersen", "Nielsen",
    "Hansen", "Andersen", "Ivanova", "Popova", "Kozlov", "Novak", "Hajek",
    "Kovac", "Popescu", "Ionescu", "Papadopoulos", "Fernandez", "Rossi", "Ferrari",
]


def to_iri(first: str, last: str) -> str:
    """camelCase IRI slug: 'Björn Müller' -> 'BjornMuller'"""
    name = first + last
    # Normalize unicode: decompose then strip combining chars
    nfd = unicodedata.normalize("NFD", name)
    ascii_name = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    # Keep only letters and digits
    return re.sub(r"[^A-Za-z0-9]", "", ascii_name)


def generate_names(n: int, reserved: set[str]) -> list[tuple[str, str, str]]:
    """Return list of (label, iri, cluster_hint) — just (label, iri) here."""
    pairs = []
    seen_iris = set(reserved)
    attempts = 0
    while len(pairs) < n and attempts < 100_000:
        attempts += 1
        first = random.choice(FIRST_NAMES)
        last  = random.choice(LAST_NAMES)
        label = f"{first} {last}"
        iri   = to_iri(first, last)
        if iri not in seen_iris:
            seen_iris.add(iri)
            pairs.append((label, iri))
    if len(pairs) < n:
        raise RuntimeError(f"Could only generate {len(pairs)}/{n} unique names")
    return pairs


def get_cluster_pool(con: sqlite3.Connection, cdef: dict, pool_size: int) -> list[int]:
    """Return top-rated game IDs matching cluster criteria."""
    cats = cdef.get("categories", [])
    mechs = cdef.get("mechanics", [])
    if cats:
        ph = ",".join("?" * len(cats))
        rows = con.execute(f"""
            SELECT DISTINCT g.id FROM games g
            JOIN game_categories gc ON gc.game_id = g.id
            WHERE gc.category_id IN ({ph}) AND g.rating IS NOT NULL
            ORDER BY g.rating DESC LIMIT ?
        """, cats + [pool_size]).fetchall()
    else:
        ph = ",".join("?" * len(mechs))
        rows = con.execute(f"""
            SELECT DISTINCT g.id FROM games g
            JOIN game_mechanics gm ON gm.game_id = g.id
            WHERE gm.mechanic_id IN ({ph}) AND g.rating IS NOT NULL
            ORDER BY g.rating DESC LIMIT ?
        """, mechs + [pool_size]).fetchall()
    return [r[0] for r in rows]


def get_random_pool(con: sqlite3.Connection, min_rating: float) -> list[int]:
    rows = con.execute(
        "SELECT id FROM games WHERE rating >= ? ORDER BY rating DESC",
        (min_rating,)
    ).fetchall()
    return [r[0] for r in rows]


def extract_preserved_blocks(src_path: str) -> tuple[str, str]:
    """Extract Gertrude Young and Maja Brown's opinion + player blocks verbatim."""
    lines = Path(src_path).read_text(encoding="utf-8").splitlines()
    gy_opinions, mb_opinions = [], []
    gy_player,   mb_player   = [], []

    i = 0
    while i < len(lines):
        line = lines[i]
        # Opinion blocks: collect until blank line after block
        if line.startswith("fake:Gertrudeyoung_opinion_"):
            block = []
            while i < len(lines) and lines[i].strip():
                block.append(lines[i])
                i += 1
            gy_opinions.append("\n".join(block))
            continue
        if line.startswith("fake:Majabrown_opinion_"):
            block = []
            while i < len(lines) and lines[i].strip():
                block.append(lines[i])
                i += 1
            mb_opinions.append("\n".join(block))
            continue
        # Player entity blocks
        if line.startswith("fake:Gertrudeyoung ") and "a bgg:Player" in line:
            block = []
            while i < len(lines) and (lines[i].strip() or block == []):
                if lines[i].strip():
                    block.append(lines[i])
                i += 1
            gy_player = block
            continue
        if line.startswith("fake:Majabrown ") and "a bgg:Player" in line:
            block = []
            while i < len(lines) and (lines[i].strip() or block == []):
                if lines[i].strip():
                    block.append(lines[i])
                i += 1
            mb_player = block
            continue
        i += 1

    opinions_ttl = "\n\n".join(gy_opinions + mb_opinions)
    player_ttl   = "\n".join(gy_player) + "\n\n" + "\n".join(mb_player)
    return opinions_ttl, player_ttl


def make_opinion_ttl(iri: str, game_id: int, rating: float, mental_load: str) -> str:
    return (
        f"fake:{iri}_opinion_{game_id} a bgg:PlayerOpinion ;\n"
        f"    bgg:hasMentalLoad {mental_load} ;\n"
        f"    bgg:hasOpinionHolder fake:{iri} ;\n"
        f"    bgg:hasOpinionOf bgg:{game_id} ;\n"
        f"    bgg:hasPlayerRatingOpinion {rating:.1f} ."
    )


def make_player_ttl(label: str, iri: str, game_ids: list[int]) -> str:
    sorted_ids = sorted(game_ids)
    ownership  = ",\n        ".join(f"bgg:{gid}" for gid in sorted_ids)
    return (
        f'fake:{iri} a bgg:Player ;\n'
        f'    rdfs:label "{label}"@en ;\n'
        f'    bgg:hasOwnershipOf {ownership} .'
    )


def main():
    con = sqlite3.connect(DB_PATH)

    # ── Build cluster game pools ───────────────────────────────────────────────
    cluster_pools: dict[str, list[int]] = {}
    for cluster, cdef in CLUSTER_DEFS.items():
        pool = get_cluster_pool(con, cdef, cdef["pool_size"])
        cluster_pools[cluster] = pool
        print(f"{cluster} pool: {len(pool)} games")

    random_pool = get_random_pool(con, MIN_RATING)
    print(f"Random pool (rating >= {MIN_RATING}): {len(random_pool)} games")
    con.close()

    # ── Generate players: 40 per cluster ──────────────────────────────────────
    clusters = list(CLUSTER_DEFS.keys())
    total_players = PLAYERS_PER_CLUSTER * len(clusters)

    # Reserve Gertrude and Maja IRIs so we don't collide
    reserved = {"Gertrudeyoung", "Majabrown"}
    all_names = generate_names(total_players, reserved)
    print(f"Generated {len(all_names)} unique player names")

    # Assign names to clusters (blocks of 40)
    cluster_players: dict[str, list[tuple[str, str]]] = {}
    idx = 0
    for cluster in clusters:
        cluster_players[cluster] = all_names[idx: idx + PLAYERS_PER_CLUSTER]
        idx += PLAYERS_PER_CLUSTER

    # ── Build TTL content ─────────────────────────────────────────────────────
    opinion_blocks: list[tuple[str, str]] = []   # (sort_key, ttl_text)
    player_blocks:  list[tuple[str, str]] = []   # (sort_key, ttl_text)

    for cluster, players in cluster_players.items():
        pool = cluster_pools[cluster]
        rlo, rhi = CLUSTER_RATING_BIAS[cluster]

        for label, iri in players:
            # Pick cluster games (without replacement) + random games
            cluster_sample = random.sample(pool, min(CLUSTER_GAMES, len(pool)))
            # Random games from general pool, exclude already-chosen
            chosen_set   = set(cluster_sample)
            random_extra = [g for g in random.sample(random_pool, min(RANDOM_GAMES * 5, len(random_pool)))
                            if g not in chosen_set][:RANDOM_GAMES]
            all_games = cluster_sample + random_extra

            # Opinions
            for gid in all_games:
                if gid in cluster_sample:
                    rating = float(random.randint(rlo, rhi))
                else:
                    rating = float(random.randint(*RANDOM_RATING_RANGE))
                ml = random.choice(MENTAL_LOADS)
                block = make_opinion_ttl(iri, gid, rating, ml)
                sort_key = f"{iri}_opinion_{gid:09d}"
                opinion_blocks.append((sort_key, block))

            # Player entity
            player_blocks.append((iri.lower(), make_player_ttl(label, iri, all_games)))

    # Sort both sections alphabetically by IRI
    opinion_blocks.sort(key=lambda x: x[0].lower())
    player_blocks.sort(key=lambda x: x[0])

    # ── Extract preserved Gertrude + Maja blocks ───────────────────────────────
    print("Extracting Gertrude Young and Maja Brown blocks from existing file...")
    preserved_opinions, preserved_players = extract_preserved_blocks(SRC_PATH)

    # ── Write output ───────────────────────────────────────────────────────────
    header = """\
@prefix bgg: <https://raw.githubusercontent.com/susvej/bg_ontology/> .
@prefix fake: <https://vejdemo.se/boardgames/fake#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""

    # Merge generated opinions with preserved opinions
    # Preserved blocks are verbatim; we insert them in sort order
    all_opinion_text = "\n\n".join(b for _, b in opinion_blocks)
    all_player_text  = "\n\n".join(b for _, b in player_blocks)

    output = (
        header + "\n"
        + all_opinion_text + "\n\n"
        + preserved_opinions + "\n\n"
        + all_player_text + "\n\n"
        + preserved_players + "\n"
    )

    Path(OUT_PATH).write_text(output, encoding="utf-8")

    n_players = total_players + 2  # +2 for Gertrude and Maja
    n_opinions = len(opinion_blocks)
    print(f"\nWrote {OUT_PATH}")
    print(f"  {n_players} fake players ({total_players} clustered + Gertrude Young + Maja Brown)")
    print(f"  {n_opinions} new opinion triples")
    print(f"  {PLAYERS_PER_CLUSTER} players per cluster x {len(clusters)} clusters = {total_players} new players")
    for cluster, players in cluster_players.items():
        pool_size = len(cluster_pools[cluster])
        print(f"  {cluster}: {len(players)} players, pool={pool_size}")


if __name__ == "__main__":
    main()
