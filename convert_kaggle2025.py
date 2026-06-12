import csv
from rdflib import Graph, URIRef, Literal, RDF, RDFS, OWL, XSD

from convert_creators import name_to_local, serialize_organized, BGG, TRENJ
from convert_threnjen import (
    read_binary_matrix, read_designers_csv,
    safe_int, safe_float, build_vocab, weight_to_size,
)

THRENJEN_DIR = "threnjen bg db"
KAGGLE_DIR   = "kaggle2025bgdb"


def main() -> None:
    print("Loading existing TTL (T-BOX + personal collection)...")
    g = Graph()
    g.parse("old_ttls/bgg_may2026_input_kaggle2025.ttl", format="turtle")
    print(f"  {len(g)} triples loaded")

    # New T-BOX properties not present in the input TTL
    print("Adding new T-BOX properties...")
    new_props = [
        (BGG.hasDescription,   OWL.DatatypeProperty, BGG.Game, XSD.string,
         "has description",
         "A human-readable textual description of the game as listed on BoardGameGeek."),
        (BGG.hasYearPublished, OWL.DatatypeProperty, BGG.Game, XSD.int,
         "has year published",
         "The year in which the game was first published."),
    ]
    for prop, prop_type, domain, range_val, label, comment in new_props:
        g.add((prop, RDF.type,        prop_type))
        g.add((prop, RDFS.domain,     domain))
        g.add((prop, RDFS.range,      range_val))
        g.add((prop, RDFS.label,      Literal(label,   lang="en")))
        g.add((prop, RDFS.comment,    Literal(comment, lang="en")))

    # hasThumbnail: ObjectProperty (URIRef value), consistent with hasURL
    g.add((BGG.hasThumbnail, RDF.type,     OWL.ObjectProperty))
    g.add((BGG.hasThumbnail, RDFS.domain,  BGG.Game))
    g.add((BGG.hasThumbnail, RDFS.label,   Literal("has thumbnail", lang="en")))
    g.add((BGG.hasThumbnail, RDFS.comment, Literal(
        "A thumbnail image URL for the game as listed on BoardGameGeek.", lang="en"
    )))

    g.add((BGG.isFullyEnriched, RDF.type,     OWL.DatatypeProperty))
    g.add((BGG.isFullyEnriched, RDFS.domain,  BGG.Game))
    g.add((BGG.isFullyEnriched, RDFS.range,   XSD.boolean))
    g.add((BGG.isFullyEnriched, RDFS.label,   Literal("is fully enriched", lang="en")))
    g.add((BGG.isFullyEnriched, RDFS.comment, Literal(
        "True if the game is fully enriched with mechanics, categories, themes, "
        "creators, and publishers; false if only basic metadata is available.",
        lang="en"
    )))

    # Save old creator data before stripping A-BOX (low-exp fallback)
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

    # Strip A-BOX instances we're rebuilding from new sources
    print("Removing old game / creator / category / mechanic / theme / publisher instances...")
    removed = 0
    for rdf_type in [BGG.Game, BGG.Creator, BGG.Category, BGG.Mechanic, BGG.Publisher, TRENJ.Theme]:
        for subj in list(g.subjects(RDF.type, rdf_type)):
            triples = list(g.triples((subj, None, None)))
            for t in triples:
                g.remove(t)
            removed += len(triples)
    print(f"  Removed {removed} triples; {len(g)} remaining")

    # Read threnjen CSVs: structured data for 21,925 games
    print("Reading threnjen CSVs for structured data...")
    themes_map     = read_binary_matrix(f"{THRENJEN_DIR}/themes.csv")
    subcats_map    = read_binary_matrix(f"{THRENJEN_DIR}/subcategories.csv")
    mechanics_map  = read_binary_matrix(f"{THRENJEN_DIR}/mechanics.csv")
    publishers_map = read_binary_matrix(
        f"{THRENJEN_DIR}/publishers_reduced.csv",
        skip_cols={"Low-Exp Publisher"},
    )
    named_designers, lowexp = read_designers_csv(f"{THRENJEN_DIR}/designers_reduced.csv")

    # Threnjen games.csv: player counts / weight / playtime (absent from kaggle)
    threnjen_rows: dict[int, dict] = {}
    with open(f"{THRENJEN_DIR}/games.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            threnjen_rows[int(row["BGGId"])] = row
    print(f"  {len(threnjen_rows)} threnjen games with structured data")

    # Original BGG categories (primary) and old mechanics (fallback)
    old_cats_map: dict[int, list[str]] = {}
    with open("bg_categories.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gid = int(row["game_id"])
            old_cats_map.setdefault(gid, []).append(row["category"])

    old_mechs_map: dict[int, list[str]] = {}
    with open("bg_mechanics.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mech = row["mechanic"]
            if mech and mech.lower() != "none":
                gid = int(row["game_id"])
                old_mechs_map.setdefault(gid, []).append(mech)

    all_themes     = {n for ns in themes_map.values()       for n in ns}
    all_old_cats   = {n for ns in old_cats_map.values()     for n in ns}
    all_subcats    = {n for ns in subcats_map.values()      for n in ns}
    all_mechanics  = {n for ns in mechanics_map.values()    for n in ns}
    all_old_mechs  = {n for ns in old_mechs_map.values()    for n in ns}
    all_publishers = {n for ns in publishers_map.values()   for n in ns}
    all_named      = {n for ns in named_designers.values()  for n in ns}
    all_old_labels = {label for entries in old_creators.values() for _, label in entries if label}

    # Build controlled-vocabulary instances
    g.bind("trenj", TRENJ)
    theme_iris   = build_vocab(g, all_themes,                    TRENJ.Theme)
    cat_iris     = build_vocab(g, all_old_cats | all_subcats,    BGG.Category)
    mech_iris    = build_vocab(g, all_mechanics | all_old_mechs, BGG.Mechanic)
    pub_iris     = build_vocab(g, all_publishers,                BGG.Publisher)
    creator_iris = build_vocab(g, all_named | all_old_labels,    BGG.Creator)

    # Separate graph for kaggle-only (not threnjen-enriched) games
    g_extra = Graph()
    g_extra.bind("bgg",  BGG)
    g_extra.bind("trenj", TRENJ)

    # Build game A-BOX from kaggle boardgames.csv
    print("Building game A-BOX from kaggle boardgames.csv...")
    game_count   = 0
    patched      = 0
    mech_patched = 0
    threnjen_enriched = 0

    with open(f"{KAGGLE_DIR}/boardgames.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                gid = int(row["Game_Id"])
            except (ValueError, TypeError):
                continue
            game = BGG[str(gid)]

            # Route to main graph (threnjen-enriched) or extra graph (kaggle-only)
            target = g if gid in threnjen_rows else g_extra

            # Core identifiers — every game gets these
            target.add((game, RDF.type,    BGG.Game))
            target.add((game, BGG.hasName, Literal(row["Title"], datatype=XSD.string)))
            target.add((game, BGG.hasID,   Literal(gid,          datatype=XSD.int)))
            target.add((game, BGG.hasURL,  URIRef(f"https://boardgamegeek.com/boardgame/{gid}")))

            desc = row["Description"].strip()
            if desc:
                target.add((game, BGG.hasDescription, Literal(desc, datatype=XSD.string)))

            v = safe_int(row["Year"])
            if v is not None and v != 0:
                target.add((game, BGG.hasYearPublished, Literal(v, datatype=XSD.int)))

            thumb = row["Thumbnail"].strip()
            if thumb:
                target.add((game, BGG.hasThumbnail, URIRef(thumb)))

            v = safe_float(row["AvgRating"])
            if v is not None:
                target.add((game, BGG.hasRating, Literal(v, datatype=XSD.double)))

            v = safe_float(row["GeekRating"])
            if v is not None:
                target.add((game, BGG.hasGeekRating, Literal(v, datatype=XSD.double)))

            if safe_float(row["AvgRating"]) is not None:
                target.add((game, BGG.ratingFromTime, Literal(2025, datatype=XSD.int)))

            target.add((game, BGG.isFullyEnriched, Literal(gid in threnjen_rows, datatype=XSD.boolean)))

            # Threnjen enrichment: player counts, weight, themes, categories,
            # mechanics, creators, publishers — only for the 21,925 overlap games
            if gid in threnjen_rows:
                tr = threnjen_rows[gid]

                v = safe_int(tr["MinPlayers"],    zero_is_none=True)
                if v is not None:
                    g.add((game, BGG.hasMinPlayers, Literal(v, datatype=XSD.int)))

                v = safe_int(tr["MaxPlayers"],    zero_is_none=True)
                if v is not None:
                    g.add((game, BGG.hasMaxPlayers, Literal(v, datatype=XSD.int)))

                v = safe_int(tr["ComMinPlaytime"], zero_is_none=True)
                if v is not None:
                    g.add((game, BGG.hasMinGameTime, Literal(v, datatype=XSD.int)))

                v = safe_int(tr["ComMaxPlaytime"], zero_is_none=True)
                if v is not None:
                    g.add((game, BGG.hasMaxGameTime, Literal(v, datatype=XSD.int)))

                v = safe_int(tr["MfgAgeRec"],     zero_is_none=True)
                if v is not None:
                    g.add((game, BGG.hasMinRecAge, Literal(v, datatype=XSD.int)))

                v = safe_int(tr["BestPlayers"],   zero_is_none=True)
                if v is not None:
                    g.add((game, BGG.hasBestNumPlayers, Literal(v, datatype=XSD.int)))

                size = weight_to_size(tr["GameWeight"])
                if size is not None:
                    g.add((game, BGG.hasSize, size))

                for theme in themes_map.get(gid, []):
                    if theme in theme_iris:
                        g.add((game, TRENJ.hasTheme, theme_iris[theme]))

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

                if not mechanics_map.get(gid) and gid in old_mechs_map:
                    for mech in old_mechs_map[gid]:
                        if mech in mech_iris:
                            g.add((game, BGG.hasMechanic, mech_iris[mech]))
                    mech_patched += 1

                for designer in named_designers.get(gid, []):
                    if designer in creator_iris:
                        g.add((game, BGG.hasCreator, creator_iris[designer]))

                if lowexp.get(gid) and gid in old_creators:
                    for creator_iri, label in old_creators[gid]:
                        g.add((game, BGG.hasCreator, creator_iri))
                    patched += 1

                for publisher in publishers_map.get(gid, []):
                    if publisher in pub_iris:
                        g.add((game, BGG.hasPublisher, pub_iris[publisher]))

                threnjen_enriched += 1

            game_count += 1

    print(f"  {game_count} games total ({threnjen_enriched} fully enriched from threnjen)")
    print(f"  {patched} patched with old creator data; {mech_patched} patched with old mechanic data")
    print(f"  {len(g)} total triples")

    output_main  = "bgg_main.ttl"
    output_extra = "bgg_kaggle_extra.ttl"
    print(f"Serializing {output_main} (T-BOX + vocabulary + {threnjen_enriched} enriched games)...")
    serialize_organized(g, output_main)
    extra_count = game_count - threnjen_enriched
    print(f"Serializing {output_extra} ({extra_count} kaggle-only games)...")
    g_extra.serialize(output_extra, format="turtle")
    print("Done.")


if __name__ == "__main__":
    main()
