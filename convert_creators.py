import re
import unicodedata
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, OWL, XSD, BNode

BGG     = Namespace("https://raw.githubusercontent.com/susvej/bg_ontology/")
BGG_OLD = "https://raw.githubusercontent.com/susvej/bg_ontology/refs/heads/main/bgg_march2025.ttl#"
SH   = Namespace("http://www.w3.org/ns/shacl#")
SVJ  = Namespace("https://vejdemo.se/boardgames#")
TRENJ = Namespace("https://vejdemo.se/boardgames/threnjen#")

HAS_CREATOR  = BGG.hasCreator
CREATOR_CLASS = BGG.Creator
SH_NS = str(SH)

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "vi"}
PRED_ORDER = {str(RDF.type): 0, str(RDFS.label): 1, str(RDFS.comment): 2}


# ---------------------------------------------------------------------------
# Creator helpers
# ---------------------------------------------------------------------------

def split_creators(s: str) -> list[str]:
    parts = [p.strip() for p in s.split(",")]
    result, i = [], 0
    while i < len(parts):
        name = parts[i]
        while i + 1 < len(parts) and parts[i + 1].strip().lower().rstrip(".") in SUFFIXES:
            i += 1
            name = name + ", " + parts[i]
        result.append(name)
        i += 1
    return result


def name_to_local(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    words = re.split(r"[^a-zA-Z0-9]+", ascii_str)
    return "".join(w.capitalize() for w in words if w)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def subject_sort_key(subj) -> tuple:
    local = str(subj).rsplit("#", 1)[-1].rsplit("/", 1)[-1]
    try:
        return (0, int(local), "")
    except ValueError:
        return (1, 0, local.lower())


def pred_sort_key(pred) -> tuple:
    return (PRED_ORDER.get(str(pred), 99), str(pred))


def add_bnode_triples(g: Graph, tmp: Graph, bnode: BNode, visited=None) -> None:
    """Recursively copy blank-node triples from g into tmp."""
    if visited is None:
        visited = set()
    if bnode in visited:
        return
    visited.add(bnode)
    for _, p, o in g.triples((bnode, None, None)):
        tmp.add((bnode, p, o))
        if isinstance(o, BNode):
            add_bnode_triples(g, tmp, o, visited)


def write_subject_block(lines: list, subj, g: Graph, skip_ns: str | None = None) -> None:
    ns = g.namespace_manager
    po: dict = {}
    for _, p, o in g.triples((subj, None, None)):
        if skip_ns and str(p).startswith(skip_ns):
            continue
        po.setdefault(p, []).append(o)
    if not po:
        return
    po_parts: list[tuple[str, str]] = []  # (line, inline_comment)
    for p in sorted(po.keys(), key=pred_sort_key):
        objs = sorted(po[p], key=str)
        obj_str = " , ".join(o.n3(ns) for o in objs)
        comment = ""
        if str(p) == str(BGG.hasOpinionOf) and len(objs) == 1:
            name = g.value(objs[0], BGG.hasName)
            if name:
                comment = f"  # {name}"
        po_parts.append((f"    {p.n3(ns)} {obj_str}", comment))
    lines.append(subj.n3(ns))
    for i, (part, comment) in enumerate(po_parts):
        suffix = " ." if i == len(po_parts) - 1 else " ;"
        lines.append(part + suffix + comment)
    lines.append("")


def write_section(lines: list, heading: str, subjects: list, g: Graph, skip_ns: str | None = None) -> None:
    if not subjects:
        return
    lines.append(f"# --- {heading} ---")
    lines.append("")
    for subj in subjects:
        write_subject_block(lines, subj, g, skip_ns=skip_ns)


def write_shacl_section(lines: list, g: Graph, named_shapes: list, shacl_props: list) -> None:
    """Build a temp graph of all SHACL content and let rdflib serialize it (handles blank nodes)."""
    tmp = Graph()
    for prefix, ns in g.namespaces():
        tmp.bind(prefix, ns)

    for subj in named_shapes:
        for _, p, o in g.triples((subj, None, None)):
            tmp.add((subj, p, o))
            if isinstance(o, BNode):
                add_bnode_triples(g, tmp, o)

    for prop in shacl_props:
        for _, p, o in g.triples((prop, None, None)):
            if str(p).startswith(SH_NS):
                tmp.add((prop, p, o))
                if isinstance(o, BNode):
                    add_bnode_triples(g, tmp, o)

    if len(tmp) == 0:
        return

    ttl_raw = tmp.serialize(format="turtle")
    for line in ttl_raw.splitlines():
        if not line.startswith("@prefix") and not line.startswith("PREFIX"):
            lines.append(line)
    lines.append("")


# ---------------------------------------------------------------------------
# Main serializer
# ---------------------------------------------------------------------------

def serialize_organized(g: Graph, output_path: str) -> None:
    ns_mgr = g.namespace_manager

    sh_shape_types = {SH.NodeShape, SH.PropertyShape}

    # Build type → subjects index
    type_subjects: dict = {}
    for subj, _, obj in g.triples((None, RDF.type, None)):
        if not isinstance(subj, BNode):
            type_subjects.setdefault(obj, set()).add(subj)

    # Named SHACL shapes go only to the SHACL section
    shacl_named = set()
    for sh_type in sh_shape_types:
        shacl_named.update(s for s in type_subjects.get(sh_type, set()) if not isinstance(s, BNode))

    # Properties that carry inline sh: predicates (but aren't named shapes themselves)
    shacl_props: set = set()
    for subj, pred, _ in g.triples((None, None, None)):
        if not isinstance(subj, BNode) and str(pred).startswith(SH_NS):
            shacl_props.add(subj)
    shacl_props -= shacl_named

    handled: set = set(shacl_named)  # named shapes are pre-claimed

    def subjects_of(rdf_type) -> list:
        raw = [s for s in type_subjects.get(rdf_type, set()) if s not in handled]
        handled.update(raw)
        return sorted(raw, key=subject_sort_key)

    lines: list[str] = []

    # 1. Prefixes — only emit namespaces actually used in this file
    USED_PREFIXES = {"bgg", "svj", "trenj", "rdf", "rdfs", "owl", "xsd", "sh", "dcterms", "skos"}
    for prefix, namespace in sorted(g.namespaces(), key=lambda x: x[0]):
        if str(prefix) in USED_PREFIXES:
            lines.append(f"@prefix {prefix}: <{namespace}> .")
    lines.append("")

    # 2. Ontology header (before everything else)
    ontology_subjs = subjects_of(OWL.Ontology)
    for subj in ontology_subjs:
        write_subject_block(lines, subj, g)

    # 3. T-BOX schema
    schema_meta = {
        OWL.Ontology, OWL.Class, RDFS.Class,
        OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property,
    } | sh_shape_types

    lines.append("# =============================================================================")
    lines.append("# T-BOX: Schema")
    lines.append("# =============================================================================")
    lines.append("")
    write_section(lines, "Classes",             subjects_of(OWL.Class),            g, skip_ns=SH_NS)
    write_section(lines, "Classes (rdfs)",      subjects_of(RDFS.Class),           g, skip_ns=SH_NS)
    write_section(lines, "Object Properties",   subjects_of(OWL.ObjectProperty),   g, skip_ns=SH_NS)
    write_section(lines, "Datatype Properties", subjects_of(OWL.DatatypeProperty), g, skip_ns=SH_NS)

    # 4. T-BOX controlled vocabulary instances
    abox_types = {BGG.Game, BGG.Creator}
    enum_types = sorted(
        [t for t in type_subjects if t not in schema_meta and t not in abox_types],
        key=str,
    )

    if enum_types:
        lines.append("# =============================================================================")
        lines.append("# T-BOX: Controlled Vocabulary Instances")
        lines.append("# =============================================================================")
        lines.append("")
        for rdf_type in enum_types:
            type_label = rdf_type.n3(ns_mgr)
            write_section(lines, type_label, subjects_of(rdf_type), g)

    # 5. A-BOX
    lines.append("# =============================================================================")
    lines.append("# A-BOX: Knowledge Graph")
    lines.append("# =============================================================================")
    lines.append("")
    write_section(lines, "Creators", subjects_of(BGG.Creator), g)
    write_section(lines, "Games",    subjects_of(BGG.Game),    g)

    # 6. Personal collection
    svj_ns = str(SVJ)
    svj_players  = [s for s in type_subjects.get(BGG.Player,        set()) if str(s).startswith(svj_ns) and s not in handled]
    svj_opinions = [s for s in type_subjects.get(BGG.PlayerOpinion, set()) if str(s).startswith(svj_ns) and s not in handled]
    if svj_players or svj_opinions:
        handled.update(svj_players)
        handled.update(svj_opinions)
        lines.append("# =============================================================================")
        lines.append("# Personal Collection — Susanne Vejdemo")
        lines.append("# =============================================================================")
        lines.append("")
        for subj in sorted(svj_players, key=subject_sort_key):
            write_subject_block(lines, subj, g)
        if svj_opinions:
            lines.append("# --- Player Opinions ---")
            lines.append("")
            for subj in sorted(svj_opinions, key=subject_sort_key):
                write_subject_block(lines, subj, g)

    # 7. SHACL
    lines.append("# =============================================================================")
    lines.append("# SHACL Constraints")
    lines.append("# =============================================================================")
    lines.append("")
    write_shacl_section(
        lines, g,
        sorted(shacl_named, key=subject_sort_key),
        sorted(shacl_props,  key=subject_sort_key),
    )

    # Fallback: anything not yet handled
    all_subjects = {s for s, _, _ in g.triples((None, None, None)) if not isinstance(s, BNode)}
    unhandled = sorted(all_subjects - handled, key=subject_sort_key)
    if unhandled:
        lines.append("# --- Uncategorized ---")
        lines.append("")
        for subj in unhandled:
            write_subject_block(lines, subj, g)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"  {len(handled)} subjects written, {len(unhandled)} uncategorized")


# ---------------------------------------------------------------------------
# Main transformation
# ---------------------------------------------------------------------------

def rename_iri(g: Graph, old: URIRef, new: URIRef) -> None:
    for s, p, o in list(g.triples((old, None, None))):
        g.remove((s, p, o)); g.add((new, p, o))
    for s, p, o in list(g.triples((None, None, old))):
        g.remove((s, p, o)); g.add((s, p, new))


def rename_namespace(g: Graph, old_ns: str, new_ns: str) -> int:
    """Rewrite every IRI starting with old_ns to use new_ns instead."""
    count = 0
    for s, p, o in list(g.triples((None, None, None))):
        ns = URIRef(str(s).replace(old_ns, new_ns, 1)) if isinstance(s, URIRef) and str(s).startswith(old_ns) else s
        np = URIRef(str(p).replace(old_ns, new_ns, 1)) if isinstance(p, URIRef) and str(p).startswith(old_ns) else p
        no = URIRef(str(o).replace(old_ns, new_ns, 1)) if isinstance(o, URIRef) and str(o).startswith(old_ns) else o
        if ns is not s or np is not p or no is not o:
            g.remove((s, p, o))
            g.add((ns, np, no))
            count += 1
    return count


def main():
    print("Parsing old_ttls/bgg_march2025.ttl ...")
    g = Graph()
    g.parse("old_ttls/bgg_march2025.ttl", format="turtle")

    # -- Rename old namespace to new --
    print("  Renaming namespace ...")
    renamed = rename_namespace(g, BGG_OLD, str(BGG))
    g.bind("bgg", BGG, override=True, replace=True)  # replace old binding
    print(f"  {renamed} triples rewritten")

    # -- Fix Print_&_Play: & is illegal in a Turtle prefixed name --
    print("  Fixing Print_&_Play ...")
    old_print = URIRef(str(BGG) + "Print_&_Play")
    rename_iri(g, old_print, BGG.Print_And_Play)

    # -- Convert hasURL string literals to actual IRIs --
    print("  Converting hasURL literals to IRIs ...")
    HAS_URL = BGG.hasURL
    for s, p, o in list(g.triples((None, HAS_URL, None))):
        if isinstance(o, Literal):
            g.remove((s, p, o))
            g.add((s, p, URIRef(str(o))))
    g.remove((HAS_URL, RDF.type, OWL.DatatypeProperty))
    g.remove((HAS_URL, RDFS.range, XSD.string))
    g.add((HAS_URL, RDF.type, OWL.ObjectProperty))

    # -- Split bgg:Memory into MemoryCategory / MemoryMechanic --
    print("  Splitting bgg:Memory ...")
    MEMORY      = BGG.Memory
    MEMORY_CAT  = BGG.MemoryCategory
    MEMORY_MECH = BGG.MemoryMechanic
    HAS_CATEGORY = BGG.hasCategory
    HAS_MECHANIC = BGG.hasMechanic

    for s, p, o in list(g.triples((None, HAS_CATEGORY, MEMORY))):
        g.remove((s, p, o)); g.add((s, p, MEMORY_CAT))
    for s, p, o in list(g.triples((None, HAS_MECHANIC, MEMORY))):
        g.remove((s, p, o)); g.add((s, p, MEMORY_MECH))
    for triple in list(g.triples((MEMORY, None, None))):
        g.remove(triple)
    g.add((MEMORY_CAT,  RDF.type, BGG.Category))
    g.add((MEMORY_MECH, RDF.type, BGG.Mechanic))

    # -- Convert creator literals to IRIs --
    to_remove, to_add = [], []
    creator_labels: dict[URIRef, str] = {}

    for game, _, creator_lit in g.triples((None, HAS_CREATOR, None)):
        if not isinstance(creator_lit, Literal):
            continue
        creator_str = str(creator_lit).strip()
        to_remove.append((game, HAS_CREATOR, creator_lit))
        if creator_str.lower() == "none" or not creator_str:
            continue
        for name in split_creators(creator_str):
            if not name:
                continue
            local = name_to_local(name)
            if not local:
                continue
            creator_iri = BGG[local]
            to_add.append((game, HAS_CREATOR, creator_iri))
            if creator_iri not in creator_labels:
                creator_labels[creator_iri] = name

    print(f"  Removing {len(to_remove)} literal creator triples")
    for triple in to_remove:
        g.remove(triple)
    print(f"  Adding {len(to_add)} IRI creator triples ({len(creator_labels)} unique creators)")
    for triple in to_add:
        g.add(triple)

    for creator_iri, label in creator_labels.items():
        g.add((creator_iri, RDF.type, CREATOR_CLASS))
        g.add((creator_iri, RDFS.label, Literal(label, lang="en")))

    g.add((CREATOR_CLASS, RDF.type, OWL.Class))
    g.add((CREATOR_CLASS, RDFS.label, Literal("Creator", lang="en")))

    g.remove((HAS_CREATOR, RDF.type, OWL.DatatypeProperty))
    g.remove((HAS_CREATOR, RDFS.range, XSD.string))
    g.remove((HAS_CREATOR, SH.maxCount, None))
    g.remove((HAS_CREATOR, SH.minCount, None))
    g.add((HAS_CREATOR, RDF.type, OWL.ObjectProperty))
    g.add((HAS_CREATOR, RDFS.range, CREATOR_CLASS))

    # -- PlayerOpinion class: combines a Player + Game to carry per-player opinions --
    PLAYER_OPINION = BGG.PlayerOpinion
    g.add((PLAYER_OPINION, RDF.type, OWL.Class))
    g.add((PLAYER_OPINION, RDFS.label, Literal("Player Opinion", lang="en")))
    g.add((PLAYER_OPINION, RDFS.comment, Literal(
        "Represents a specific player's perspective on a specific game, "
        "carrying subjective properties such as perceived difficulty and personal rating.",
        lang="en"
    )))

    # Linking properties: PlayerOpinion → Game and PlayerOpinion → Player
    HAS_OPINION_OF = BGG.hasOpinionOf
    g.add((HAS_OPINION_OF, RDF.type, OWL.ObjectProperty))
    g.add((HAS_OPINION_OF, RDFS.domain, PLAYER_OPINION))
    g.add((HAS_OPINION_OF, RDFS.range, BGG.Game))
    g.add((HAS_OPINION_OF, RDFS.label, Literal("has opinion of", lang="en")))

    HAS_OPINION_HOLDER = BGG.hasOpinionHolder
    g.add((HAS_OPINION_HOLDER, RDF.type, OWL.ObjectProperty))
    g.add((HAS_OPINION_HOLDER, RDFS.domain, PLAYER_OPINION))
    g.add((HAS_OPINION_HOLDER, RDFS.range, BGG.Player))
    g.add((HAS_OPINION_HOLDER, RDFS.label, Literal("has opinion holder", lang="en")))

    # Move hasMentalLoad domain from Game to PlayerOpinion
    g.remove((BGG.hasMentalLoad, RDFS.domain, BGG.Game))
    g.add((BGG.hasMentalLoad, RDFS.domain, PLAYER_OPINION))

    # Move hasComment domain from Player to PlayerOpinion
    g.remove((BGG.hasComment, RDFS.domain, BGG.Player))
    g.add((BGG.hasComment, RDFS.domain, PLAYER_OPINION))

    # -- Publisher class: convert hasPublisher from DatatypeProperty to ObjectProperty --
    PUBLISHER = BGG.Publisher
    g.add((PUBLISHER, RDF.type, OWL.Class))
    g.remove((BGG.hasPublisher, RDF.type, OWL.DatatypeProperty))
    g.remove((BGG.hasPublisher, RDFS.range, XSD.string))
    g.add((BGG.hasPublisher, RDF.type, OWL.ObjectProperty))
    g.add((BGG.hasPublisher, RDFS.range, PUBLISHER))

    # -- ratingFromTime: year the community rating data was collected --
    g.add((BGG.ratingFromTime, RDF.type, OWL.DatatypeProperty))
    g.add((BGG.ratingFromTime, RDFS.domain, BGG.Game))
    g.add((BGG.ratingFromTime, RDFS.range, XSD.int))

    # -- trenj:Theme and trenj:hasTheme (threnjen-dataset themes, distinct from bgg:Category) --
    g.bind("trenj", TRENJ)
    g.add((TRENJ.Theme, RDF.type, OWL.Class))
    g.add((TRENJ.Theme, RDFS.label,   Literal("Theme", lang="en")))
    g.add((TRENJ.Theme, RDFS.comment, Literal(
        "A thematic tag sourced from the threnjen Kaggle dataset, "
        "corresponding to BGG's category system. Distinct from bgg:Category.",
        lang="en"
    )))
    g.add((TRENJ.hasTheme, RDF.type,       OWL.ObjectProperty))
    g.add((TRENJ.hasTheme, RDFS.label,     Literal("has theme", lang="en")))
    g.add((TRENJ.hasTheme, RDFS.comment,   Literal(
        "Links a game to a threnjen theme tag.", lang="en"
    )))
    g.add((TRENJ.hasTheme, RDFS.domain,    BGG.Game))
    g.add((TRENJ.hasTheme, RDFS.range,     TRENJ.Theme))

    # New datatype property: personal rating 1–10
    HAS_PLAYER_RATING = BGG.hasPlayerRatingOpinion
    g.add((HAS_PLAYER_RATING, RDF.type, OWL.DatatypeProperty))
    g.add((HAS_PLAYER_RATING, RDFS.domain, PLAYER_OPINION))
    g.add((HAS_PLAYER_RATING, RDFS.range, XSD.decimal))
    g.add((HAS_PLAYER_RATING, RDFS.label, Literal("has player rating opinion", lang="en")))
    g.add((HAS_PLAYER_RATING, SH.minInclusive, Literal(1, datatype=XSD.decimal)))
    g.add((HAS_PLAYER_RATING, SH.maxInclusive, Literal(10, datatype=XSD.decimal)))

    # -- Upgrade rdfs:Class to owl:Class for consistency --
    for subj in list(g.subjects(RDF.type, RDFS.Class)):
        g.remove((subj, RDF.type, RDFS.Class))
        g.add((subj, RDF.type, OWL.Class))

    # -- rdfs:label and rdfs:comment for all classes (Comments Galore) --
    print("  Adding class labels and comments ...")
    CLASS_ANNOTATIONS = {
        BGG.Game: (
            "Game",
            "A board game listed on BoardGameGeek, carrying descriptive properties "
            "such as name, player count, play time, and aggregate community ratings.",
        ),
        BGG.Creator: (
            "Creator",
            "A person who designed or created a board game.",
        ),
        BGG.Category: (
            "Category",
            "A thematic grouping for board games as defined by BoardGameGeek "
            "(e.g. Fantasy, Economic, Card Game).",
        ),
        BGG.Mechanic: (
            "Mechanic",
            "A game-play mechanism or rule pattern as defined by BoardGameGeek "
            "(e.g. Auction/Bidding, Worker Placement, Dice Rolling).",
        ),
        BGG.MentalLoad: (
            "Mental Load",
            "An ordered enumeration of perceived cognitive difficulty: easy, moderate, or difficult.",
        ),
        BGG.Player: (
            "Player",
            "A person who plays board games; may own games and record personal opinions on them.",
        ),
        BGG.Size: (
            "Size",
            "A physical size category for a game box (e.g. small, medium, large).",
        ),
        BGG.Publisher: (
            "Publisher",
            "A company or individual that publishes board games.",
        ),
    }
    for cls_iri, (label, comment) in CLASS_ANNOTATIONS.items():
        g.add((cls_iri, RDFS.label,   Literal(label,   lang="en")))
        g.add((cls_iri, RDFS.comment, Literal(comment, lang="en")))

    # -- rdfs:label and rdfs:comment for all properties --
    print("  Adding property labels and comments ...")
    PROPERTY_ANNOTATIONS = {
        # Object Properties
        BGG.hasCategory: (
            "has category",
            "Links a game to one of its BoardGameGeek thematic categories.",
        ),
        BGG.hasCreator: (
            "has creator",
            "Links a game to a person who designed or otherwise created it.",
        ),
        BGG.hasMechanic: (
            "has mechanic",
            "Links a game to one of its BoardGameGeek game-play mechanics.",
        ),
        BGG.hasMentalLoad: (
            "has mental load",
            "Links a player opinion to the perceived cognitive difficulty of the game.",
        ),
        BGG.hasOpinionHolder: (
            "has opinion holder",
            "Links a PlayerOpinion to the player who holds that opinion.",
        ),
        BGG.hasOpinionOf: (
            "has opinion of",
            "Links a PlayerOpinion to the game being evaluated.",
        ),
        BGG.hasOwnershipOf: (
            "has ownership of",
            "Links a player to a game they own.",
        ),
        BGG.hasSize: (
            "has size",
            "Links a game to its physical box size category.",
        ),
        BGG.hasURL: (
            "has URL",
            "The BoardGameGeek web page URL for this game.",
        ),
        BGG.isCategoryOf: (
            "is category of",
            "Inverse of bgg:hasCategory; links a category to the games in that category.",
        ),
        BGG.isMechanicOf: (
            "is mechanic of",
            "Inverse of bgg:hasMechanic; links a mechanic to the games that use it.",
        ),
        BGG.isOwnedBy: (
            "is owned by",
            "Inverse of bgg:hasOwnershipOf; links a game to a player who owns it.",
        ),
        BGG.likesCategory: (
            "likes category",
            "Links a player to a thematic category they enjoy.",
        ),
        BGG.likesMechanic: (
            "likes mechanic",
            "Links a player to a game-play mechanic they enjoy.",
        ),
        # Datatype Properties
        BGG.hasBestNumPlayers: (
            "has best number of players",
            "The number of players at which the game plays best, according to BoardGameGeek community votes.",
        ),
        BGG.hasComment: (
            "has comment",
            "A free-text comment written by the player.",
        ),
        BGG.hasGeekRating: (
            "has Geek Rating",
            "The Geek Rating assigned by BoardGameGeek, computed from community votes and adjusted for vote count.",
        ),
        BGG.hasID: (
            "has ID",
            "The unique numeric identifier for the game on BoardGameGeek.",
        ),
        BGG.hasMaxGameTime: (
            "has max game time",
            "The maximum play time in minutes as listed on BoardGameGeek.",
        ),
        BGG.hasMaxPlayers: (
            "has max players",
            "The maximum number of players the game supports.",
        ),
        BGG.hasMaxRecAge: (
            "has max recommended age",
            "The maximum recommended player age in years.",
        ),
        BGG.hasMinGameTime: (
            "has min game time",
            "The minimum play time in minutes as listed on BoardGameGeek.",
        ),
        BGG.hasMinPlayers: (
            "has min players",
            "The minimum number of players required to play the game.",
        ),
        BGG.hasMinRecAge: (
            "has min recommended age",
            "The minimum recommended player age in years.",
        ),
        BGG.hasName: (
            "has name",
            "The name of the game as listed on BoardGameGeek.",
        ),
        BGG.hasPlayerRatingOpinion: (
            "has player rating opinion",
            "A personal rating of the game by the opinion holder, on a scale of 1 to 10.",
        ),
        BGG.hasPublisher: (
            "has publisher",
            "Links a game to its publisher.",
        ),
        BGG.hasRating: (
            "has rating",
            "The average community rating on BoardGameGeek, on a scale of 1 to 10.",
        ),
        BGG.ratingFromTime: (
            "rating from time",
            "The year in which the community rating data was collected.",
        ),
    }
    for prop_iri, (label, comment) in PROPERTY_ANNOTATIONS.items():
        g.add((prop_iri, RDFS.label,   Literal(label,   lang="en")))
        g.add((prop_iri, RDFS.comment, Literal(comment, lang="en")))

    # -- Remove stale editorial note and replace with current project notes --
    SKOS_NS = Namespace("http://www.w3.org/2004/02/skos/core#")
    for s, p, o in list(g.triples((None, SKOS_NS.editorialNote, None))):
        g.remove((s, p, o))
    g.add((BGG["boardgame-ontology"], SKOS_NS.editorialNote, Literal(
        "Future projects:\n"
        "- Comments Galore: Add rdfs:comment to all classes except Category and Mechanic instances.\n"
        "- More Data: Find an updated BGG dataset with post-2018 games.",
        lang="en"
    )))

    # -- Fix rdf:Property and mistyped DatatypeProperty --
    print("  Fixing property types ...")
    for prop in list(g.subjects(RDF.type, RDF.Property)):
        range_vals = list(g.objects(prop, RDFS.range))
        is_datatype = any(str(r).startswith(str(XSD)) for r in range_vals)
        g.remove((prop, RDF.type, RDF.Property))
        g.add((prop, RDF.type, OWL.DatatypeProperty if is_datatype else OWL.ObjectProperty))

    for prop in list(g.subjects(RDF.type, OWL.DatatypeProperty)):
        range_vals = list(g.objects(prop, RDFS.range))
        if any(not str(r).startswith(str(XSD)) for r in range_vals):
            g.remove((prop, RDF.type, OWL.DatatypeProperty))
            g.add((prop, RDF.type, OWL.ObjectProperty))

    # -- Personal collection --
    g.bind("svj", SVJ)
    SUSANNE = SVJ.SusanneVejdemo
    g.add((SUSANNE, RDF.type, BGG.Player))
    g.add((SUSANNE, RDFS.label, Literal("Susanne Vejdemo", lang="en")))
    # Games identified from photo of collection and found in dataset.
    # Still not in dataset: Pandemic: In the Lab, Science Tarot,
    # Don't Go Chasing Waterfalls, Xeno Language,
    # Hunt a Killer: Body on the Boardwalk.
    OWNED_GAMES: list[URIRef] = [
        BGG["11"],      # Bohnanza
        BGG["92828"],   # Dixit Odyssey
        BGG["148228"],  # Splendor
        BGG["42215"],   # Tobago
        BGG["31481"],   # Galaxy Trucker
        BGG["40692"],   # Small World
        BGG["68448"],   # 7 Wonders
        BGG["173346"],  # 7 Wonders Duel
        BGG["70323"],   # King of Tokyo
        BGG["136063"],  # Forbidden Desert
        BGG["65244"],   # Forbidden Island
        BGG["178900"],  # Codenames
        BGG["200147"],  # Kanagawa
        BGG["204583"],  # Kingdomino
        BGG["9209"],    # Ticket to Ride
        BGG["14996"],   # Ticket to Ride: Europe
        BGG["31627"],   # Ticket to Ride: Nordic Countries
        BGG["202670"],  # Ticket to Ride: Rails & Sails
        BGG["276894"],  # Ticket to Ride: London
        BGG["30549"],   # Pandemic
        BGG["230802"],  # Azul
        BGG["25669"],   # Qwirkle
        BGG["2281"],    # Pictionary
        BGG["1198"],    # SET
        BGG["119632"],  # IOTA
        BGG["66056"],   # The Rivals for Catan
        BGG["145475"],  # Hobbit Tales from the Green Dragon Inn
        BGG["5782"],    # Coloretto
        BGG["193737"],  # Star Trek Panic
        BGG["51"],      # Ricochet Robots
        BGG["36218"],   # Dominion
        BGG["21790"],   # Thurn and Taxis
        BGG["266192"],  # Wingspan
        BGG["295895"],  # Distilled
        BGG["284083"],  # The Crew: The Quest for Planet Nine
        BGG["324856"],  # The Crew: Mission Deep Sea
        BGG["414317"],  # Harmonies
        BGG["234190"],  # Unstable Unicorns
        BGG["299571"],  # Bandida
        BGG["299371"],  # The Emerald Flame
        BGG["270633"],  # Aeon's End: The New Age
    ]
    for game in OWNED_GAMES:
        g.add((SUSANNE, BGG.hasOwnershipOf, game))

    # -- Susanne's opinions: (game IRI, bgg:MentalLoad value, rating 1-10) --
    OPINIONS: list[tuple[URIRef, URIRef, int]] = [
        (BGG["230802"], BGG.moderate,  7),   # Azul
        (BGG["11"],     BGG.easy,      8),   # Bohnanza
        (BGG["178900"], BGG.moderate,  8),   # Codenames
        (BGG["5782"],   BGG.easy,     10),   # Coloretto
        (BGG["92828"],  BGG.moderate,  8),   # Dixit Odyssey
        (BGG["36218"],  BGG.moderate, 10),   # Dominion
        (BGG["136063"], BGG.moderate,  6),   # Forbidden Desert
        (BGG["65244"],  BGG.moderate,  6),   # Forbidden Island
        (BGG["31481"],  BGG.moderate,  6),   # Galaxy Trucker
        (BGG["145475"], BGG.difficult,10),   # Hobbit Tales from the Green Dragon Inn
        (BGG["119632"], BGG.moderate,  8),   # IOTA
        (BGG["200147"], BGG.moderate, 10),   # Kanagawa
        (BGG["70323"],  BGG.easy,      7),   # King of Tokyo
        (BGG["204583"], BGG.easy,      8),   # Kingdomino
        (BGG["2281"],   BGG.moderate,  4),   # Pictionary
        (BGG["25669"],  BGG.moderate,  5),   # Qwirkle
        (BGG["51"],     BGG.difficult,10),   # Ricochet Robots
        (BGG["1198"],   BGG.difficult,  8),  # SET
        (BGG["40692"],  BGG.difficult,  7),  # Small World
        (BGG["148228"], BGG.moderate,  7),   # Splendor
        (BGG["193737"], BGG.difficult,10),   # Star Trek Panic
        (BGG["66056"],  BGG.moderate,  5),   # The Rivals for Catan
        (BGG["21790"],  BGG.moderate, 10),   # Thurn and Taxis
        (BGG["9209"],   BGG.moderate, 10),   # Ticket to Ride
        (BGG["14996"],  BGG.moderate, 10),   # Ticket to Ride: Europe
        (BGG["31627"],  BGG.difficult,  8),  # Ticket to Ride: Nordic Countries
        (BGG["202670"], BGG.difficult,  8),  # Ticket to Ride: Rails & Sails
        (BGG["42215"],  BGG.difficult,  7),  # Tobago
        (BGG["68448"],  BGG.difficult,  7),  # 7 Wonders
        (BGG["173346"], BGG.moderate,  7),   # 7 Wonders Duel
        (BGG["30549"],  BGG.difficult, 10),  # Pandemic
        (BGG["266192"], BGG.easy,       9),  # Wingspan
        (BGG["295895"], BGG.difficult,  9),  # Distilled
        (BGG["284083"], BGG.easy,      10),  # The Crew: The Quest for Planet Nine
        (BGG["324856"], BGG.easy,      10),  # The Crew: Mission Deep Sea
        (BGG["414317"], BGG.easy,      10),  # Harmonies
        (BGG["234190"], BGG.easy,       4),  # Unstable Unicorns
        (BGG["299571"], BGG.easy,       4),  # Bandida
        (BGG["276894"], BGG.moderate,   7),  # Ticket to Ride: London
        (BGG["299371"], BGG.difficult,  4),  # The Emerald Flame
        (BGG["270633"], BGG.difficult, 10),  # Aeon's End: The New Age
    ]
    for game_iri, mental_load, rating in OPINIONS:
        game_id = str(game_iri).rsplit("#", 1)[-1]
        opinion = SVJ[f"SusanneOpinion_{game_id}"]
        g.add((opinion, RDF.type,               BGG.PlayerOpinion))
        g.add((opinion, BGG.hasOpinionOf,        game_iri))
        g.add((opinion, BGG.hasOpinionHolder,    SUSANNE))
        g.add((opinion, BGG.hasMentalLoad,       mental_load))
        g.add((opinion, BGG.hasPlayerRatingOpinion, Literal(rating, datatype=XSD.decimal)))

    output = "old_ttls/bgg_march2025_with_creator_iris.ttl"
    print(f"Serializing to {output} ...")
    serialize_organized(g, output)
    print("Done.")


if __name__ == "__main__":
    main()
