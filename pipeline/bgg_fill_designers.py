"""
bgg_fill_designers.py

Finds all enriched games in bgg_main.ttl that are missing bgg:hasCreator,
queries the BGG geekdo API for their designers, and writes a patch TTL file.

Usage:
    python bgg_fill_designers.py

Output:
    bgg_designers_patch.ttl  — paste-into or merge with bgg_main.ttl

Checkpoint:
    bgg_designers_checkpoint.json  — resume after interruption
"""

import json
import os
import re
import time
import unicodedata

import requests

# ── Configuration ────────────────────────────────────────────────────────────
TTL_FILE          = '../data/bgg_main.ttl'
PATCH_FILE        = 'bgg_designers_patch.ttl'
CHECKPOINT_FILE   = 'bgg_designers_checkpoint.json'
ENV_FILE          = '.env'
BGG_LOGIN_URL     = 'https://boardgamegeek.com/login/api/v1'
GEEKDO_ITEM_URL   = 'https://api.geekdo.com/api/geekitems'
REQUEST_DELAY     = 1.0   # seconds between API calls
BATCH_STATUS_EVERY = 50   # print progress every N games

SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'BGG-Ontology-Designer-Fill/1.0'})

# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_env() -> dict:
    env = {}
    try:
        with open(ENV_FILE, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def login_bgg(username: str, password: str) -> bool:
    print(f'Logging in to BGG as {username} ...')
    try:
        r = SESSION.post(
            BGG_LOGIN_URL,
            json={'credentials': {'username': username, 'password': password}},
            timeout=30,
        )
        if r.status_code in (200, 204):
            print(f'  Logged in (HTTP {r.status_code})')
            return True
        print(f'  Login failed: HTTP {r.status_code}')
        return False
    except Exception as e:
        print(f'  Login error: {e}')
        return False


def name_to_iri(name: str) -> str:
    """Convert a designer name to the bgg: IRI local part.

    'Elizabeth Hargrave' -> 'ElizabethHargrave'
    'Adam E. Daulton'    -> 'AdamEDaulton'
    'Adam Kałuża'        -> 'AdamKauza'
    """
    # Normalise accented characters to ASCII equivalents
    normalised = unicodedata.normalize('NFD', name)
    ascii_name = ''.join(c for c in normalised if unicodedata.category(c) != 'Mn')
    # Capitalise each space-separated word, keep only alphanumeric
    parts = []
    for word in ascii_name.split():
        word = word.capitalize()
        word = re.sub(r'[^A-Za-z0-9]', '', word)
        if word:
            parts.append(word)
    return ''.join(parts)


def load_existing_ttl() -> tuple[set[int], set[str], dict[str, str]]:
    """Parse bgg_main.ttl and return:
    - enriched_missing: set of game IDs (int) that are enriched but have no hasCreator
    - existing_creator_iris: set of IRI local parts like 'ElizabethHargrave'
    - existing_creator_labels: map IRI local part -> rdfs:label string
    """
    print(f'Parsing {TTL_FILE} ...')
    with open(TTL_FILE, encoding='utf-8') as f:
        content = f.read()

    # Collect existing Creator IRIs and their labels
    creator_label_pat = re.compile(
        r'(bgg:(\w+))\s*\n\s*rdf:type bgg:Creator\s*;\s*\n\s*rdfs:label\s*"([^"]+)"'
    )
    existing_creator_iris: set[str] = set()
    existing_creator_labels: dict[str, str] = {}
    for m in creator_label_pat.finditer(content):
        local = m.group(2)
        label = m.group(3)
        existing_creator_iris.add(local)
        existing_creator_labels[local] = label

    # Collect enriched games missing hasCreator
    # Split on game blocks (lines starting with bgg:<digits>)
    blocks = re.split(r'\n(?=bgg:\d+\n)', content)
    enriched_missing: set[int] = set()
    for block in blocks:
        if 'isFullyEnriched' in block and 'hasCreator' not in block:
            m = re.match(r'bgg:(\d+)', block)
            if m:
                enriched_missing.add(int(m.group(1)))

    print(f'  Existing Creator entities: {len(existing_creator_iris)}')
    print(f'  Enriched games missing hasCreator: {len(enriched_missing)}')
    return enriched_missing, existing_creator_iris, existing_creator_labels


def load_checkpoint() -> tuple[set[int], dict]:
    """Return (already_processed_ids, accumulated_results)."""
    if not os.path.exists(CHECKPOINT_FILE):
        return set(), {}
    with open(CHECKPOINT_FILE, encoding='utf-8') as f:
        data = json.load(f)
    processed = set(data.get('processed', []))
    results = data.get('results', {})
    print(f'Resuming from checkpoint: {len(processed)} games already processed')
    return processed, results


def save_checkpoint(processed: set[int], results: dict) -> None:
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'processed': sorted(processed), 'results': results}, f)


def fetch_designers(game_id: int) -> list[dict]:
    """Query geekdo API and return list of {id, name} dicts for designers."""
    try:
        r = SESSION.get(
            GEEKDO_ITEM_URL,
            params={'objectid': game_id, 'objecttype': 'thing'},
            timeout=20,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        item = data.get('item') or data.get('data') or {}
        links = item.get('links', {})
        designers = links.get('boardgamedesigner', [])
        return [{'id': d.get('id'), 'name': d.get('name', '').strip()} for d in designers if d.get('name', '').strip()]
    except Exception:
        return []


def write_patch(results: dict, existing_creator_iris: set[str], existing_creator_labels: dict[str, str]) -> None:
    """Write bgg_designers_patch.ttl with new Creator entities and hasCreator triples."""

    # Collect all new creators needed
    new_creators: dict[str, str] = {}   # iri_local -> label
    game_creators: dict[int, list[str]] = {}  # game_id -> [iri_locals]

    for game_id_str, designers in results.items():
        game_id = int(game_id_str)
        iris = []
        for d in designers:
            name = d['name']
            if not name:
                continue
            iri = name_to_iri(name)
            if not iri:
                continue
            if iri not in existing_creator_iris and iri not in new_creators:
                new_creators[iri] = name
            iris.append(iri)
        if iris:
            game_creators[game_id] = iris

    print(f'  New Creator entities to add: {len(new_creators)}')
    print(f'  Games that will get hasCreator: {len(game_creators)}')

    with open(PATCH_FILE, 'w', encoding='utf-8') as f:
        f.write('# BGG designer patch — generated by bgg_fill_designers.py\n')
        f.write('# Merge this into bgg_main.ttl\n\n')
        f.write('@prefix bgg: <https://raw.githubusercontent.com/susvej/bg_ontology/> .\n')
        f.write('@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n')
        f.write('@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n')
        f.write('@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n')

        f.write('# ── NEW CREATOR ENTITIES ────────────────────────────────────────────────────\n\n')
        for iri in sorted(new_creators):
            label = new_creators[iri]
            f.write(f'bgg:{iri}\n')
            f.write(f'    rdf:type bgg:Creator ;\n')
            f.write(f'    rdfs:label "{label}"@en .\n\n')

        f.write('# ── GAME hasCreator ADDITIONS ───────────────────────────────────────────────\n')
        f.write('# Add these triples to the corresponding game blocks in bgg_main.ttl\n\n')
        for game_id in sorted(game_creators):
            iris = game_creators[game_id]
            creators_str = ' , '.join(f'bgg:{i}' for i in iris)
            f.write(f'# bgg:{game_id}\n')
            f.write(f'bgg:{game_id} bgg:hasCreator {creators_str} .\n\n')

    print(f'Patch written to {PATCH_FILE}')


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    env = _load_env()
    username = env.get('BGG_USERNAME', '')
    password = env.get('BGG_PASSWORD', '')

    if username and password:
        login_bgg(username, password)
    else:
        print('No BGG credentials found in .env — proceeding without login (may get fewer results)')

    enriched_missing, existing_creator_iris, existing_creator_labels = load_existing_ttl()
    processed, results = load_checkpoint()

    to_process = sorted(enriched_missing - processed)
    total = len(to_process)
    print(f'Games left to query: {total}')

    for i, game_id in enumerate(to_process):
        designers = fetch_designers(game_id)
        if designers:
            results[str(game_id)] = designers

        processed.add(game_id)

        if (i + 1) % BATCH_STATUS_EVERY == 0 or (i + 1) == total:
            found = sum(1 for v in results.values() if v)
            print(f'  [{i+1}/{total}] game {game_id} — designers found so far: {found}')
            save_checkpoint(processed, results)

        time.sleep(REQUEST_DELAY)

    save_checkpoint(processed, results)
    write_patch(results, existing_creator_iris, existing_creator_labels)
    print('Done.')


if __name__ == '__main__':
    main()
