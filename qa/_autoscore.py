"""Auto-score blank entries in qa_log.jsonl using Claude Haiku."""
import json, os, sys, time
from pathlib import Path
import xml.etree.ElementTree as ET
import anthropic

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── API key ───────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
if not ANTHROPIC_API_KEY:
    for line in Path(".env").read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            ANTHROPIC_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-haiku-4-5-20251001"

# ── Load verified answers from XML ───────────────────────────────
tree = ET.parse("GoldenQandA_June17.xml")
root = tree.getroot()

VERIFIED = {}   # qid -> {"text": question, "criteria": ..., "answer_summary": ...}
for query in root.iter("query"):
    qid = query.get("id")
    text_el = query.find("text")
    crit_el  = query.find("evaluation_criteria")
    va_el    = query.find("verified_answer")
    if qid is None:
        continue
    names = []
    if va_el is not None:
        for result in va_el.findall("result"):
            n = result.find("name")
            if n is not None and n.text:
                names.append(n.text.strip())
    VERIFIED[qid] = {
        "text":     text_el.text.strip() if text_el is not None else "",
        "criteria": crit_el.text.strip() if crit_el is not None else "",
        "names":    names,
    }

# ── QSQL reference answers (manually curated) ────────────────────
QSQL_REF = {
    "QSQL1": {
        "criteria": "Should return sea-themed games with route/network mechanic not owned by Susanne Vejdemo, Gertrude Young, or Maja Brown. Any reasonable list of such games is correct.",
        "notes": "Both SPARQL and SQL produce valid results. No single ground truth."
    },
    "QSQL2": {
        "criteria": "Should return highly-rated games not owned by Susanne, designed by someone who also designed a game Gertrude rates 8+. Valid results exist.",
        "notes": "Both agents typically return valid results."
    },
    "QSQL3": {
        "criteria": "Game neither player owns; designer has a Susanne 8+ game; game has a mechanic from Gertrude's 8+ games. Complex multi-hop filter.",
        "notes": "Both agents typically return valid results if query is correct."
    },
    "QSQL4": {
        "criteria": "Should rank players by number of games shared with Susanne Vejdemo. Correct answer: top is Barbara Lewis with 2 shared games, then many players with 1 shared game. Max overlap is only 2 due to sparse ownership data.",
        "notes": "Score 9/10 if returns correct ranking. Deduct if Susanne included in results, if ordering is wrong, or if agent doesn't note the sparse data issue. Score 10 only if agent notes max=2 is a data sparsity artefact."
    },
    "QSQL5": {
        "criteria": "Should return a 3-hop designer chain: Gertrude's 8+ game -> designer -> another game by that designer -> co-designer -> recommended game not owned by Susanne or Gertrude. Valid chains exist.",
        "notes": "Both agents produce valid chains."
    },
    "QSQL6": {
        "criteria": "Should return ALL players reachable from Susanne through chains of shared game ownership (transitive closure). Correct answer: 202 unique community members (SPARQL). SQL agent has a known bug: returns 203 because Susanne herself is re-added via the recursive arm.",
        "notes": "SPARQL: 202 members = correct (10/10). SQL: 203 members = off-by-one bug (7/10). If SQL returns 202 it somehow avoided the bug (9/10)."
    },
    "QSQL7": {
        "criteria": "Should return all games in the Ticket to Ride game family (reimplementation tree from BGG #9209), any depth. Correct: 22 games total including the original.",
        "notes": "Both agents return 22 games correctly. Score 10/10 if correct count and reasonable game names shown."
    },
    "QSQL8": {
        "criteria": "Should return all games with their total reimplementation family size at any depth. Correct top results: CATAN 33, Star Wars: Epic Duels 25, Love Letter 25, Ticket to Ride 21, Escape Room 21. Both SPARQL and SQL return identical results (861 games).",
        "notes": "Score 10/10 if top results are correct. Both agents should get this right."
    },
}

SYSTEM_SCORE = """\
You are an evaluator for a board game knowledge graph QA system.
You will be given:
- A question asked to an AI agent
- Evaluation criteria / verified correct answer
- The agent's actual answer

Score the answer 1–10 and write a brief comment (1–2 sentences).

Scoring guide:
10 = Fully correct, complete, well-explained
9  = Correct but minor issue (e.g. missing edge case, truncated, no LIMIT)
8  = Mostly correct, small factual gap
7  = Partially correct, missing key info or minor error
5–6 = Significant gap or partial data
3–4 = Largely wrong but some relevant info
1–2 = Completely wrong or refused

Respond ONLY with valid JSON: {"score": <int 1-10>, "comment": "<string>"}
No other text."""

def score_entry(entry: dict) -> tuple[int, str]:
    qid = entry["question_id"]
    question = entry["question"]
    answer = entry.get("answer", "") or ""

    if qid in VERIFIED:
        ref = VERIFIED[qid]
        ref_text = f"Evaluation criteria: {ref['criteria']}"
        if ref["names"]:
            ref_text += f"\nVerified correct answer includes these names (in order): {', '.join(ref['names'][:15])}"
    elif qid in QSQL_REF:
        ref = QSQL_REF[qid]
        ref_text = f"Evaluation criteria: {ref['criteria']}\nNotes: {ref['notes']}"
    else:
        ref_text = "No verified answer available. Score based on answer quality and plausibility."

    user_msg = f"""Question: {question}

{ref_text}

Agent answer:
{answer[:2000]}"""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=SYSTEM_SCORE,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text.strip()
    try:
        parsed = json.loads(raw)
        return int(parsed["score"]), str(parsed["comment"])
    except Exception:
        # fallback: extract from raw text
        import re
        m = re.search(r'"score"\s*:\s*(\d+)', raw)
        score = int(m.group(1)) if m else 5
        m2 = re.search(r'"comment"\s*:\s*"([^"]+)"', raw)
        comment = m2.group(1) if m2 else raw[:120]
        return score, comment


# ── Load, score, rewrite ──────────────────────────────────────────
log_path = Path("qa_log.jsonl")
entries = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]

blank = [(i, e) for i, e in enumerate(entries)
         if e.get("score") is None or e.get("score") == ""]

print(f"Total entries: {len(entries)}")
print(f"Blank score entries to process: {len(blank)}")
print()

for n, (i, entry) in enumerate(blank, 1):
    qid   = entry["question_id"]
    agent = entry["agent"]
    print(f"[{n}/{len(blank)}] {agent} | {qid} ... ", end="", flush=True)
    try:
        score, comment = score_entry(entry)
        entries[i]["score"]   = score
        entries[i]["comment"] = comment
        print(f"score={score}  {comment[:70]}")
    except Exception as e:
        print(f"ERROR: {e}")
    time.sleep(0.3)  # gentle rate limiting

# Write back
log_path.write_text(
    "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
    encoding="utf-8"
)
print(f"\nDone. {log_path} updated.")

# Summary
from collections import defaultdict
by_agent_qid = defaultdict(list)
for i, e in blank:
    if entries[i].get("score") is not None:
        by_agent_qid[e["agent"]].append(entries[i]["score"])

print("\nAverage scores by agent (newly scored entries):")
for agent, scores in sorted(by_agent_qid.items()):
    avg = sum(scores) / len(scores)
    print(f"  {agent}: {avg:.1f}  (n={len(scores)})")
