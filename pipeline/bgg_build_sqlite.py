"""
Build bgg.db (SQLite) by parsing TTL files directly with rdflib.
No GraphDB instance required. Run once; output is bgg.db in the project root.

Source files:
  bgg_main.ttl      — 21,379 base games + 11,726 expansions + T-BOX + designer data (all merged)
  fake_players.ttl  — 201 players with ownership and opinions
"""
import re, sqlite3, sys, time
from pathlib import Path
from rdflib import Dataset, Namespace, RDF, RDFS
from rdflib.namespace import SKOS

TTL_FILES = ["bgg_main.ttl", "fake_players.ttl"]
DB_PATH   = "bgg.db"

BGG   = Namespace("https://raw.githubusercontent.com/susvej/bg_ontology/")
TRENJ = Namespace("https://vejdemo.se/boardgames/threnjen#")
SVJ   = Namespace("https://vejdemo.se/boardgames#")
FAKE  = Namespace("https://vejdemo.se/boardgames/fake#")

BGG_BASE  = str(BGG)
SVJ_BASE  = str(SVJ)
FAKE_BASE = str(FAKE)

# ── Schema ────────────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id               INTEGER PRIMARY KEY,
    name             TEXT    NOT NULL,
    year             INTEGER,
    rating           REAL,
    geek_rating      REAL,
    min_players      INTEGER,
    max_players      INTEGER,
    best_num_players INTEGER,
    min_time         INTEGER,
    max_time         INTEGER,
    min_rec_age      INTEGER,
    size             TEXT,
    description      TEXT
);

CREATE TABLE IF NOT EXISTS mechanics (
    id    TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id    TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS themes (
    id    TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS creators (
    id    TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publishers (
    id    TEXT PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    id        TEXT PRIMARY KEY,
    label     TEXT NOT NULL,
    namespace TEXT NOT NULL
);

/* One row per (entity, altLabel) — covers mechanics, categories, themes */
CREATE TABLE IF NOT EXISTS alt_labels (
    entity_id TEXT NOT NULL,
    label     TEXT NOT NULL,
    PRIMARY KEY (entity_id, label)
);

CREATE TABLE IF NOT EXISTS game_mechanics (
    game_id     INTEGER NOT NULL REFERENCES games(id),
    mechanic_id TEXT    NOT NULL REFERENCES mechanics(id),
    PRIMARY KEY (game_id, mechanic_id)
);

CREATE TABLE IF NOT EXISTS game_categories (
    game_id     INTEGER NOT NULL REFERENCES games(id),
    category_id TEXT    NOT NULL REFERENCES categories(id),
    PRIMARY KEY (game_id, category_id)
);

CREATE TABLE IF NOT EXISTS game_themes (
    game_id  INTEGER NOT NULL REFERENCES games(id),
    theme_id TEXT    NOT NULL REFERENCES themes(id),
    PRIMARY KEY (game_id, theme_id)
);

CREATE TABLE IF NOT EXISTS game_creators (
    game_id    INTEGER NOT NULL REFERENCES games(id),
    creator_id TEXT    NOT NULL REFERENCES creators(id),
    PRIMARY KEY (game_id, creator_id)
);

CREATE TABLE IF NOT EXISTS game_publishers (
    game_id      INTEGER NOT NULL REFERENCES games(id),
    publisher_id TEXT    NOT NULL REFERENCES publishers(id),
    PRIMARY KEY (game_id, publisher_id)
);

CREATE TABLE IF NOT EXISTS player_owns (
    player_id TEXT    NOT NULL REFERENCES players(id),
    game_id   INTEGER NOT NULL REFERENCES games(id),
    PRIMARY KEY (player_id, game_id)
);

CREATE TABLE IF NOT EXISTS player_opinions (
    player_id   TEXT    NOT NULL REFERENCES players(id),
    game_id     INTEGER NOT NULL REFERENCES games(id),
    rating      REAL,
    mental_load TEXT,
    PRIMARY KEY (player_id, game_id)
);

CREATE TABLE IF NOT EXISTS game_expansions (
    expansion_id INTEGER NOT NULL REFERENCES games(id),
    base_id      INTEGER NOT NULL REFERENCES games(id),
    PRIMARY KEY (expansion_id, base_id)
);

CREATE TABLE IF NOT EXISTS game_reimplements (
    newer_id INTEGER NOT NULL REFERENCES games(id),
    older_id INTEGER NOT NULL REFERENCES games(id),
    PRIMARY KEY (newer_id, older_id)
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_gm_mechanic   ON game_mechanics(mechanic_id);
CREATE INDEX IF NOT EXISTS idx_gc_category   ON game_categories(category_id);
CREATE INDEX IF NOT EXISTS idx_gt_theme      ON game_themes(theme_id);
CREATE INDEX IF NOT EXISTS idx_gcr_creator   ON game_creators(creator_id);
CREATE INDEX IF NOT EXISTS idx_gp_publisher  ON game_publishers(publisher_id);
CREATE INDEX IF NOT EXISTS idx_po_player     ON player_owns(player_id);
CREATE INDEX IF NOT EXISTS idx_po_game       ON player_owns(game_id);
CREATE INDEX IF NOT EXISTS idx_pop_player    ON player_opinions(player_id);
CREATE INDEX IF NOT EXISTS idx_pop_game      ON player_opinions(game_id);
CREATE INDEX IF NOT EXISTS idx_games_rating  ON games(rating DESC);
CREATE INDEX IF NOT EXISTS idx_players_label ON players(label);
CREATE INDEX IF NOT EXISTS idx_alt_label     ON alt_labels(label);
CREATE INDEX IF NOT EXISTS idx_exp_base      ON game_expansions(base_id);
CREATE INDEX IF NOT EXISTS idx_reimpl_older  ON game_reimplements(older_id);
"""

# ── Helpers ───────────────────────────────────────────────────────────────────
def local_id(iri) -> str:
    return re.split(r"[/#]", str(iri))[-1]

def game_id(iri) -> int | None:
    s = str(iri)
    if not s.startswith(BGG_BASE):
        return None
    try:
        return int(s[len(BGG_BASE):])
    except ValueError:
        return None

def val(g, subj, pred, cast=str):
    v = g.value(subj, pred)
    if v is None:
        return None
    try:
        return cast(v)
    except (ValueError, TypeError):
        return None

# ── Main ──────────────────────────────────────────────────────────────────────
def build():
    # 1. Load TTLs ─────────────────────────────────────────────────────────────
    g = Dataset()
    for ttl in TTL_FILES:
        p = Path(ttl)
        if not p.exists():
            print(f"  WARNING: {ttl} not found — skipping")
            continue
        t0 = time.time()
        print(f"Parsing {ttl} ...", end=" ", flush=True)
        g.parse(str(p), format="turtle")
        print(f"{len(g):,} triples ({time.time()-t0:.1f}s)")
    print(f"Total: {len(g):,} triples\n")

    # 2. Create DB ─────────────────────────────────────────────────────────────
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)

    # 3. Vocabulary: mechanics, categories, themes, creators, publishers ────────
    print("Extracting vocabulary...")

    mech_rows, cat_rows, theme_rows = [], [], []
    creator_rows, publisher_rows, alt_rows = [], [], []

    for m in g.subjects(RDF.type, BGG.Mechanic):
        lbl = val(g, m, RDFS.label)
        if lbl:
            mid = local_id(m)
            mech_rows.append((mid, lbl))
            for alt in g.objects(m, SKOS.altLabel):
                alt_rows.append((mid, str(alt)))

    for c in g.subjects(RDF.type, BGG.Category):
        lbl = val(g, c, RDFS.label)
        if lbl:
            cid = local_id(c)
            cat_rows.append((cid, lbl))
            for alt in g.objects(c, SKOS.altLabel):
                alt_rows.append((cid, str(alt)))

    for t in g.subjects(RDF.type, TRENJ.Theme):
        lbl = val(g, t, RDFS.label)
        if lbl:
            tid = local_id(t)
            theme_rows.append((tid, lbl))
            for alt in g.objects(t, SKOS.altLabel):
                alt_rows.append((tid, str(alt)))

    for cr in g.subjects(RDF.type, BGG.Creator):
        lbl = val(g, cr, RDFS.label)
        if lbl:
            creator_rows.append((local_id(cr), lbl))

    for pub in g.subjects(RDF.type, BGG.Publisher):
        lbl = val(g, pub, RDFS.label)
        if lbl:
            publisher_rows.append((local_id(pub), lbl))

    con.executemany("INSERT OR IGNORE INTO mechanics  VALUES (?,?)", mech_rows)
    con.executemany("INSERT OR IGNORE INTO categories VALUES (?,?)", cat_rows)
    con.executemany("INSERT OR IGNORE INTO themes     VALUES (?,?)", theme_rows)
    con.executemany("INSERT OR IGNORE INTO creators   VALUES (?,?)", creator_rows)
    con.executemany("INSERT OR IGNORE INTO publishers VALUES (?,?)", publisher_rows)
    con.executemany("INSERT OR IGNORE INTO alt_labels VALUES (?,?)", alt_rows)
    con.commit()
    print(f"  {len(mech_rows)} mechanics ({len([r for r in alt_rows if r[0] in dict(mech_rows)])} altLabels)")
    print(f"  {len(cat_rows)} categories")
    print(f"  {len(theme_rows)} themes")
    print(f"  {len(creator_rows)} creators")
    print(f"  {len(publisher_rows)} publishers")
    print(f"  {len(alt_rows)} alt_labels total")

    # 4. Games + junction tables ───────────────────────────────────────────────
    print("Extracting games + junctions...")

    game_rows = []
    gm_rows, gc_rows, gt_rows, gcr_rows, gp_rows = [], [], [], [], []
    game_ids = set()
    creator_ids  = {r[0] for r in creator_rows}
    publisher_ids = {r[0] for r in publisher_rows}

    for game in g.subjects(RDF.type, BGG.Game):
        gid = game_id(game)
        if gid is None:
            continue
        name = val(g, game, BGG.hasName)
        if name is None:
            continue
        if gid in game_ids:
            continue
        game_ids.add(gid)

        # Size IRIs have no rdfs:label — use the local name capitalized
        size_iri = g.value(game, BGG.hasSize)
        size_lbl = local_id(size_iri).capitalize() if size_iri else None

        game_rows.append((
            gid,
            name,
            val(g, game, BGG.hasYearPublished,  int),
            val(g, game, BGG.hasRating,          float),
            val(g, game, BGG.hasGeekRating,      float),
            val(g, game, BGG.hasMinPlayers,      int),
            val(g, game, BGG.hasMaxPlayers,      int),
            val(g, game, BGG.hasBestNumPlayers,  int),
            val(g, game, BGG.hasMinGameTime,     int),
            val(g, game, BGG.hasMaxGameTime,     int),
            val(g, game, BGG.hasMinRecAge,       int),
            size_lbl,
            val(g, game, BGG.hasDescription),
        ))

        for m in g.objects(game, BGG.hasMechanic):
            gm_rows.append((gid, local_id(m)))
        for c in g.objects(game, BGG.hasCategory):
            gc_rows.append((gid, local_id(c)))
        for t in g.objects(game, TRENJ.hasTheme):
            gt_rows.append((gid, local_id(t)))
        for cr in g.objects(game, BGG.hasCreator):
            cid = local_id(cr)
            if cid in creator_ids:
                gcr_rows.append((gid, cid))
        for pub in g.objects(game, BGG.hasPublisher):
            pid = local_id(pub)
            if pid in publisher_ids:
                gp_rows.append((gid, pid))

        if len(game_rows) % 5000 == 0:
            print(f"    ... {len(game_rows):,} games", end="\r")

    con.executemany("INSERT OR IGNORE INTO games           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", game_rows)
    con.executemany("INSERT OR IGNORE INTO game_mechanics  VALUES (?,?)", gm_rows)
    con.executemany("INSERT OR IGNORE INTO game_categories VALUES (?,?)", gc_rows)
    con.executemany("INSERT OR IGNORE INTO game_themes     VALUES (?,?)", gt_rows)
    con.executemany("INSERT OR IGNORE INTO game_creators   VALUES (?,?)", gcr_rows)
    con.executemany("INSERT OR IGNORE INTO game_publishers VALUES (?,?)", gp_rows)
    con.commit()
    print(f"  {len(game_rows):,} games")
    print(f"  {len(gm_rows):,} game_mechanics, {len(gc_rows):,} game_categories, "
          f"{len(gt_rows):,} game_themes")
    print(f"  {len(gcr_rows):,} game_creators, {len(gp_rows):,} game_publishers")

    # 4b. Expansion relationships (bgg:isExpansionOf)
    gexp_rows = []
    for exp_game, base_game in g.subject_objects(BGG.isExpansionOf):
        exp_id  = game_id(exp_game)
        base_id = game_id(base_game)
        if exp_id in game_ids and base_id in game_ids:
            gexp_rows.append((exp_id, base_id))
    if gexp_rows:
        con.executemany("INSERT OR IGNORE INTO game_expansions VALUES (?,?)", gexp_rows)
        con.commit()
        print(f"  {len(gexp_rows):,} game_expansions (isExpansionOf)")

    # 4c. Reimplementation relationships (bgg:reimplements)
    greimpl_rows = []
    for newer_game, older_game in g.subject_objects(BGG.reimplements):
        newer_id = game_id(newer_game)
        older_id = game_id(older_game)
        if newer_id in game_ids and older_id in game_ids:
            greimpl_rows.append((newer_id, older_id))
    if greimpl_rows:
        con.executemany("INSERT OR IGNORE INTO game_reimplements VALUES (?,?)", greimpl_rows)
        con.commit()
        print(f"  {len(greimpl_rows):,} game_reimplements (reimplements)")

    # 5. Players, ownership, opinions ──────────────────────────────────────────
    print("Extracting players + ownership + opinions...")

    player_rows, po_rows, pop_rows = [], [], []

    for player in g.subjects(RDF.type, BGG.Player):
        lbl = val(g, player, RDFS.label)
        if lbl is None:
            continue
        s = str(player)
        ns  = "svj" if s.startswith(SVJ_BASE) else "fake"
        pid = local_id(player)
        player_rows.append((pid, lbl, ns))

        for owned in g.objects(player, BGG.hasOwnershipOf):
            gid = game_id(owned)
            if gid in game_ids:
                po_rows.append((pid, gid))

    for opinion in g.subjects(RDF.type, BGG.PlayerOpinion):
        holder = g.value(opinion, BGG.hasOpinionHolder)
        game   = g.value(opinion, BGG.hasOpinionOf)
        if holder is None or game is None:
            continue
        pid = local_id(holder)
        gid = game_id(game)
        if gid not in game_ids:
            continue
        rating  = val(g, opinion, BGG.hasPlayerRatingOpinion, float)
        ml_iri  = g.value(opinion, BGG.hasMentalLoad)
        ml_lbl  = local_id(ml_iri).capitalize() if ml_iri else None
        pop_rows.append((pid, gid, rating, ml_lbl))

    con.executemany("INSERT OR IGNORE INTO players         VALUES (?,?,?)",   player_rows)
    con.executemany("INSERT OR IGNORE INTO player_owns     VALUES (?,?)",     po_rows)
    con.executemany("INSERT OR IGNORE INTO player_opinions VALUES (?,?,?,?)", pop_rows)
    con.commit()
    print(f"  {len(player_rows)} players, {len(po_rows)} player_owns, "
          f"{len(pop_rows)} player_opinions")

    # 6. Indexes ───────────────────────────────────────────────────────────────
    print("Creating indexes...")
    con.executescript(INDEXES)
    con.commit()

    # 7. Summary ───────────────────────────────────────────────────────────────
    tables = [
        "games", "mechanics", "categories", "themes", "creators", "publishers",
        "players", "alt_labels",
        "game_mechanics", "game_categories", "game_themes",
        "game_creators", "game_publishers",
        "player_owns", "player_opinions",
        "game_expansions", "game_reimplements",
    ]
    print("\nDatabase summary:")
    for tbl in tables:
        n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:<22} {n:>9,}")
    con.close()

    size_mb = Path(DB_PATH).stat().st_size / 1_048_576
    print(f"\nDone — {DB_PATH} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    t0 = time.time()
    build()
    print(f"Total time: {time.time()-t0:.1f}s")
