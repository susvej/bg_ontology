import json as _json
from IPython.display import display, HTML, Markdown

# Standard prefixes — injected into any query that omits them
_PREFIXES = [
    ("bgg:",   "PREFIX bgg:   <https://raw.githubusercontent.com/susvej/bg_ontology/>"),
    ("trenj:", "PREFIX trenj: <https://vejdemo.se/boardgames/threnjen#>"),
    ("svj:",   "PREFIX svj:   <https://vejdemo.se/boardgames#>"),
    ("fake:",  "PREFIX fake:  <https://vejdemo.se/boardgames/fake#>"),
    ("rdf:",   "PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>"),
    ("rdfs:",  "PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>"),
    ("skos:",  "PREFIX skos:  <http://www.w3.org/2004/02/skos/core#>"),
    ("xsd:",   "PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>"),
]

def _inject_prefixes(query):
    needed = [decl for token, decl in _PREFIXES
              if token in query and "PREFIX " + token not in query]
    return ("\n".join(needed) + "\n" + query) if needed else query


# ── Ollama call ───────────────────────────────────────────────────────────────
def _call_ollama(system, user, max_tokens=1024):
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens, "num_ctx": 32768, "temperature": 0},
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


# ── SPARQL generation ─────────────────────────────────────────────────────────
def generate_sparql(question, error_context=None):
    user_content = question
    if error_context:
        user_content = "\n\n".join([
            question,
            "Your previous query failed with this error:\n" + error_context,
            "Please fix the SPARQL query.",
        ])
    query = _call_ollama(SYSTEM_SPARQL, user_content, max_tokens=1024)
    fence = "```"
    if query.startswith(fence):
        query = "\n".join(l for l in query.splitlines() if not l.startswith(fence)).strip()
    lines = query.splitlines()
    for i, line in enumerate(lines):
        if line.strip().upper().startswith(("PREFIX", "SELECT", "ASK", "CONSTRUCT", "DESCRIBE")):
            query = "\n".join(lines[i:])
            break
    query = query.replace("rdf-design#", "rdf-schema#")
    query = _inject_prefixes(query)
    return query


# ── SPARQL execution ──────────────────────────────────────────────────────────
def execute_sparql(query):
    resp = requests.post(
        SPARQL_ENDPOINT,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=SPARQL_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# ── Result table display ──────────────────────────────────────────────────────
def _show_table(bindings, vars_):
    if not bindings:
        display(HTML("<i>No results.</i>"))
        return
    import pandas as pd
    rows = [{v: b.get(v, {}).get("value", "") for v in vars_} for b in bindings]
    df = pd.DataFrame(rows, columns=vars_)
    df.index = range(1, len(df) + 1)
    display(HTML(
        "<p><b>" + str(len(bindings)) + " result(s)</b></p>" +
        df.to_html(classes="table table-sm", border=1, max_rows=None)
    ))


# ── Result interpretation ─────────────────────────────────────────────────────
def interpret_results(question, query, results):
    bindings = results.get("results", {}).get("bindings", [])
    vars_    = results.get("head", {}).get("vars", [])
    payload  = _json.dumps({
        "question":          question,
        "sparql_query":      query,
        "result_variables":  vars_,
        "result_count":      len(bindings),
        "results_truncated": len(bindings) > 100,
        "results":           bindings[:100],
    }, ensure_ascii=False)
    return _call_ollama(SYSTEM_RESULT, payload, max_tokens=1024)


# ── Logging ───────────────────────────────────────────────────────────────────
def _log(question_id, question, answer, query=""):
    entry = {
        "timestamp":       _dt.now().isoformat(timespec="seconds"),
        "agent":           AGENT_NAME,
        "question_id":     question_id,
        "question":        question,
        "generated_query": query,
        "answer":          answer,
        "score":           None,
        "comment":         "",
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(_json.dumps(entry, ensure_ascii=False) + "\n")


# ── Full pipeline ─────────────────────────────────────────────────────────────
def ask(question, question_id="Q?", max_retries=2):
    display(Markdown("---\n#### [" + question_id + "]\n*" + question + "*"))

    query = generate_sparql(question)
    fence = "```"
    display(Markdown("**Generated SPARQL:**\n" + fence + "sparql\n" + query + "\n" + fence))

    for attempt in range(max_retries + 1):
        try:
            results = execute_sparql(query)
            break
        except requests.HTTPError as e:
            error_msg = e.response.text[:500]
            display(Markdown("**SPARQL error (attempt " + str(attempt + 1) + "):** `" + error_msg[:200] + "`"))
            if attempt < max_retries:
                query = generate_sparql(question, error_msg)
                display(Markdown("**Revised query:**\n" + fence + "sparql\n" + query + "\n" + fence))
            else:
                answer = "Query failed after " + str(max_retries + 1) + " attempts: " + error_msg[:200]
                _log(question_id, question, answer, query)
                display(Markdown("**Answer:** " + answer))
                return answer
        except requests.Timeout:
            answer = "Query timed out after " + str(SPARQL_TIMEOUT) + "s."
            _log(question_id, question, answer, query)
            display(Markdown("**Answer:** " + answer))
            return answer

    bindings = results.get("results", {}).get("bindings", [])
    vars_    = results.get("head", {}).get("vars", [])
    _show_table(bindings, vars_)

    answer = interpret_results(question, query, results)
    _log(question_id, question, answer, query)
    display(Markdown("**Answer:** " + answer))
    return answer

print("Pipeline ready.")
