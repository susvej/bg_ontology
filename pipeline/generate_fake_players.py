import csv
import random
from rdflib import Graph, Namespace, URIRef, Literal, RDF, RDFS, XSD

random.seed(42)  # reproducible output

BGG  = Namespace("https://raw.githubusercontent.com/susvej/bg_ontology/")
FAKE = Namespace("https://vejdemo.se/boardgames/fake#")

FIRST_NAMES = [
    # Swedish/Nordic
    "Erik", "Lars", "Anna", "Maria", "Johan", "Sara", "Emma", "Bjorn",
    "Astrid", "Sigrid", "Ingrid", "Gunnar", "Sven", "Maja", "Oskar", "Lena",
    "Anders", "Kristina", "Elsa", "Gustav", "Hanna", "Nils", "Britta", "Ulf",
    # English
    "James", "John", "Mary", "Patricia", "Michael", "Jennifer", "David",
    "Linda", "Robert", "Barbara", "William", "Susan", "Richard", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Daniel", "Lisa", "Matthew",
    "Nancy", "Anthony", "Betty", "Mark", "Margaret", "Paul", "Sandra",
    # German
    "Hans", "Klaus", "Friedrich", "Helga", "Wolfgang", "Ursula", "Dieter",
    "Monika", "Heinrich", "Gertrude", "Walter", "Hildegard",
    # French
    "Pierre", "Marie", "Jean", "Claire", "François", "Isabelle", "Henri",
    "Céline", "Louis", "Marguerite",
    # Spanish/Portuguese
    "Carlos", "Ana", "Miguel", "Carmen", "José", "Lucia", "Diego", "Isabel",
    "Alejandro", "Sofia", "Rafael", "Elena",
    # Japanese
    "Kenji", "Yuki", "Hiroshi", "Akiko", "Takeshi", "Naomi", "Ryo", "Mika",
    # Other
    "Andrei", "Natasha", "Fatima", "Kwame", "Amara", "Leila", "Tariq",
    "Priya", "Arjun", "Mei", "Wei", "Hana",
]

LAST_NAMES = [
    # Swedish
    "Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson", "Larsson",
    "Olsson", "Persson", "Svensson", "Gustafsson", "Pettersson", "Jonsson",
    "Lindström", "Lindqvist", "Bergström", "Lindberg", "Magnusson", "Axelsson",
    # English
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis",
    "Wilson", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Thompson",
    "White", "Harris", "Clark", "Lewis", "Robinson", "Walker", "Hall",
    "Allen", "Young", "King", "Wright", "Scott", "Green", "Baker", "Adams",
    # German
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
    "Becker", "Schulz", "Hoffmann", "Schäfer", "Koch",
    # French
    "Dupont", "Martin", "Bernard", "Dubois", "Laurent", "Moreau", "Girard",
    "Petit", "Roux", "Vincent",
    # Spanish
    "García", "Rodríguez", "Martínez", "López", "Sánchez", "Pérez",
    "González", "Hernández", "Díaz", "Torres",
    # Japanese
    "Tanaka", "Suzuki", "Watanabe", "Yamamoto", "Nakamura", "Kobayashi",
    "Sato", "Ito", "Kato", "Yoshida",
    # Other
    "Okafor", "Mensah", "Hassan", "Nkrumah", "Patel", "Sharma", "Singh",
    "Nguyen", "Kim", "Chen", "Zhang", "Ivanov",
]

MENTAL_LOADS = [BGG.easy, BGG.moderate, BGG.difficult]


def name_to_local(first: str, last: str) -> str:
    """Make a clean CamelCase local IRI part from a name."""
    import unicodedata, re
    full = first + last
    normalized = unicodedata.normalize("NFKD", full)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    words = re.split(r"[^a-zA-Z0-9]+", ascii_str)
    return "".join(w.capitalize() for w in words if w)


def load_game_ids(csv_path: str, id_col: str) -> list[str]:
    with open(csv_path, encoding="utf-8") as f:
        return [row[id_col] for row in csv.DictReader(f) if row[id_col].strip()]


def main():
    game_ids = load_game_ids("threnjen bg db/games.csv", "BGGId")
    print(f"Loaded {len(game_ids)} games (threnjen-enriched only)")

    g = Graph()
    g.bind("bgg",  BGG)
    g.bind("fake", FAKE)
    g.bind("rdf",  RDF)
    g.bind("rdfs", RDFS)
    g.bind("xsd",  XSD)

    used_locals: set[str] = set()

    player_count = 0
    opinion_count = 0

    for i in range(200):
        first = random.choice(FIRST_NAMES)
        last  = random.choice(LAST_NAMES)
        local = name_to_local(first, last)

        # Deduplicate: append index if name already used
        if local in used_locals:
            local = f"{local}{i}"
        used_locals.add(local)

        player_iri = FAKE[local]
        label = f"{first} {last}"
        g.add((player_iri, RDF.type,     BGG.Player))
        g.add((player_iri, RDFS.label,   Literal(label, lang="en")))

        n_games = random.randint(10, 30)
        owned   = random.sample(game_ids, n_games)

        for game_id in owned:
            game_iri = BGG[game_id]
            g.add((player_iri, BGG.hasOwnershipOf, game_iri))

            opinion_iri = FAKE[f"{local}_opinion_{game_id}"]
            g.add((opinion_iri, RDF.type,                    BGG.PlayerOpinion))
            g.add((opinion_iri, BGG.hasOpinionHolder,        player_iri))
            g.add((opinion_iri, BGG.hasOpinionOf,            game_iri))
            g.add((opinion_iri, BGG.hasMentalLoad,           random.choice(MENTAL_LOADS)))
            g.add((opinion_iri, BGG.hasPlayerRatingOpinion,
                   Literal(random.randint(1, 10), datatype=XSD.decimal)))
            opinion_count += 1

        player_count += 1

    output = "../data/fake_players.ttl"
    print(f"Serializing {player_count} players, {opinion_count} opinions ...")
    g.serialize(output, format="turtle")
    print(f"Written to {output}")
    print(f"Total triples: {len(g)}")


if __name__ == "__main__":
    main()
