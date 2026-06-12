"""Add skos:altLabel triples to vocabulary instances in bgg_main.ttl.

Also fixes a handful of labels that still have CamelCase or slash-without-spaces
forms left over from the source data (not caught by the underscore/Theme_ rules
in fix_vocab_labels.py).

Safe to re-run: removes all existing skos:altLabel triples first.
"""
from rdflib import Graph, Namespace, Literal, RDFS

from convert_creators import BGG, TRENJ, serialize_organized

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

# Labels in the source data that need a targeted fix before altLabels are added.
# Key = current label string; value = corrected label string.
LABEL_FIXES: dict[str, str] = {
    "MurderMystery":        "Murder Mystery",
    "Murder/Mystery":       "Murder Mystery",    # same IRI, slash form from threnjen
    "TableauBuilding":      "Tableau Building",
    "Spies/Secret Agents":  "Spies / Secret Agents",
    "SpiesSecret Agents":   "Spies / Secret Agents",
}

ALT_LABELS: dict[str, list[str]] = {
    # ---- Categories (some instances are also trenj:Theme) ----
    "Science Fiction":          ["sci-fi", "scifi", "SF", "futuristic"],
    "World War I":              ["WW1", "WWI", "world war one", "first world war", "the great war"],
    "World War II":             ["WW2", "WWII", "world war two", "second world war", "world war 2"],
    "Spies / Secret Agents":   ["spies", "spy", "espionage", "secret agents", "intelligence"],
    "Murder Mystery":           ["whodunit", "whodunnit", "detective mystery"],
    "Mature / Adult":           ["18+", "adult content", "adult game", "mature content", "taboo content"],
    "Childrens Game":           ["kids game", "for children", "for kids", "children's game"],
    "Miniatures":               ["minis", "miniature wargame", "minis game"],
    "Nautical":                 ["naval", "ships", "sailing", "sea", "maritime"],
    "Trains":                   ["railroad", "railway", "train game"],
    "Wargame":                  ["war game", "wargaming"],
    "Print & Play":             ["PnP", "print and play", "free game"],
    "Trivia":                   ["quiz", "quiz game", "knowledge game"],
    "Maze":                     ["labyrinth"],
    "American Revolutionary War": ["American Revolution", "revolutionary war",
                                   "war of independence", "independence war"],
    "Napoleonic":               ["Napoleon", "Napoleonic Wars"],
    "Prehistoric":              ["stone age", "caveman", "dinosaurs"],
    "American West":            ["Wild West", "cowboys", "western", "frontier"],
    "Movies / TV / Radio theme": ["film", "television", "media tie-in", "licensed game"],
    "Medieval":                 ["middle ages"],
    "Arabian":                  ["middle eastern"],
    "Civilization":             ["civ game", "civ"],
    "Economic":                 ["economy", "business", "finance", "financial"],
    "Deduction":                ["logic puzzle", "detective"],
    "Post-Napoleonic":          ["Victorian era", "Victorian", "19th century"],
    "City Building":            ["city builder", "urban planning"],
    "Fighting":                 ["combat", "battle"],
    "Humor":                    ["comedy", "funny"],
    "Math":                     ["maths", "mathematics"],
    "Comic Book / Strip":       ["comics", "graphic novel"],
    "Card Game":                ["card-based"],
    "Aviation / Flight":        ["airplane", "aircraft", "flying", "pilot"],
    "Bluffing":                 ["deception", "lying", "social deduction"],
    "Memory":                   ["pairs", "matching pairs"],
    "Religious":                ["faith"],
    "Korean War":               ["Korean conflict"],
    # ---- Mechanics ----
    "Action Point Allowance System": ["action points", "AP system", "action economy"],
    "Action Points":            ["AP", "action economy", "action tokens"],
    "Co-operative Play":        ["cooperative", "co-op", "coop", "team game"],
    "Cooperative Game":         ["cooperative", "co-op", "coop", "team game"],
    "Role Playing":             ["RPG", "roleplay", "role-play", "roleplaying"],
    "Tile Placement":           ["tile laying", "tile game"],
    "Variable Player Powers":   ["asymmetric", "asymmetric powers", "asymmetric gameplay"],
    "Tableau Building":         ["engine building", "engine builder"],
    "Narrative Choice / Paragraph": ["choose your own adventure", "CYOA", "story game"],
    "Hidden Roles":             ["hidden identity", "social deduction", "secret role"],
    "Solo / Solitaire Game":    ["solo game", "single player", "1 player", "solitaire"],
    "Semi-Cooperative Game":    ["semi-coop", "semi cooperative"],
    "Pick-up and Deliver":      ["pickup and deliver", "PnD", "delivery game"],
    "Deck, Bag, and Pool Building": ["deck building", "deckbuilding", "deck builder"],
    "Deck Construction":        ["deck building", "deckbuilding"],
    "Trick-taking":             ["trick taking"],
    "Roll / Spin and Move":     ["roll and move", "dice movement"],
    "Simultaneous Action Selection": ["simultaneous play", "secret selection"],
    "Hex-and-Counter":          ["hex wargame", "hex game"],
    "Area Majority / Influence": ["area control", "influence game"],
    "Card Drafting":            ["card draft", "drafting game"],
    "Traitor Game":             ["hidden traitor", "betrayal game"],
    "Hand Management":          ["card management", "hand optimization"],
    "Programmed Movement":      ["programming mechanic"],
    "Legacy Game":              ["campaign game", "persistent game"],
    "Push Your Luck":           ["risk taking"],
    "Stock Holding":            ["stock market", "shares", "investment"],
    "Real-Time":                ["speed game"],
    "Secret Unit Deployment":   ["secret placement"],
    "Negotiation":              ["diplomacy"],
    "Storytelling":             ["narrative game", "story game"],
    "Zone of Control":          ["ZOC", "zones of control"],
    # ---- Themes (clean labels — no "Theme_" prefix) ----
    "Cthulhu Mythos":           ["Cthulhu", "Lovecraft", "lovecraftian", "eldritch horror"],
    "Vikings":                  ["viking", "norse", "norsemen"],
    "Post-Apocalyptic":         ["post apocalypse", "apocalyptic", "end of the world", "dystopia"],
    "Archaeology / Paleontology": ["archaeology", "dinosaurs", "fossils"],
    "Anime / Manga":            ["anime", "manga", "japanese animation"],
    "Kaiju":                    ["giant monsters", "monster attack"],
    "Food / Cooking":           ["cooking", "culinary", "chef", "food game"],
    "Samurai":                  ["feudal japan", "japan", "samurai game"],
    "Steampunk":                ["steam punk"],
    "Cyberpunk":                ["cyber punk", "neon noir"],
    "Evolution":                ["natural selection", "darwinian"],
    "Survival":                 ["survival game", "wilderness survival"],
    "Robots":                   ["android", "AI game"],
    "Native Americans / First Peoples": ["indigenous", "first nations"],
    "Aztecs":                   ["mesoamerican", "pre-columbian"],
    "Druids":                   ["celtic", "pagan"],
    "Ecology":                  ["ecosystem", "environmentalism"],
    "Alternate History":        ["what if", "counterfactual"],
}


def apply_label_fixes(g: Graph) -> int:
    """Rename specific messy rdfs:label values to clean forms."""
    fixed = 0
    for old_str, new_str in LABEL_FIXES.items():
        old_lit = Literal(old_str, lang="en")
        new_lit = Literal(new_str, lang="en")
        for subj in list(g.subjects(RDFS.label, old_lit)):
            g.remove((subj, RDFS.label, old_lit))
            # Only add the new label if not already present
            if (subj, RDFS.label, new_lit) not in g:
                g.add((subj, RDFS.label, new_lit))
            fixed += 1
    return fixed


def main() -> None:
    print("Loading bgg_main.ttl...")
    g = Graph()
    g.parse("bgg_main.ttl", format="turtle")
    g.bind("skos", SKOS)
    print(f"  {len(g)} triples loaded")

    # Remove any existing skos:altLabel triples (safe re-run)
    existing = list(g.triples((None, SKOS.altLabel, None)))
    for t in existing:
        g.remove(t)
    if existing:
        print(f"  Cleared {len(existing)} existing skos:altLabel triples")

    # Fix residual label issues before building the lookup index
    fixed = apply_label_fixes(g)
    print(f"  Fixed {fixed} residual label issues")

    # Build label → list-of-subjects index
    label_to_subjs: dict[str, list] = {}
    for subj, _, label_lit in g.triples((None, RDFS.label, None)):
        label_to_subjs.setdefault(str(label_lit), []).append(subj)

    added = 0
    not_found = []

    for label, alts in ALT_LABELS.items():
        subjects = label_to_subjs.get(label, [])
        if not subjects:
            not_found.append(label)
            continue
        for subj in subjects:
            for alt in alts:
                g.add((subj, SKOS.altLabel, Literal(alt, lang="en")))
            added += len(alts)

    if not_found:
        print(f"  WARNING — labels not found ({len(not_found)}): {not_found}")

    print(f"  Added {added} skos:altLabel triples across {len(ALT_LABELS) - len(not_found)} instances")

    print("Serializing bgg_main.ttl...")
    serialize_organized(g, "bgg_main.ttl")
    print("Done.")


if __name__ == "__main__":
    main()
