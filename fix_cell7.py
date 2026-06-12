"""Rewrite Cell 7 (pipeline functions) in bgg_sparql_qa.ipynb.

Uses chr(10) instead of \\n string literals everywhere to avoid the
notebook-JSON storage issue where \\n gets stored as a real newline.
"""
import json, ast

NB_FILE = "bgg_sparql_qa.ipynb"

# Each entry is one source line WITHOUT a trailing newline.
# chr(10) is used wherever the cell source needs a newline character at runtime
# (i.e. inside string literals).  This avoids \\n escape sequences entirely.
LINES = [
    "MAX_RETRIES = 2",
    "",
    "",
    "def generate_sparql(question: str, error_context: str = None) -> str:",
    '    """Call 1: natural language -> SPARQL query. Pass error_context to repair a bad query."""',
    "    user_content = question",
    "    if error_context:",
    "        nl = chr(10)",
    "        user_content = (nl * 2).join([",
    "            question,",
    '            f"Your previous query failed with this GraphDB error: {error_context}",',
    '            "Please fix the SPARQL query.",',
    "        ])",
    "    response = client.messages.create(",
    "        model=MODEL,",
    "        max_tokens=1024,",
    "        system=[",
    "            {",
    '                "type": "text",',
    '                "text": SYSTEM_SPARQL,',
    '                "cache_control": {"type": "ephemeral"},',
    "            }",
    "        ],",
    '        messages=[{"role": "user", "content": user_content}],',
    "    )",
    "    query = response.content[0].text.strip()",
    "    # Strip markdown fences if present",
    '    if query.startswith("```"):',
    "        query = chr(10).join(",
    '            l for l in query.splitlines() if not l.startswith("```")',
    "        ).strip()",
    "    return query",
    "",
    "",
    "def execute_sparql(query: str) -> dict:",
    '    """Execute a SPARQL SELECT against GraphDB; return parsed JSON results."""',
    "    resp = requests.post(",
    "        SPARQL_ENDPOINT,",
    '        data={"query": query},',
    '        headers={"Accept": "application/sparql-results+json"},',
    "        timeout=30,",
    "    )",
    "    resp.raise_for_status()",
    "    return resp.json()",
    "",
    "",
    "def format_results_table(results: dict, max_rows: int = 20) -> str:",
    '    """Format SPARQL JSON results as a markdown table (values truncated at 80 chars)."""',
    '    bindings = results.get("results", {}).get("bindings", [])',
    '    vars_    = results.get("head",    {}).get("vars",     [])',
    "    if not bindings or not vars_:",
    '        return "(no results)"',
    "",
    "    def cell(b, v):",
    '        val = b.get(v, {}).get("value", "")',
    '        return val[:80] + "..." if len(val) > 80 else val',
    "",
    "    rows  = [[cell(b, v) for v in vars_] for b in bindings]",
    "    shown = rows[:max_rows]",
    "    col_w = [max(len(v), max(len(r[i]) for r in shown)) for i, v in enumerate(vars_)]",
    "",
    "    def md_row(cells):",
    '        return "| " + " | ".join(c.ljust(col_w[i]) for i, c in enumerate(cells)) + " |"',
    "",
    '    header  = md_row(vars_)',
    '    divider = "| " + " | ".join("-" * col_w[i] for i in range(len(vars_))) + " |"',
    "    lines   = [header, divider] + [md_row(r) for r in shown]",
    "    if len(bindings) > max_rows:",
    '        lines.append(f"*(showing {max_rows} of {len(bindings)} rows)*")',
    "    return chr(10).join(lines)",
    "",
    "",
    "def interpret_results(question: str, query: str, results: dict) -> str:",
    '    """Call 2: SPARQL results -> natural-language answer."""',
    '    bindings = results.get("results", {}).get("bindings", [])',
    '    vars_    = results.get("head",    {}).get("vars",     [])',
    "    truncated = len(bindings) > 50",
    "",
    "    payload = {",
    '        "question": question,',
    '        "sparql_query": query,',
    '        "result_variables": vars_,',
    '        "result_count": len(bindings),',
    '        "results_truncated": truncated,',
    '        "results": bindings[:50],',
    "    }",
    "",
    "    response = client.messages.create(",
    "        model=MODEL,",
    "        max_tokens=512,",
    "        system=SYSTEM_RESULT,",
    "        messages=[",
    "            {",
    '                "role": "user",',
    '                "content": json.dumps(payload, ensure_ascii=False),',
    "            }",
    "        ],",
    "    )",
    "    return response.content[0].text.strip()",
    "",
    "",
    "def ask(question: str, show_query: bool = True) -> str:",
    '    """Full pipeline: question -> SPARQL -> execute (with retry) -> natural-language answer."""',
    '    print(f"Question: {question}")',
    "    print()",
    "",
    "    query = generate_sparql(question)",
    "    for attempt in range(MAX_RETRIES + 1):",
    "        if show_query:",
    '            label = f"Generated SPARQL (attempt {attempt + 1}):" if attempt > 0 else "Generated SPARQL:"',
    "            print(label)",
    '            print("-" * 60)',
    "            print(query)",
    '            print("-" * 60)',
    "            print()",
    "",
    "        try:",
    "            results = execute_sparql(query)",
    "            break",
    "        except requests.HTTPError as e:",
    "            error_msg = e.response.text[:500]",
    "            if attempt < MAX_RETRIES:",
    '                print(f"SPARQL error (attempt {attempt + 1}), retrying...")',
    "                print(error_msg[:120])",
    "                print()",
    "                query = generate_sparql(question, error_msg)",
    "            else:",
    '                print(f"SPARQL execution failed after {MAX_RETRIES + 1} attempts.")',
    "                print(error_msg)",
    '                return ""',
    "",
    '    n = len(results.get("results", {}).get("bindings", []))',
    '    print(f"Results: {n} row(s)" + (" (truncated to 50 for interpretation)" if n > 50 else ""))',
    "    print()",
    "    print(format_results_table(results))",
    "    print()",
    "",
    "    answer = interpret_results(question, query, results)",
    '    print("Answer:")',
    "    print(textwrap.fill(answer, width=80))",
    "    print()",
    "    return answer",
]

# Verify the source parses as valid Python before writing
source = "\n".join(LINES)
try:
    ast.parse(source)
    print("AST parse: OK")
except SyntaxError as e:
    print(f"SyntaxError in generated source: {e}")
    raise

# Build the source list for the notebook (each line ends with \n except the last)
source_list = [l + "\n" for l in LINES[:-1]] + ([LINES[-1]] if LINES[-1] else [])

with open(NB_FILE, encoding="utf-8-sig") as f:
    nb = json.load(f)

# Find the cell
target_idx = None
for i, cell in enumerate(nb["cells"]):
    if cell.get("id") == "c4260353":
        target_idx = i
        break

if target_idx is None:
    raise RuntimeError("Cell c4260353 not found")

nb["cells"][target_idx]["source"] = source_list
print(f"Replacing cell {target_idx} ({len(source_list)} lines)")

with open(NB_FILE, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)
print("Saved.")
