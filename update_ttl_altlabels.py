#!/usr/bin/env python3
"""
Apply broken-label fixes and add skos:altLabel triples to bgg_kaggle2025.ttl,
then update the vocabulary section in Cell 2 of bgg_sparql_qa.ipynb.
"""

import json
import re

TTL_FILE = "bgg_kaggle2025.ttl"
NB_FILE  = "bgg_sparql_qa.ipynb"

# --- 1. Broken label string replacements ---
# 9 explicitly requested by user + 3 additional found blocking altLabel insertion
LABEL_FIXES = {
    '"Childrens_Game"@en':             '"Children\'s Game"@en',
    '"MurderMystery"@en':              '"Murder Mystery"@en',
    '"SpiesSecret_Agents"@en':         '"Spies / Secret Agents"@en',
    '"AuctionBidding"@en':             '"Auction / Bidding"@en',
    '"BettingWagering"@en':            '"Betting / Wagering"@en',
    '"RouteNetwork_Building"@en':      '"Route / Network Building"@en',
    '"TableauBuilding"@en':            '"Tableau Building"@en',
    '"Murder/Mystery"@en':             '"Murder Mystery"@en',
    '"Spies/Secret Agents"@en':        '"Spies / Secret Agents"@en',
    # Additional fixes: underscore versions found in mechanic instances
    '"Action_Point_Allowance_System"@en': '"Action Point Allowance System"@en',
    '"Card_Drafting"@en':              '"Card Drafting"@en',
    '"Co-operative_Play"@en':          '"Co-operative Play"@en',
}

# --- 2. altLabels keyed by the exact rdfs:label string in the TTL ---
# Themes use "Theme_NAME" format (underscore separator from threnjen dataset).
# The altLabel SPARQL property path  rdfs:label|skos:altLabel  will resolve these.
ALT_LABELS: dict[str, list[str]] = {
    # ---- Categories (some instances are also trenj:Theme) ----
    "Science Fiction":          ["sci-fi", "scifi", "SF", "futuristic"],
    "World War I":              ["WW1", "WWI", "world war one", "first world war", "the great war"],
    "World War II":             ["WW2", "WWII", "world war two", "second world war", "world war 2"],
    "Spies / Secret Agents":    ["spies", "spy", "espionage", "secret agents", "intelligence"],
    "Murder Mystery":           ["whodunit", "whodunnit", "detective mystery"],
    "Mature / Adult":           ["18+", "adult content", "adult game", "mature content", "taboo content"],
    "Children's Game":          ["kids game", "for children", "for kids"],
    "Miniatures":               ["minis", "miniature wargame", "minis game"],
    "Nautical":                 ["naval", "ships", "sailing", "sea", "maritime"],
    "Trains":                   ["railroad", "railway", "train game", "rail road", "rail way"],
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
    # ---- Themes (actual TTL rdfs:label uses "Theme_NAME" prefix) ----
    "Theme_Cthulhu Mythos":     ["Cthulhu", "Lovecraft", "lovecraftian", "eldritch horror"],
    "Theme_Vikings":            ["viking", "norse", "norsemen"],
    "Theme_Post-Apocalyptic":   ["post apocalypse", "apocalyptic", "end of the world", "dystopia"],
    "Theme_Archaeology / Paleontology": ["archaeology", "dinosaurs", "fossils"],
    "Theme_Anime / Manga":      ["anime", "manga", "japanese animation"],
    "Theme_Kaiju":              ["giant monsters", "monster attack"],
    "Theme_Food / Cooking":     ["cooking", "culinary", "chef", "food game"],
    "Theme_Samurai":            ["feudal japan", "japan", "samurai game"],
    "Theme_Steampunk":          ["steam punk"],
    "Theme_Cyberpunk":          ["cyber punk", "neon noir"],
    "Theme_Evolution":          ["natural selection", "darwinian"],
    "Theme_Survival":           ["survival game", "wilderness survival"],
    "Theme_Robots":             ["android", "AI game"],
    "Theme_Native Americans / First Peoples": ["indigenous", "first nations"],
    "Theme_Aztecs":             ["mesoamerican", "pre-columbian"],
    "Theme_Druids":             ["celtic", "pagan"],
    "Theme_Ecology":            ["ecosystem", "environmentalism"],
    "Theme_Alternate History":  ["alternate history", "what if", "counterfactual"],
}


def make_alt_label_line(alts: list[str]) -> str:
    parts = ', '.join(f'"{a}"@en' for a in alts)
    return f'    skos:altLabel {parts} .'


def update_ttl() -> None:
    print(f"Reading {TTL_FILE}...")
    with open(TTL_FILE, encoding="utf-8") as f:
        content = f.read()
    print(f"  {content.count(chr(10))+1} lines, {len(content):,} chars")

    # Pass 1: broken label fixes
    print("Applying broken-label fixes...")
    fix_count = 0
    for old, new in LABEL_FIXES.items():
        n = content.count(old)
        if n:
            content = content.replace(old, new)
            print(f"  {old!r} -> {new!r}  ({n}×)")
            fix_count += n
        else:
            print(f"  WARN: {old!r} not found — already fixed?")
    print(f"  {fix_count} replacements total")

    # Pass 2: insert skos:altLabel after matching rdfs:label lines
    print("Inserting skos:altLabel triples...")
    lines = content.split("\n")
    result: list[str] = []
    added = 0
    skipped_already = 0

    for i, line in enumerate(lines):
        result.append(line)
        # Only act on rdfs:label lines that end the property block (period)
        stripped = line.rstrip()
        if "rdfs:label" not in stripped or not stripped.endswith(" ."):
            continue
        # Check whether next non-blank line is already a skos:altLabel (skip if so)
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j].strip()
            if nxt:
                if nxt.startswith("skos:altLabel"):
                    skipped_already += 1
                break
        else:
            pass

        for label, alts in ALT_LABELS.items():
            if f'"{label}"@en' in stripped:
                # Change trailing ' .' to ' ;' and append altLabel line
                result[-1] = stripped[:-2] + " ;"
                result.append(make_alt_label_line(alts))
                added += 1
                break

    print(f"  {added} skos:altLabel blocks added  ({skipped_already} already present, skipped)")

    content = "\n".join(result)
    with open(TTL_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Written back to {TTL_FILE}")


def update_notebook() -> None:
    """Fix broken label strings in the hardcoded vocab list in Cell 2 of the notebook."""
    print(f"\nUpdating vocab labels in {NB_FILE}...")
    with open(NB_FILE, encoding="utf-8-sig") as f:
        nb = json.load(f)

    # Notebook label fixes: same broken→fixed pairs, without the @en suffix
    nb_fixes = {
        "Childrens_Game":             "Children's Game",
        "MurderMystery":              "Murder Mystery",
        "SpiesSecret_Agents":         "Spies / Secret Agents",
        "AuctionBidding":             "Auction / Bidding",
        "BettingWagering":            "Betting / Wagering",
        "RouteNetwork_Building":      "Route / Network Building",
        "TableauBuilding":            "Tableau Building",
        "Murder/Mystery":             "Murder Mystery",
        "Spies/Secret Agents":        "Spies / Secret Agents",
        "Action_Point_Allowance_System": "Action Point Allowance System",
        "Card_Drafting":              "Card Drafting",
        "Co-operative_Play":          "Co-operative Play",
    }

    nb_fix_count = 0
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        src = cell.get("source", [])
        # source may be a plain string or a list; normalise to joined string
        joined = src if isinstance(src, str) else "".join(src)
        changed = False
        for old, new in nb_fixes.items():
            if old in joined:
                joined = joined.replace(old, new)
                nb_fix_count += 1
                changed = True
        if changed:
            lines = joined.split("\n")
            cell["source"] = [l + "\n" for l in lines[:-1]] + ([lines[-1]] if lines[-1] else [])

    with open(NB_FILE, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"  {nb_fix_count} label strings fixed in notebook")


if __name__ == "__main__":
    update_ttl()
    update_notebook()
    print("\nAll done.")
