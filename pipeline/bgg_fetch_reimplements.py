"""
bgg_fetch_reimplements.py

Two-phase fetch of reimplementation relationship data from the BGG geekdo API.

Phase 1: For the top N base games, collect all IDs of games that REIMPLEMENT them
         (i.e. newer editions, re-releases, spiritual successors) via `reimplementation` links.

Phase 2: For every unique reimplementation ID discovered, fetch full game data
         and record which original game(s) it reimplements.

Output:
  bgg_reimplements_patch.ttl        -- bgg:reimplements triples (+ new Game entities
                                       for games not already in the ontology)
  bgg_reimplements_checkpoint.json  -- resumable checkpoint (both phases)

The property direction is: subject=newer reimplementation, object=original.
  e.g.  bgg:31627 bgg:reimplements bgg:9209   (TtR Nordic Countries reimplements TtR)

This enables SPARQL property-path queries like:
  ?game bgg:reimplements* bgg:9209   -- all games in the Ticket to Ride family

Usage:
    python bgg_fetch_reimplements.py [--top N]   (default: 2000)
    python bgg_fetch_reimplements.py --write-only
"""

import argparse, json, os, re, sqlite3, time, unicodedata
import requests

DB_PATH         = "../bgg.db"
PATCH_FILE      = "bgg_reimplements_patch.ttl"
CHECKPOINT_FILE = "bgg_reimplements_checkpoint.json"
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
SESSION.headers.update({"User-Agent": "BGG-Ontology-Reimplements-Fill/1.0"})


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
    print(f"Logging in as {username} ...", end=" ", flush=True)
    r = SESSION.post(
        BGG_LOGIN_URL,
        json={"credentials": {"username": username, "password": password}},
        timeout=30,
    )
    ok = r.status_code in (200, 204)
    print("OK" if ok else f"FAILED ({r.status_code})")
    return ok


def label_to_iri(label: str) -> str:
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
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


# ── DB lookups ────────────────────────────────────────────────────────────────

def load_db_lookups(top_n: int) -> tuple[list[int], set[int], dict, dict, dict, dict]:
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
    print(f"DB: {len(top_ids)} top games | {len(all_game_ids):,} total games")
    print(f"    {len(mech_iri)} mechanics | {len(cat_iri)} categories | "
          f"{len(creator_iri)} creators | {len(pub_iri)} publishers")
    return top_ids, all_game_ids, mech_iri, cat_iri, creator_iri, pub_iri


# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    if not os.path.exists(CHECKPOINT_FILE):
        return {"phase1_done": False, "phase1_processed": [], "reimpl_ids": [],
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


def fetch_reimpl_ids(base_id: int) -> list[int]:
    """Return BGG IDs of games that are reimplementations of this base game."""
    item  = _get_item(base_id)
    links = item.get("links", {})
    ids   = []
    for e in links.get("reimplementation", []):
        oid = e.get("objectid") or e.get("id")
        if oid:
            ids.append(int(oid))
    return ids


def fetch_reimpl_data(game_id: int) -> dict | None:
    """Fetch full game data + which games it reimplements. Returns None on failure."""
    try:
        item = _get_item(game_id)
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

        # Which original game(s) does this game reimplement?
        original_ids = [int(e["objectid"]) for e in links.get("reimplements", [])
                        if e.get("objectid")]

        return {
            "id":           game_id,
            "name":         name,
            "year":         year,
            "rating":       rating,
            "geek_rating":  geek_rating,
            "min_players":  min_p,
            "max_players":  max_p,
            "min_time":     min_t,
            "max_time":     max_t,
            "mechanics":    mechanics,
            "categories":   categories,
            "creators":     creators,
            "publishers":   publishers,
            "original_ids": original_ids,
        }
    except Exception as e:
        print(f"    error fetching {game_id}: {e}")
        return None


# ── TTL writer ────────────────────────────────────────────────────────────────

def write_ttl(cp: dict, all_game_ids: set[int],
              mech_iri: dict, cat_iri: dict,
              creator_iri: dict, pub_iri: dict) -> None:

    games = cp.get("games", {})
    if not games:
        print("No reimplements data in checkpoint -- nothing to write.")
        return

    new_mechs    = {}
    new_cats     = {}
    new_creators = {}
    new_pubs     = {}

    new_game_records = []   # games NOT in the existing ontology: need full entity
    reimpl_triples   = []   # (game_id, original_id) pairs for ALL reimplements triples

    for gid_str, gdata in games.items():
        gid  = int(gid_str)
        name = gdata.get("name", "")
        if not name:
            continue

        # Filter to original_ids that are in our ontology
        original_ids = [o for o in gdata.get("original_ids", []) if o in all_game_ids]
        if not original_ids:
            continue   # No link to our dataset -- skip

        for oid in original_ids:
            reimpl_triples.append((gid, oid))

        # Only create new game entity if this game isn't already in the ontology
        if gid in all_game_ids:
            continue

        resolved_mechs = []
        resolved_cats  = []
        resolved_crs   = []
        resolved_pubs  = []

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

        new_game_records.append({
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
        })

    new_game_records.sort(key=lambda r: r["id"])
    reimpl_triples.sort()

    # Separate "existing game" triples from "new game" triples
    existing_reimpl = [(g, o) for g, o in reimpl_triples if g in all_game_ids]
    new_reimpl      = [(g, o) for g, o in reimpl_triples if g not in all_game_ids]

    print(f"\nWriting {PATCH_FILE}:")
    print(f"  {len(reimpl_triples)} bgg:reimplements triples total")
    print(f"    {len(existing_reimpl)} for games already in ontology (triple-only)")
    print(f"    {len(new_reimpl)} for new game entities")
    print(f"  {len(new_game_records)} new Game entities")
    print(f"  {len(new_mechs)} new mechanics | {len(new_cats)} new categories | "
          f"{len(new_creators)} new creators | {len(new_pubs)} new publishers")

    with open(PATCH_FILE, "w", encoding="utf-8") as f:
        f.write("# BGG reimplements patch -- generated by bgg_fetch_reimplements.py\n")
        f.write(f"# {len(reimpl_triples)} bgg:reimplements triples "
                f"+ {len(new_game_records)} new Game entities\n\n")
        f.write(f"@prefix bgg:  <{BGG_NS}> .\n")
        f.write(f"@prefix rdf:  <{RDF_NS}> .\n")
        f.write(f"@prefix rdfs: <{RDFS_NS}> .\n")
        f.write(f"@prefix xsd:  <{XSD_NS}> .\n\n")

        # ── New vocabulary entities ──────────────────────────────────────────
        if new_mechs:
            f.write("# -- NEW MECHANIC ENTITIES --\n\n")
            for iri in sorted(new_mechs):
                f.write(f'bgg:{iri} rdf:type bgg:Mechanic ; rdfs:label "{escape_ttl(new_mechs[iri])}"@en .\n')
            f.write("\n")

        if new_cats:
            f.write("# -- NEW CATEGORY ENTITIES --\n\n")
            for iri in sorted(new_cats):
                f.write(f'bgg:{iri} rdf:type bgg:Category ; rdfs:label "{escape_ttl(new_cats[iri])}"@en .\n')
            f.write("\n")

        if new_creators:
            f.write("# -- NEW CREATOR ENTITIES --\n\n")
            for iri in sorted(new_creators):
                f.write(f'bgg:{iri} rdf:type bgg:Creator ; rdfs:label "{escape_ttl(new_creators[iri])}"@en .\n')
            f.write("\n")

        if new_pubs:
            f.write("# -- NEW PUBLISHER ENTITIES --\n\n")
            for iri in sorted(new_pubs):
                f.write(f'bgg:{iri} rdf:type bgg:Publisher ; rdfs:label "{escape_ttl(new_pubs[iri])}"@en .\n')
            f.write("\n")

        # ── Existing games: just the bgg:reimplements triple ────────────────
        if existing_reimpl:
            f.write("# -- bgg:reimplements TRIPLES FOR GAMES ALREADY IN ONTOLOGY --\n\n")
            for gid, oid in existing_reimpl:
                f.write(f"bgg:{gid} bgg:reimplements bgg:{oid} .\n")
            f.write("\n")

        # ── New game entities + their reimplements triples ───────────────────
        if new_game_records:
            f.write("# -- NEW GAME ENTITIES (reimplementations not already in ontology) --\n\n")
            new_reimpl_by_game = {}
            for gid, oid in new_reimpl:
                new_reimpl_by_game.setdefault(gid, []).append(oid)

            for r in new_game_records:
                lines = [f"bgg:{r['id']}"]
                triples = ["    rdf:type bgg:Game"]
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
                    triples.append(f'    bgg:hasMechanic {" , ".join(f"bgg:{m}" for m in r["mechanics"])}')
                if r["categories"]:
                    triples.append(f'    bgg:hasCategory {" , ".join(f"bgg:{c}" for c in r["categories"])}')
                if r["creators"]:
                    triples.append(f'    bgg:hasCreator {" , ".join(f"bgg:{c}" for c in r["creators"])}')
                if r["publishers"]:
                    triples.append(f'    bgg:hasPublisher {" , ".join(f"bgg:{p}" for p in r["publishers"])}')
                for oid in new_reimpl_by_game.get(r["id"], []):
                    triples.append(f"    bgg:reimplements bgg:{oid}")

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
        raise SystemExit("Login failed -- check .env")

    cp = load_checkpoint()

    # ── Phase 1: collect reimplementation IDs ─────────────────────────────────
    if not cp.get("phase1_done"):
        p1_processed = set(cp.get("phase1_processed", []))
        reimpl_id_set = set(cp.get("reimpl_ids", []))
        todo = [gid for gid in top_ids if gid not in p1_processed]
        print(f"\nPhase 1: collecting reimplementation IDs from {len(todo)} base games ...")

        for i, gid in enumerate(todo, 1):
            new_ids = fetch_reimpl_ids(gid)
            reimpl_id_set.update(new_ids)
            p1_processed.add(gid)

            if i % LOG_EVERY == 0:
                print(f"  {i:>5}/{len(todo)}  |  {len(reimpl_id_set):,} reimplementation IDs so far")
                cp["phase1_processed"] = sorted(p1_processed)
                cp["reimpl_ids"]       = sorted(reimpl_id_set)
                save_checkpoint(cp)

            time.sleep(REQUEST_DELAY)

        cp["phase1_processed"] = sorted(p1_processed)
        cp["reimpl_ids"]       = sorted(reimpl_id_set)
        cp["phase1_done"]      = True
        save_checkpoint(cp)
        print(f"Phase 1 done. {len(reimpl_id_set):,} unique reimplementation IDs found.\n")
    else:
        reimpl_id_set = set(cp.get("reimpl_ids", []))
        print(f"Phase 1 already done. {len(reimpl_id_set):,} reimplementation IDs loaded.")

    # ── Phase 2: fetch data for each reimplementation ─────────────────────────
    p2_processed = set(cp.get("phase2_processed", []))
    games_data   = cp.get("games", {})

    # Unlike expansions, we DO process reimpl IDs even if they're already in the DB
    # (we need their reimplements links to write the triples)
    todo_reimpl = [rid for rid in sorted(reimpl_id_set) if rid not in p2_processed]
    print(f"Phase 2: fetching data for {len(todo_reimpl):,} reimplementation games ...")

    for i, rid in enumerate(todo_reimpl, 1):
        gdata = fetch_reimpl_data(rid)
        if gdata:
            games_data[str(rid)] = gdata

        p2_processed.add(rid)

        if i % LOG_EVERY == 0:
            print(f"  {i:>5}/{len(todo_reimpl)}  |  {len(games_data):,} games fetched")
            cp["phase2_processed"] = sorted(p2_processed)
            cp["games"]            = games_data
            save_checkpoint(cp)

        time.sleep(REQUEST_DELAY)

    cp["phase2_processed"] = sorted(p2_processed)
    cp["games"]            = games_data
    save_checkpoint(cp)
    print(f"Phase 2 done. {len(games_data):,} reimplementation games fetched.\n")

    write_ttl(cp, all_game_ids, mech_iri, cat_iri, creator_iri, pub_iri)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=2000,
                        help="Top N base games to scan for reimplementations (default: 2000)")
    parser.add_argument("--write-only", action="store_true",
                        help="Skip fetching; just write TTL from existing checkpoint")
    args = parser.parse_args()
    main(args.top, args.write_only)
