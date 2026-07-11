"""
bgg_fetch_expansions.py

Two-phase fetch of expansion game data from the BGG geekdo API.

Phase 1: For the top N base games (by geek_rating), collect all expansion IDs
         from their `boardgameexpansion` links.

Phase 2: For every unique expansion ID discovered, fetch full game data
         (name, year, rating, players, time, mechanics, categories, creators,
         publishers, and which base game(s) it expands).

Output:
  bgg_expansions_patch.ttl   — new bgg:Game entities + bgg:isExpansionOf triples
  bgg_expansions_checkpoint.json  — resumable checkpoint (both phases)

Usage:
    python bgg_fetch_expansions.py [--top N]   (default: 2000)
    python bgg_fetch_expansions.py --write-only  (skip fetching, just (re)write TTL from checkpoint)
"""

import argparse, json, os, re, sqlite3, time, unicodedata
import requests

DB_PATH         = "../bgg.db"
PATCH_FILE      = "bgg_expansions_patch.ttl"
CHECKPOINT_FILE = "bgg_expansions_checkpoint.json"
ENV_FILE        = ".env"
BGG_LOGIN_URL   = "https://boardgamegeek.com/login/api/v1"
GEEKDO_ITEM_URL = "https://api.geekdo.com/api/geekitems"
REQUEST_DELAY   = 1.0
LOG_EVERY       = 50

BGG_NS   = "https://raw.githubusercontent.com/susvej/bg_ontology/"
RDF_NS   = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS_NS  = "http://www.w3.org/2000/01/rdf-schema#"
XSD_NS   = "http://www.w3.org/2001/XMLSchema#"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "BGG-Ontology-Expansion-Fill/1.0"})


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_env() -> dict:
    env = {}
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def login(username: str, password: str) -> bool:
    print(f"Logging in as {username} …", end=" ", flush=True)
    r = SESSION.post(
        BGG_LOGIN_URL,
        json={"credentials": {"username": username, "password": password}},
        timeout=30,
    )
    ok = r.status_code in (200, 204)
    print("OK" if ok else f"FAILED ({r.status_code})")
    return ok


def label_to_iri(label: str) -> str:
    """Convert a label to a camelCase IRI local name.

    'Hand Management'       → 'HandManagement'
    'Route/Network Building'→ 'RouteNetworkBuilding'
    'Uwe Rosenberg'         → 'UweRosenberg'
    """
    normalized = unicodedata.normalize("NFD", label)
    ascii_str  = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    words = re.split(r"[\s\-/]+", ascii_str)
    parts = []
    for word in words:
        word = word.capitalize()
        word = re.sub(r"[^A-Za-z0-9]", "", word)
        if word:
            parts.append(word)
    return "".join(parts)


def escape_ttl(s: str) -> str:
    """Escape a string for use inside a Turtle double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


# ── DB lookups ────────────────────────────────────────────────────────────────

def load_db_lookups(top_n: int) -> tuple[list[int], set[int], dict, dict, dict, dict]:
    """Return:
      top_ids      — list of top-N base game IDs by geek_rating
      all_game_ids — set of all base game IDs in db
      mech_iri     — {lower(label): iri_local}  for existing mechanics
      cat_iri      — {lower(label): iri_local}  for existing categories
      creator_iri  — {lower(label): iri_local}  for existing creators
      pub_iri      — {lower(label): iri_local}  for existing publishers
    """
    con = sqlite3.connect(DB_PATH)

    top_ids = [r[0] for r in con.execute(
        "SELECT id FROM games WHERE geek_rating IS NOT NULL "
        "ORDER BY geek_rating DESC LIMIT ?", (top_n,)
    )]
    all_game_ids = {r[0] for r in con.execute("SELECT id FROM games")}

    mech_iri    = {r[1].lower(): r[0] for r in con.execute("SELECT id, label FROM mechanics")}
    cat_iri     = {r[1].lower(): r[0] for r in con.execute("SELECT id, label FROM categories")}
    creator_iri = {r[1].lower(): r[0] for r in con.execute("SELECT id, label FROM creators")}
    pub_iri     = {r[1].lower(): r[0] for r in con.execute("SELECT id, label FROM publishers")}

    con.close()
    print(f"DB: {len(top_ids)} top games | {len(all_game_ids):,} total base games")
    print(f"    {len(mech_iri)} mechanics | {len(cat_iri)} categories | "
          f"{len(creator_iri)} creators | {len(pub_iri)} publishers")
    return top_ids, all_game_ids, mech_iri, cat_iri, creator_iri, pub_iri


# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    if not os.path.exists(CHECKPOINT_FILE):
        return {"phase1_done": False, "phase1_processed": [], "expansion_ids": [],
                "phase2_processed": [], "games": {}}
    with open(CHECKPOINT_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_checkpoint(cp: dict) -> None:
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(cp, f)


# ── API fetching ──────────────────────────────────────────────────────────────

def _get_item(game_id: int) -> dict:
    r = SESSION.get(
        GEEKDO_ITEM_URL,
        params={"objectid": game_id, "objecttype": "thing"},
        timeout=20,
    )
    if r.status_code != 200:
        return {}
    return r.json().get("item", {})


def fetch_expansion_ids(base_id: int) -> list[int]:
    """Return list of BGG IDs that are expansions of this base game."""
    item  = _get_item(base_id)
    links = item.get("links", {})
    ids   = []
    for e in links.get("boardgameexpansion", []):
        oid = e.get("objectid") or e.get("id")
        if oid:
            ids.append(int(oid))
    return ids


def fetch_expansion_data(exp_id: int) -> dict | None:
    """Fetch full game data for an expansion. Returns None on failure."""
    try:
        item  = _get_item(exp_id)
        if not item:
            return None

        # ── Name ──────────────────────────────────────────────────────────────
        name = None
        names = item.get("names") or []
        if isinstance(names, list):
            for n in names:
                if n.get("primary") or n.get("sortindex") in (1, "1"):
                    name = n.get("name", "").strip()
                    break
            if not name and names:
                name = names[0].get("name", "").strip()
        if not name:
            name = item.get("name", "").strip()
        if not name:
            return None

        # ── Year ──────────────────────────────────────────────────────────────
        year = item.get("yearpublished") or item.get("year")
        try:
            year = int(year) if year else None
        except (ValueError, TypeError):
            year = None

        # ── Ratings ───────────────────────────────────────────────────────────
        stats = item.get("stats", {})
        def _f(val):
            try:
                v = float(val or 0)
                return v if v > 0 else None
            except (ValueError, TypeError):
                return None

        rating      = _f(stats.get("avgrating") or stats.get("average"))
        geek_rating = _f(stats.get("bayesaverage") or stats.get("geekrating"))

        # ── Players / time ────────────────────────────────────────────────────
        def _i(val):
            try:
                v = int(val or 0)
                return v if v > 0 else None
            except (ValueError, TypeError):
                return None

        min_p = _i(item.get("minplayers"))
        max_p = _i(item.get("maxplayers"))
        min_t = _i(item.get("minplaytime"))
        max_t = _i(item.get("maxplaytime"))

        # ── Links ─────────────────────────────────────────────────────────────
        links = item.get("links", {})

        def _labels(link_type):
            return [e.get("label", "").strip() for e in links.get(link_type, [])
                    if e.get("label", "").strip()]

        mechanics  = _labels("boardgamemechanic")
        categories = _labels("boardgamecategory")
        publishers = _labels("boardgamepublisher")
        creators   = [e.get("name", "").strip() for e in links.get("boardgamedesigner", [])
                      if e.get("name", "").strip()]

        # Which base games does this expand?
        base_ids = [int(e["objectid"]) for e in links.get("expandsboardgame", [])
                    if e.get("objectid")]

        return {
            "id":          exp_id,
            "name":        name,
            "year":        year,
            "rating":      rating,
            "geek_rating": geek_rating,
            "min_players": min_p,
            "max_players": max_p,
            "min_time":    min_t,
            "max_time":    max_t,
            "mechanics":   mechanics,
            "categories":  categories,
            "creators":    creators,
            "publishers":  publishers,
            "base_ids":    base_ids,
        }
    except Exception as e:
        print(f"    error fetching {exp_id}: {e}")
        return None


# ── TTL writer ────────────────────────────────────────────────────────────────

def write_ttl(cp: dict, all_game_ids: set[int],
              mech_iri: dict, cat_iri: dict,
              creator_iri: dict, pub_iri: dict) -> None:

    games = cp.get("games", {})
    if not games:
        print("No expansion data in checkpoint — nothing to write.")
        return

    # ── Resolve which mechanics/categories/creators/publishers are NEW ─────────
    # (not in the existing ontology; we need to declare them)
    new_mechs     = {}   # iri_local → label
    new_cats      = {}
    new_creators  = {}
    new_pubs      = {}

    game_records  = []   # processed data ready for TTL output

    for gid_str, gdata in games.items():
        gid  = int(gid_str)
        name = gdata.get("name", "")
        if not name:
            continue

        # Filter base_ids to those in our ontology
        base_ids = [b for b in gdata.get("base_ids", []) if b in all_game_ids]
        if not base_ids:
            # Expansion not linked to any game in our set — skip
            continue

        resolved_mechs  = []
        resolved_cats   = []
        resolved_crs    = []
        resolved_pubs   = []

        for lbl in gdata.get("mechanics", []):
            key = lbl.lower()
            if key in mech_iri:
                resolved_mechs.append(mech_iri[key])
            else:
                iri = label_to_iri(lbl)
                if iri:
                    if iri not in new_mechs:
                        new_mechs[iri] = lbl
                    resolved_mechs.append(iri)

        for lbl in gdata.get("categories", []):
            key = lbl.lower()
            if key in cat_iri:
                resolved_cats.append(cat_iri[key])
            else:
                iri = label_to_iri(lbl)
                if iri:
                    if iri not in new_cats:
                        new_cats[iri] = lbl
                    resolved_cats.append(iri)

        for lbl in gdata.get("creators", []):
            key = lbl.lower()
            if key in creator_iri:
                resolved_crs.append(creator_iri[key])
            else:
                iri = label_to_iri(lbl)
                if iri:
                    if iri not in new_creators:
                        new_creators[iri] = lbl
                    resolved_crs.append(iri)

        for lbl in gdata.get("publishers", []):
            key = lbl.lower()
            if key in pub_iri:
                resolved_pubs.append(pub_iri[key])
            else:
                iri = label_to_iri(lbl)
                if iri:
                    if iri not in new_pubs:
                        new_pubs[iri] = lbl
                    resolved_pubs.append(iri)

        game_records.append({
            "id":          gid,
            "name":        name,
            "year":        gdata.get("year"),
            "rating":      gdata.get("rating"),
            "geek_rating": gdata.get("geek_rating"),
            "min_players": gdata.get("min_players"),
            "max_players": gdata.get("max_players"),
            "min_time":    gdata.get("min_time"),
            "max_time":    gdata.get("max_time"),
            "mechanics":   resolved_mechs,
            "categories":  resolved_cats,
            "creators":    resolved_crs,
            "publishers":  resolved_pubs,
            "base_ids":    base_ids,
        })

    game_records.sort(key=lambda r: r["id"])

    total_triples = (
        len(game_records)          # rdf:type
        + sum(1 for r in game_records if r["name"])
        + sum(1 for r in game_records if r["year"])
        + sum(1 for r in game_records if r["rating"])
        + sum(1 for r in game_records if r["geek_rating"])
        + sum(len(r["mechanics"])  for r in game_records)
        + sum(len(r["categories"]) for r in game_records)
        + sum(len(r["creators"])   for r in game_records)
        + sum(len(r["publishers"]) for r in game_records)
        + sum(len(r["base_ids"])   for r in game_records)
    )

    print(f"\nWriting {PATCH_FILE}:")
    print(f"  {len(game_records)} expansion games")
    print(f"  {len(new_mechs)} new mechanics | {len(new_cats)} new categories | "
          f"{len(new_creators)} new creators | {len(new_pubs)} new publishers")
    print(f"  ~{total_triples:,} triples")

    with open(PATCH_FILE, "w", encoding="utf-8") as f:
        f.write("# BGG expansion patch — generated by bgg_fetch_expansions.py\n")
        f.write(f"# {len(game_records)} expansion Game entities + bgg:isExpansionOf triples\n\n")
        f.write(f"@prefix bgg:  <{BGG_NS}> .\n")
        f.write(f"@prefix rdf:  <{RDF_NS}> .\n")
        f.write(f"@prefix rdfs: <{RDFS_NS}> .\n")
        f.write(f"@prefix xsd:  <{XSD_NS}> .\n\n")

        # ── New vocabulary entities ──────────────────────────────────────────
        if new_mechs:
            f.write("# ── NEW MECHANIC ENTITIES ───────────────────────────────────────────────\n\n")
            for iri in sorted(new_mechs):
                f.write(f'bgg:{iri} rdf:type bgg:Mechanic ; rdfs:label "{escape_ttl(new_mechs[iri])}"@en .\n')
            f.write("\n")

        if new_cats:
            f.write("# ── NEW CATEGORY ENTITIES ───────────────────────────────────────────────\n\n")
            for iri in sorted(new_cats):
                f.write(f'bgg:{iri} rdf:type bgg:Category ; rdfs:label "{escape_ttl(new_cats[iri])}"@en .\n')
            f.write("\n")

        if new_creators:
            f.write("# ── NEW CREATOR ENTITIES ────────────────────────────────────────────────\n\n")
            for iri in sorted(new_creators):
                f.write(f'bgg:{iri} rdf:type bgg:Creator ; rdfs:label "{escape_ttl(new_creators[iri])}"@en .\n')
            f.write("\n")

        if new_pubs:
            f.write("# ── NEW PUBLISHER ENTITIES ──────────────────────────────────────────────\n\n")
            for iri in sorted(new_pubs):
                f.write(f'bgg:{iri} rdf:type bgg:Publisher ; rdfs:label "{escape_ttl(new_pubs[iri])}"@en .\n')
            f.write("\n")

        # ── Expansion game entities ──────────────────────────────────────────
        f.write("# ── EXPANSION GAME ENTITIES ─────────────────────────────────────────────\n\n")
        for r in game_records:
            lines = [f"bgg:{r['id']}"]
            triples = [f"    rdf:type bgg:Game"]
            triples.append(f'    bgg:hasName "{escape_ttl(r["name"])}"')
            if r["year"]:
                triples.append(f'    bgg:hasYearPublished {r["year"]}')
            if r["rating"]:
                triples.append(f'    bgg:hasRating {r["rating"]:.2f}')
            if r["geek_rating"]:
                triples.append(f'    bgg:hasGeekRating {r["geek_rating"]:.2f}')
            if r["min_players"]:
                triples.append(f'    bgg:hasMinPlayers {r["min_players"]}')
            if r["max_players"]:
                triples.append(f'    bgg:hasMaxPlayers {r["max_players"]}')
            if r["min_time"]:
                triples.append(f'    bgg:hasMinGameTime {r["min_time"]}')
            if r["max_time"]:
                triples.append(f'    bgg:hasMaxGameTime {r["max_time"]}')
            if r["mechanics"]:
                mech_str = " , ".join(f"bgg:{m}" for m in r["mechanics"])
                triples.append(f"    bgg:hasMechanic {mech_str}")
            if r["categories"]:
                cat_str = " , ".join(f"bgg:{c}" for c in r["categories"])
                triples.append(f"    bgg:hasCategory {cat_str}")
            if r["creators"]:
                cr_str = " , ".join(f"bgg:{c}" for c in r["creators"])
                triples.append(f"    bgg:hasCreator {cr_str}")
            if r["publishers"]:
                pub_str = " , ".join(f"bgg:{p}" for p in r["publishers"])
                triples.append(f"    bgg:hasPublisher {pub_str}")
            for bid in r["base_ids"]:
                triples.append(f"    bgg:isExpansionOf bgg:{bid}")

            f.write("\n".join(lines) + "\n")
            f.write(" ;\n".join(triples) + " .\n\n")

    print(f"Written -> {PATCH_FILE}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main(top_n: int, write_only: bool) -> None:
    top_ids, all_game_ids, mech_iri, cat_iri, creator_iri, pub_iri = load_db_lookups(top_n)

    if write_only:
        cp = load_checkpoint()
        write_ttl(cp, all_game_ids, mech_iri, cat_iri, creator_iri, pub_iri)
        return

    env = load_env()
    if not login(env.get("BGG_USERNAME", ""), env.get("BGG_PASSWORD", "")):
        raise SystemExit("Login failed — check .env")

    cp = load_checkpoint()

    # ── Phase 1: collect expansion IDs ────────────────────────────────────────
    if not cp.get("phase1_done"):
        p1_processed = set(cp.get("phase1_processed", []))
        exp_id_set   = set(cp.get("expansion_ids", []))
        todo = [gid for gid in top_ids if gid not in p1_processed]
        print(f"\nPhase 1: collecting expansion IDs from {len(todo)} base games …")

        for i, gid in enumerate(todo, 1):
            new_ids = fetch_expansion_ids(gid)
            exp_id_set.update(new_ids)
            p1_processed.add(gid)

            if i % LOG_EVERY == 0:
                print(f"  {i:>5}/{len(todo)}  |  {len(exp_id_set):,} expansion IDs so far")
                cp["phase1_processed"] = sorted(p1_processed)
                cp["expansion_ids"]    = sorted(exp_id_set)
                save_checkpoint(cp)

            time.sleep(REQUEST_DELAY)

        cp["phase1_processed"] = sorted(p1_processed)
        cp["expansion_ids"]    = sorted(exp_id_set)
        cp["phase1_done"]      = True
        save_checkpoint(cp)
        print(f"Phase 1 done. {len(exp_id_set):,} unique expansion IDs found.\n")
    else:
        exp_id_set = set(cp.get("expansion_ids", []))
        print(f"Phase 1 already done. {len(exp_id_set):,} expansion IDs loaded from checkpoint.")

    # ── Phase 2: fetch data for each expansion ────────────────────────────────
    p2_processed = set(cp.get("phase2_processed", []))
    games_data   = cp.get("games", {})

    # Skip expansions already in our base game set (no need to re-fetch)
    todo_exp = [eid for eid in sorted(exp_id_set)
                if eid not in p2_processed and eid not in all_game_ids]
    print(f"Phase 2: fetching data for {len(todo_exp):,} expansion games …")

    for i, eid in enumerate(todo_exp, 1):
        gdata = fetch_expansion_data(eid)
        if gdata:
            games_data[str(eid)] = gdata

        p2_processed.add(eid)

        if i % LOG_EVERY == 0:
            print(f"  {i:>5}/{len(todo_exp)}  |  {len(games_data):,} expansions fetched")
            cp["phase2_processed"] = sorted(p2_processed)
            cp["games"]            = games_data
            save_checkpoint(cp)

        time.sleep(REQUEST_DELAY)

    cp["phase2_processed"] = sorted(p2_processed)
    cp["games"]            = games_data
    save_checkpoint(cp)
    print(f"Phase 2 done. {len(games_data):,} expansion games fetched.\n")

    write_ttl(cp, all_game_ids, mech_iri, cat_iri, creator_iri, pub_iri)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=2000,
                        help="Top N base games to scan for expansions (default: 2000)")
    parser.add_argument("--write-only", action="store_true",
                        help="Skip fetching; just write TTL from existing checkpoint")
    args = parser.parse_args()
    main(args.top, args.write_only)
