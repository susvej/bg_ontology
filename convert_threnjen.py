import csv
from rdflib import Graph, URIRef, Literal, RDF, RDFS, XSD

from convert_creators import name_to_local, serialize_organized, BGG, TRENJ

DATA_DIR = "threnjen bg db"


def weight_to_size(w_str: str) -> URIRef | None:
    try:
        w = float(w_str)
    except (ValueError, TypeError):
        return None
    if w <= 0:
        return None
    if w < 2.0:
        return BGG.small
    if w < 3.0:
        return BGG.medium
    return BGG.large


def read_binary_matrix(path: str, skip_cols: set[str] | None = None) -> dict[int, list[str]]:
    """Wide binary CSV → {BGGId: [column names where value == '1']}."""
    skip = set(skip_cols or [])
    result: dict[int, list[str]] = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data_cols = [c for c in (reader.fieldnames or [])[1:] if c not in skip]
        for row in reader:
            gid = int(row["BGGId"])
            result[gid] = [c for c in data_cols if row.get(c) == "1"]
    return result


def read_designers_csv(path: str) -> tuple[dict[int, list[str]], dict[int, bool]]:
    """Returns (named_map, lowexp_map) from designers_reduced.csv."""
    named: dict[int, list[str]] = {}
    lowexp: dict[int, bool] = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        data_cols = [c for c in (reader.fieldnames or [])[1:] if c != "Low-Exp Designer"]
        for row in reader:
            gid = int(row["BGGId"])
            lowexp[gid] = row.get("Low-Exp Designer", "0") == "1"
            named[gid] = [c for c in data_cols if row.get(c) == "1"]
    return named, lowexp


def safe_int(val: str, zero_is_none: bool = False) -> int | None:
    try:
        v = int(float(val))
        return None if (zero_is_none and v == 0) else v
    except (ValueError, TypeError):
        return None


def safe_float(val: str) -> float | None:
    try:
        v = float(val)
        return None if v == 0.0 else v
    except (ValueError, TypeError):
        return None


def _norm_label(name: str) -> str:
    """Strip dataset-internal prefixes and replace underscores with spaces."""
    if name.startswith("Theme_"):
        name = name[6:]
    return name.replace("_", " ")


def build_vocab(g: Graph, names: set[str], rdf_type: URIRef) -> dict[str, URIRef]:
    """Create controlled-vocabulary instances; return name → IRI map.

    Multiple raw names may share the same IRI (e.g. "Card Game" and
    "Card_Game" both normalise to bgg:CardGame).  We pick the best
    human-readable label: prefer labels that contain "/" (original BGG
    format with slashes) over plain-alphanumeric concatenations, then
    prefer shorter labels.
    """
    iri_map: dict[str, URIRef] = {}
    iri_labels: dict[str, set[str]] = {}  # local → set of clean candidate labels

    for name in names:
        local = name_to_local(name)
        if not local:
            continue
        iri_map[name] = BGG[local]
        iri_labels.setdefault(local, set()).add(_norm_label(name))

    for local, candidates in iri_labels.items():
        iri = BGG[local]
        # Score: (underscore_count, -slash_count, length) — lower wins
        best = min(candidates, key=lambda s: (s.count("_"), -s.count("/"), len(s)))
        g.add((iri, RDF.type, rdf_type))
        g.add((iri, RDFS.label, Literal(best, lang="en")))

    return iri_map


def main() -> None:
    print("Loading existing TTL (T-BOX + personal collection)...")
    g = Graph()
    g.parse("old_ttls/bgg_march2026_as_threnjen_convert_input.ttl", format="turtle")
    print(f"  {len(g)} triples loaded")

    # Save old game→creator mapping BEFORE stripping A-BOX.
    # {game_id_int: [(creator_iri, label_str), ...]}
    print("Extracting old creator data as low-exp fallback...")
    old_creators: dict[int, list[tuple[URIRef, str]]] = {}
    for game_iri, _, creator_iri in g.triples((None, BGG.hasCreator, None)):
        gid_str = str(game_iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        try:
            gid = int(gid_str)
        except ValueError:
            continue
        label = str(g.value(creator_iri, RDFS.label) or "")
        old_creators.setdefault(gid, []).append((creator_iri, label))
    print(f"  Saved creator data for {len(old_creators)} games")

    # Remove old A-BOX instances for types we're rebuilding from the new source
    print("Removing old game / creator / category / mechanic instances...")
    removed = 0
    for rdf_type in [BGG.Game, BGG.Creator, BGG.Category, BGG.Mechanic]:
        for subj in list(g.subjects(RDF.type, rdf_type)):
            triples = list(g.triples((subj, None, None)))
            for t in triples:
                g.remove(t)
            removed += len(triples)
    print(f"  Removed {removed} triples; {len(g)} remaining")

    # Read threnjen CSVs
    print("Reading threnjen CSVs...")
    themes_map              = read_binary_matrix(f"{DATA_DIR}/themes.csv")
    subcats_map             = read_binary_matrix(f"{DATA_DIR}/subcategories.csv")

    # Original BGG categories from the old dataset (primary source for bgg:hasCategory)
    old_cats_map: dict[int, list[str]] = {}
    with open("bg_categories.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid = int(row["game_id"])
            old_cats_map.setdefault(gid, []).append(row["category"])
    print(f"  Loaded BGG categories for {len(old_cats_map)} games from bg_categories.csv")

    # Original BGG mechanics (fallback for games threnjen has no mechanics for)
    old_mechs_map: dict[int, list[str]] = {}
    with open("bg_mechanics.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mech = row["mechanic"]
            if mech and mech.lower() != "none":
                gid = int(row["game_id"])
                old_mechs_map.setdefault(gid, []).append(mech)
    print(f"  Loaded BGG mechanics for {len(old_mechs_map)} games from bg_mechanics.csv")
    mechanics_map           = read_binary_matrix(f"{DATA_DIR}/mechanics.csv")
    publishers_map          = read_binary_matrix(
        f"{DATA_DIR}/publishers_reduced.csv",
        skip_cols={"Low-Exp Publisher"},
    )
    named_designers, lowexp = read_designers_csv(f"{DATA_DIR}/designers_reduced.csv")

    all_themes     = {n for ns in themes_map.values()       for n in ns}
    all_old_cats   = {n for ns in old_cats_map.values()    for n in ns}
    all_subcats    = {n for ns in subcats_map.values()     for n in ns}
    all_mechanics  = {n for ns in mechanics_map.values()   for n in ns}
    all_old_mechs  = {n for ns in old_mechs_map.values()   for n in ns}
    all_publishers = {n for ns in publishers_map.values()  for n in ns}
    all_named      = {n for ns in named_designers.values() for n in ns}

    # Also collect all creator labels coming from the old fallback data
    all_old_labels = {label for entries in old_creators.values() for _, label in entries if label}

    print(f"  {len(all_themes)} trenj themes, {len(all_old_cats)} bgg categories (old), "
          f"{len(all_subcats)} subcategories (fallback), {len(all_mechanics)} mechanics, "
          f"{len(all_old_mechs)} old mechanics (fallback), "
          f"{len(all_publishers)} publishers, "
          f"{len(all_named)} named designers, "
          f"{len(all_old_labels)} additional creators from old data")

    # Build controlled vocabulary instances
    g.bind("trenj", TRENJ)
    theme_iris   = build_vocab(g, all_themes,                   TRENJ.Theme)
    cat_iris     = build_vocab(g, all_old_cats | all_subcats,   BGG.Category)
    mech_iris    = build_vocab(g, all_mechanics | all_old_mechs, BGG.Mechanic)
    pub_iris     = build_vocab(g, all_publishers, BGG.Publisher)
    # Named designers from matrix + old fallback names both get IRIs
    creator_iris = build_vocab(g, all_named | all_old_labels, BGG.Creator)

    # Build game A-BOX
    print("Building game A-BOX from games.csv...")
    patched = 0
    mech_patched = 0
    game_count = 0

    with open(f"{DATA_DIR}/games.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid  = int(row["BGGId"])
            game = BGG[str(gid)]

            g.add((game, RDF.type,    BGG.Game))
            g.add((game, BGG.hasName, Literal(row["Name"], datatype=XSD.string)))
            g.add((game, BGG.hasID,   Literal(gid,         datatype=XSD.int)))
            g.add((game, BGG.hasURL,  URIRef(f"https://boardgamegeek.com/boardgame/{gid}")))

            v = safe_float(row["AvgRating"])
            if v is not None:
                g.add((game, BGG.hasRating,     Literal(v, datatype=XSD.double)))

            v = safe_float(row["BayesAvgRating"])
            if v is not None:
                g.add((game, BGG.hasGeekRating, Literal(v, datatype=XSD.double)))

            v = safe_int(row["MinPlayers"],    zero_is_none=True)
            if v is not None:
                g.add((game, BGG.hasMinPlayers, Literal(v, datatype=XSD.int)))

            v = safe_int(row["MaxPlayers"],    zero_is_none=True)
            if v is not None:
                g.add((game, BGG.hasMaxPlayers, Literal(v, datatype=XSD.int)))

            v = safe_int(row["ComMinPlaytime"], zero_is_none=True)
            if v is not None:
                g.add((game, BGG.hasMinGameTime, Literal(v, datatype=XSD.int)))

            v = safe_int(row["ComMaxPlaytime"], zero_is_none=True)
            if v is not None:
                g.add((game, BGG.hasMaxGameTime, Literal(v, datatype=XSD.int)))

            v = safe_int(row["MfgAgeRec"],     zero_is_none=True)
            if v is not None:
                g.add((game, BGG.hasMinRecAge,  Literal(v, datatype=XSD.int)))

            v = safe_int(row["BestPlayers"],   zero_is_none=True)
            if v is not None:
                g.add((game, BGG.hasBestNumPlayers, Literal(v, datatype=XSD.int)))

            size = weight_to_size(row["GameWeight"])
            if size is not None:
                g.add((game, BGG.hasSize, size))

            for theme in themes_map.get(gid, []):
                if theme in theme_iris:
                    g.add((game, TRENJ.hasTheme, theme_iris[theme]))

            # bgg:hasCategory: prefer original BGG data; fall back to subcategories for new games
            if gid in old_cats_map:
                for cat in old_cats_map[gid]:
                    if cat in cat_iris:
                        g.add((game, BGG.hasCategory, cat_iris[cat]))
            else:
                for subcat in subcats_map.get(gid, []):
                    if subcat in cat_iris:
                        g.add((game, BGG.hasCategory, cat_iris[subcat]))

            for mech in mechanics_map.get(gid, []):
                if mech in mech_iris:
                    g.add((game, BGG.hasMechanic, mech_iris[mech]))

            # Old-data mechanic patch: fill gap for games threnjen has no mechanics for
            if not mechanics_map.get(gid) and gid in old_mechs_map:
                for mech in old_mechs_map[gid]:
                    if mech in mech_iris:
                        g.add((game, BGG.hasMechanic, mech_iris[mech]))
                mech_patched += 1

            # Named designers from binary matrix
            for designer in named_designers.get(gid, []):
                if designer in creator_iris:
                    g.add((game, BGG.hasCreator, creator_iris[designer]))

            # Low-exp patch: supplement from old dataset
            if lowexp.get(gid) and gid in old_creators:
                for creator_iri, label in old_creators[gid]:
                    g.add((game, BGG.hasCreator, creator_iri))
                patched += 1

            for publisher in publishers_map.get(gid, []):
                if publisher in pub_iris:
                    g.add((game, BGG.hasPublisher, pub_iris[publisher]))

            if safe_float(row["AvgRating"]) is not None:
                g.add((game, BGG.ratingFromTime, Literal(2022, datatype=XSD.int)))

            game_count += 1

    print(f"  {game_count} games; {patched} patched with old creator data; {mech_patched} patched with old mechanic data")
    print(f"  {len(g)} total triples")

    output = "old_ttls/bgg_threnjen.ttl"
    print(f"Serializing to {output} ...")
    serialize_organized(g, output)
    print("Done.")


if __name__ == "__main__":
    main()
