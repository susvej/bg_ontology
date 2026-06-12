"""Fix vocabulary labels in bgg_main.ttl.

Rules:
- Category / Mechanic labels:  if a clean label (no underscores) already
  exists on the same IRI, drop the underscore duplicate.
  If only an underscore label exists, replace underscores with spaces.
- Theme labels: strip the "Theme_" prefix, then replace remaining
  underscores with spaces.
"""
from rdflib import Graph, Literal, RDF, RDFS

from convert_creators import BGG, TRENJ, serialize_organized


def normalize(s: str) -> str:
    if s.startswith("Theme_"):
        s = s[6:]
    return s.replace("_", " ")


def is_messy(s: str) -> bool:
    return "_" in s or s.startswith("Theme_")


def fix_labels(g: Graph) -> int:
    fixed = 0
    for rdf_type in [BGG.Category, BGG.Mechanic, TRENJ.Theme]:
        for subj in list(g.subjects(RDF.type, rdf_type)):
            labels = [(str(l), l) for l in g.objects(subj, RDFS.label)
                      if isinstance(l, Literal)]
            messy  = [(s, node) for s, node in labels if is_messy(s)]
            if not messy:
                continue

            clean_existing = {s for s, _ in labels if not is_messy(s)}

            for s, node in messy:
                g.remove((subj, RDFS.label, node))
                fixed += 1

            if not clean_existing:
                # No clean label at all — add normalized versions (deduped)
                for clean in {normalize(s) for s, _ in messy}:
                    g.add((subj, RDFS.label, Literal(clean, lang="en")))

            # If clean labels already existed, we just dropped the messy ones.

    return fixed


def main() -> None:
    print("Loading bgg_main.ttl...")
    g = Graph()
    g.parse("bgg_main.ttl", format="turtle")
    print(f"  {len(g)} triples loaded")

    fixed = fix_labels(g)
    print(f"  Fixed {fixed} labels")

    print("Serializing bgg_main.ttl...")
    serialize_organized(g, "bgg_main.ttl")
    print("Done.")


if __name__ == "__main__":
    main()
