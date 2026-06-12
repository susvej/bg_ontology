import glob
from rdflib import Graph, RDF, RDFS, Namespace

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

ttl_files = sorted(glob.glob("*.ttl"))
print(f"Found {len(ttl_files)} TTL files\n")

for path in ttl_files:
    print(f"=== {path} ===")
    try:
        g = Graph()
        g.parse(path, format="turtle")
        print(f"  Parsed OK - {len(g)} triples")

        rdfs_classes = list(g.subjects(RDF.type, RDFS.Class))
        print(f"  rdfs:Class subjects: {len(rdfs_classes)}")
        for s in rdfs_classes:
            print(f"    {s}")

        notes = list(g.triples((None, SKOS.editorialNote, None)))
        print(f"  Editorial notes: {len(notes)}")

        with open(path, encoding="utf-8") as f:
            prefix_lines = [l.strip() for l in f if l.startswith("@prefix")]
        print(f"  Prefixes ({len(prefix_lines)}): {', '.join(l.split()[1] for l in prefix_lines)}")

    except Exception as e:
        print(f"  ERROR: {e}")
    print()
