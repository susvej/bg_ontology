"""Quick smoke test: Gemma generates SPARQL, executes against GraphDB."""
import json, sys, requests
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OLLAMA_URL      = "http://localhost:11434"
MODEL           = "gemma4:e4b"
SPARQL_ENDPOINT = "http://localhost:7200/repositories/bgg"

# Load system prompts
with open("bgg_sparql_qa.ipynb", encoding="utf-8") as f:
    nb = json.load(f)
SYSTEM_SPARQL = SYSTEM_RESULT = None
for cell in nb["cells"]:
    src = "".join(cell["source"])
    if 'SYSTEM_SPARQL = """' in src and SYSTEM_SPARQL is None:
        s1 = src.index('SYSTEM_SPARQL = """') + len('SYSTEM_SPARQL = """')
        s2 = src.index('"""\n\nSYSTEM_RESULT')
        SYSTEM_SPARQL = src[s1:s2]
    if 'SYSTEM_RESULT = """' in src and SYSTEM_RESULT is None:
        r1 = src.index('SYSTEM_RESULT = """') + len('SYSTEM_RESULT = """')
        r2 = src.index('"""\n\nprint')
        SYSTEM_RESULT = src[r1:r2]

print(f"Prompts loaded: SPARQL={len(SYSTEM_SPARQL)} chars, RESULT={len(SYSTEM_RESULT)} chars")

# Stage 1: Generate SPARQL
print("\nGenerating SPARQL (may take 20-40s)...")
resp = requests.post(f"{OLLAMA_URL}/api/chat", json={
    "model": MODEL,
    "messages": [
        {"role": "system", "content": SYSTEM_SPARQL},
        {"role": "user",   "content": "What are the top 3 highest-rated board games?"},
    ],
    "stream": False,
    "options": {"num_predict": 2048, "num_ctx": 32768, "temperature": 0},
}, timeout=300)
resp.raise_for_status()

raw = resp.json()["message"]["content"].strip()
print(f"Raw response ({len(raw)} chars):")
print(raw[:800])
print("---")

# Clean up the response
query = raw
if query.startswith("```"):
    query = "\n".join(l for l in query.splitlines() if not l.startswith("```")).strip()
lines = query.splitlines()
for i, line in enumerate(lines):
    if line.strip().upper().startswith(("PREFIX", "SELECT", "ASK")):
        query = "\n".join(lines[i:])
        break

print(f"\nCleaned query ({len(query)} chars):")
print(query[:500])

if len(query.strip()) < 20:
    print("\nERROR: Query too short — Gemma likely did not generate valid SPARQL.")
    sys.exit(1)

# Stage 2: Execute
print("\nExecuting against GraphDB...")
gr = requests.post(
    SPARQL_ENDPOINT,
    data={"query": query},
    headers={"Accept": "application/sparql-results+json"},
    timeout=90,
)
if not gr.ok:
    print(f"GraphDB error {gr.status_code}:")
    print(gr.text[:400])
    sys.exit(1)

bindings = gr.json()["results"]["bindings"]
print(f"Results: {len(bindings)} binding(s)")
for b in bindings[:3]:
    vals = {k: v["value"] for k, v in b.items()}
    print(" ", vals)

# Stage 3: Interpret
print("\nInterpreting results...")
payload = json.dumps({
    "question": "What are the top 3 highest-rated board games?",
    "sparql_query": query,
    "result_count": len(bindings),
    "results": bindings[:10],
}, ensure_ascii=False)
resp2 = requests.post(f"{OLLAMA_URL}/api/chat", json={
    "model": MODEL,
    "messages": [
        {"role": "system", "content": SYSTEM_RESULT},
        {"role": "user",   "content": payload},
    ],
    "stream": False,
    "options": {"num_predict": 512, "temperature": 0},
}, timeout=180)
resp2.raise_for_status()
print("Answer:", resp2.json()["message"]["content"].strip())
print("\nSmoke test PASSED.")
