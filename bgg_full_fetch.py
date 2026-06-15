#!/usr/bin/env python3
"""
bgg_full_fetch.py — Full BGG data pull (base games + expansions).

Downloads all ranked BGG games via the BGG XML API2, writing RDF/Turtle output.
Saves progress to bgg_fetch_checkpoint.json so the run can be interrupted and resumed.

Usage:
    python bgg_full_fetch.py            # start fresh or resume
    python bgg_full_fetch.py --reset    # delete checkpoint and start over
    python bgg_full_fetch.py --finalize # write entity labels and close output file

Output:
    bgg_full.ttl                  — final RDF/Turtle file (when complete)
    bgg_full_progress.ttl         — partial file written during fetch
    bgg_fetch_checkpoint.json     — progress tracker
"""

import argparse
import json
import os
import re
import time
import xml.etree.ElementTree as ET

import requests

BGG_LOGIN_URL = 'https://boardgamegeek.com/login/api/v1'

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/xml,text/xml,*/*',
})


def _load_env(path: str = '.env') -> dict:
    """Parse key=value pairs from a .env file."""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def login_bgg() -> bool:
    """Log in to BGG using credentials from .env; returns True on success."""
    env = _load_env()
    username = env.get('BGG_USERNAME') or os.environ.get('BGG_USERNAME', '')
    password = env.get('BGG_PASSWORD') or os.environ.get('BGG_PASSWORD', '')
    if not username or not password:
        print('WARNING: BGG_USERNAME / BGG_PASSWORD not set — skipping login')
        return False
    print(f'Logging in to BGG as {username} ...')
    r = SESSION.post(
        BGG_LOGIN_URL,
        json={'credentials': {'username': username, 'password': password}},
        timeout=15,
    )
    if r.status_code in (200, 204):
        cookies = list(SESSION.cookies.keys())
        print(f'  Login OK (HTTP {r.status_code}) — cookies: {cookies}')
        return True
    print(f'  Login failed: HTTP {r.status_code} — {r.text[:200]}')
    return False

# ── Configuration ──────────────────────────────────────────────────────────────
CHECKPOINT_FILE = 'bgg_fetch_checkpoint.json'
PROGRESS_FILE   = 'bgg_full_progress.ttl'
OUTPUT_FILE     = 'bgg_full.ttl'

BATCH_SIZE  = 20     # IDs per API request (BGG supports ~20 reliably)
DELAY_SEC   = 3.0    # polite delay between requests
RETRY_WAIT  = 15.0   # wait time on 202 / 5xx response

BGG_API_URL      = 'https://boardgamegeek.com/xmlapi2/thing'
ID_SOURCE_TTL    = 'bgg_kaggle2025.ttl'   # known game IDs extracted from this file
ID_SCAN_UP_TO    = 500_000                # scan above max known ID to catch new games

TTL_HEADER = """\
@prefix bgg:  <https://raw.githubusercontent.com/susvej/bg_ontology/> .
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .

"""


# ── ID discovery ───────────────────────────────────────────────────────────────
def collect_game_ids() -> list[int]:
    """
    Build a sorted list of BGG game IDs to fetch.

    1. Extract IDs already known from the local TTL file (bgg_kaggle2025.ttl),
       which contains 126k games up to ID ~438,593.
    2. Append a scan range above the highest known ID up to ID_SCAN_UP_TO,
       to catch any games BGG has added since the Kaggle dataset was scraped.
    """
    known_ids: set[int] = set()
    ttl_path = ID_SOURCE_TTL

    if os.path.exists(ttl_path):
        print(f'Extracting IDs from {ttl_path} ...')
        id_re = re.compile(r'bgg:(\d+)\s')
        with open(ttl_path, encoding='utf-8', errors='replace') as f:
            for line in f:
                m = id_re.search(line)
                if m:
                    known_ids.add(int(m.group(1)))
        print(f'  {len(known_ids):,} IDs found in {ttl_path}')
    else:
        print(f'WARNING: {ttl_path} not found — skipping known-ID extraction')

    max_known = max(known_ids) if known_ids else 0
    scan_start = max_known + 1
    scan_range = list(range(scan_start, ID_SCAN_UP_TO + 1))
    print(f'  Scan range: {scan_start:,} – {ID_SCAN_UP_TO:,} ({len(scan_range):,} extra IDs)')

    all_ids = sorted(known_ids) + scan_range
    print(f'  Total IDs to fetch: {len(all_ids):,}')
    return all_ids


# ── Checkpoint ─────────────────────────────────────────────────────────────────
def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {'game_ids': [], 'done_ids': [], 'seen_entities': {}}


def save_checkpoint(cp: dict) -> None:
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(cp, f)


# ── BGG API fetch ──────────────────────────────────────────────────────────────
def fetch_batch(ids: list[int]) -> ET.Element | None:
    """Fetch up to BATCH_SIZE game IDs from BGG API. Returns parsed XML root."""
    params = {
        'id':   ','.join(str(i) for i in ids),
        'type': 'boardgame,boardgameexpansion',
        'stats': '1',
    }
    for attempt in range(4):
        try:
            r = SESSION.get(BGG_API_URL, params=params, timeout=30)
        except requests.RequestException as e:
            print(f'\n  Network error: {e}')
            time.sleep(RETRY_WAIT)
            continue
        if r.status_code == 200:
            try:
                return ET.fromstring(r.content)
            except ET.ParseError as e:
                print(f'\n  XML parse error: {e}')
                return None
        elif r.status_code == 202:
            print(f'\n  API queued (202) — waiting {RETRY_WAIT}s...')
            time.sleep(RETRY_WAIT)
        else:
            print(f'\n  HTTP {r.status_code} — retrying...')
            time.sleep(RETRY_WAIT)
    return None


# ── XML parsing ────────────────────────────────────────────────────────────────
def _val(el: ET.Element | None, default: str = '') -> str:
    return el.get('value', default) if el is not None else default


def _text(el: ET.Element | None) -> str:
    return (el.text or '').strip() if el is not None else ''


def parse_item(item: ET.Element) -> dict | None:
    game_id   = item.get('id', '')
    game_type = item.get('type', 'boardgame')
    if not game_id:
        return None

    # Primary name
    name = ''
    for n in item.findall('name'):
        if n.get('type') == 'primary':
            name = n.get('value', '')
            break
    if not name:
        return None

    # Scalar fields
    year    = _val(item.find('yearpublished'))
    min_p   = _val(item.find('minplayers'))
    max_p   = _val(item.find('maxplayers'))
    min_age = _val(item.find('minage'))
    min_t   = _val(item.find('minplaytime'))
    max_t   = _val(item.find('maxplaytime'))
    desc    = _text(item.find('description'))[:1000]   # cap description length
    thumb   = _text(item.find('thumbnail'))

    # Ratings
    rating = bayesian = num_ratings = complexity = ''
    stats = item.find('statistics/ratings')
    if stats is not None:
        rating      = _val(stats.find('average'))
        bayesian    = _val(stats.find('bayesaverage'))
        num_ratings = _val(stats.find('usersrated'))
        complexity  = _val(stats.find('averageweight'))

    # Best player count (from poll)
    best_p = ''
    for poll in item.findall('poll'):
        if poll.get('name') == 'suggested_numplayers':
            best_votes = 0
            for res in poll.findall('results'):
                np = res.get('numplayers', '')
                best_el = res.find('result[@value="Best"]')
                if best_el is not None:
                    v = int(best_el.get('numvotes', 0) or 0)
                    if v > best_votes:
                        best_votes = v
                        best_p = np
            break

    # Linked entities (id, label)
    def links(ltype):
        return [(lk.get('id', ''), lk.get('value', ''))
                for lk in item.findall('link') if lk.get('type') == ltype]

    return {
        'id':         game_id,
        'type':       game_type,
        'name':       name,
        'year':       year,
        'min_p':      min_p,
        'max_p':      max_p,
        'best_p':     best_p,
        'min_age':    min_age,
        'min_t':      min_t,
        'max_t':      max_t,
        'desc':       desc,
        'thumb':      thumb,
        'rating':     rating,
        'bayesian':   bayesian,
        'num_ratings': num_ratings,
        'complexity': complexity,
        'designers':  links('boardgamedesigner'),
        'publishers': links('boardgamepublisher'),
        'categories': links('boardgamecategory'),
        'mechanics':  links('boardgamemechanic'),
    }


# ── TTL serialisation ──────────────────────────────────────────────────────────
def _ttl_str(s: str) -> str:
    """Escape a Python string for Turtle."""
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '')
    return f'"{s}"'


def _safe_int(v: str) -> bool:
    try:
        int(v)
        return bool(v and v != '0')
    except ValueError:
        return False


def _safe_float(v: str) -> bool:
    try:
        f = float(v)
        return f > 0
    except ValueError:
        return False


def game_to_ttl(g: dict, seen_entities: dict) -> str:
    """Convert a parsed game dict to Turtle lines. Also registers new entities."""
    gid = g['id']
    props = []

    def p(pred, obj):
        props.append(f'    {pred} {obj}')

    p('rdf:type', 'bgg:Game')
    if g['type'] == 'boardgameexpansion':
        p('bgg:isExpansion', '"true"^^xsd:boolean')
    p('bgg:hasID',   f'"{gid}"^^xsd:int')
    p('bgg:hasName', f'{_ttl_str(g["name"])}^^xsd:string')

    if _safe_int(g['year']):
        p('bgg:hasYearPublished', f'"{g["year"]}"^^xsd:int')
    if _safe_int(g['min_p']):
        p('bgg:hasMinPlayers', f'"{g["min_p"]}"^^xsd:int')
    if _safe_int(g['max_p']):
        p('bgg:hasMaxPlayers', f'"{g["max_p"]}"^^xsd:int')
    if _safe_int(g['best_p']):
        p('bgg:hasBestNumPlayers', f'"{g["best_p"]}"^^xsd:int')
    if _safe_int(g['min_age']):
        p('bgg:hasMinRecAge', f'"{g["min_age"]}"^^xsd:int')
    if _safe_int(g['min_t']):
        p('bgg:hasMinGameTime', f'"{g["min_t"]}"^^xsd:int')
    if _safe_int(g['max_t']):
        p('bgg:hasMaxGameTime', f'"{g["max_t"]}"^^xsd:int')
    if _safe_float(g['rating']):
        p('bgg:hasRating',     f'"{float(g["rating"]):.4f}"^^xsd:double')
    if _safe_float(g['bayesian']):
        p('bgg:hasGeekRating', f'"{float(g["bayesian"]):.4f}"^^xsd:double')
    if g['num_ratings'] and g['num_ratings'] != '0':
        p('bgg:hasNumRatings', f'"{g["num_ratings"]}"^^xsd:int')
    if _safe_float(g['complexity']):
        p('bgg:hasComplexity', f'"{float(g["complexity"]):.4f}"^^xsd:double')
    if g['desc']:
        p('bgg:hasDescription', f'{_ttl_str(g["desc"])}^^xsd:string')
    if g['thumb']:
        p('bgg:hasThumbnail', f'<{g["thumb"]}>')
    p('bgg:hasURL', f'<https://boardgamegeek.com/boardgame/{gid}>')
    p('bgg:isFullyEnriched', '"true"^^xsd:boolean')

    for eid, elabel in g['designers']:
        slug = f'creator_{eid}'
        p('bgg:hasCreator', f'bgg:{slug}')
        seen_entities.setdefault(slug, elabel)
    for eid, elabel in g['publishers']:
        slug = f'pub_{eid}'
        p('bgg:hasPublisher', f'bgg:{slug}')
        seen_entities.setdefault(slug, elabel)
    for eid, elabel in g['categories']:
        slug = f'cat_{eid}'
        p('bgg:hasCategory', f'bgg:{slug}')
        seen_entities.setdefault(slug, elabel)
    for eid, elabel in g['mechanics']:
        slug = f'mech_{eid}'
        p('bgg:hasMechanic', f'bgg:{slug}')
        seen_entities.setdefault(slug, elabel)

    prop_lines = ' ;\n'.join(props) + ' .'
    return f'bgg:{gid}\n{prop_lines}\n'


def write_entity_declarations(seen_entities: dict, out_file) -> None:
    """Append rdfs:label declarations for all collected categories/mechanics/creators."""
    out_file.write('\n# ── Entity labels (categories, mechanics, creators, publishers) ──\n')
    for slug, label in sorted(seen_entities.items()):
        safe = label.replace('\\', '\\\\').replace('"', '\\"')
        out_file.write(f'bgg:{slug} rdfs:label "{safe}"^^xsd:string .\n')


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='Download all BGG games to Turtle RDF.')
    parser.add_argument('--reset',    action='store_true', help='Clear checkpoint and start over')
    parser.add_argument('--finalize', action='store_true', help='Write entity labels and close output')
    args = parser.parse_args()

    login_bgg()

    if args.reset:
        for f in [CHECKPOINT_FILE, PROGRESS_FILE]:
            if os.path.exists(f):
                os.remove(f)
                print(f'Deleted {f}')

    cp = load_checkpoint()

    # Collect game IDs if not cached in checkpoint
    if not cp['game_ids']:
        cp['game_ids'] = collect_game_ids()
        save_checkpoint(cp)

    all_ids      = cp['game_ids']
    done_ids     = set(cp.get('done_ids', []))
    seen_entities = cp.get('seen_entities', {})
    todo         = [i for i in all_ids if i not in done_ids]

    print(f'Total IDs: {len(all_ids):,} | Done: {len(done_ids):,} | Remaining: {len(todo):,}')

    if args.finalize or not todo:
        # Write entity declarations and finalize
        print(f'Writing entity declarations ({len(seen_entities):,} entities)...')
        with open(PROGRESS_FILE, 'a', encoding='utf-8') as out:
            write_entity_declarations(seen_entities, out)
        if os.path.exists(OUTPUT_FILE):
            os.rename(OUTPUT_FILE, OUTPUT_FILE + '.bak')
        os.rename(PROGRESS_FILE, OUTPUT_FILE)
        print(f'Output written to {OUTPUT_FILE}')
        print(f'Games fetched: {len(done_ids):,}')
        return

    # Write prefix header only if starting a fresh progress file
    fresh = not os.path.exists(PROGRESS_FILE) or os.path.getsize(PROGRESS_FILE) == 0
    with open(PROGRESS_FILE, 'a', encoding='utf-8') as out:
        if fresh:
            out.write(TTL_HEADER)

        n_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
        for batch_num, offset in enumerate(range(0, len(todo), BATCH_SIZE), start=1):
            batch = todo[offset:offset + BATCH_SIZE]
            pct   = (len(done_ids) + offset) / len(all_ids) * 100
            print(f'[{pct:5.1f}%] Batch {batch_num}/{n_batches} (IDs {batch[0]}–{batch[-1]}) ... ',
                  end='', flush=True)

            root = fetch_batch(batch)
            if root is not None:
                written = 0
                for item in root.findall('item'):
                    parsed = parse_item(item)
                    if parsed:
                        out.write(game_to_ttl(parsed, seen_entities) + '\n')
                        written += 1
                done_ids.update(batch)
                cp['done_ids']      = list(done_ids)
                cp['seen_entities'] = seen_entities
                save_checkpoint(cp)
                print(f'{written} games')
            else:
                print('FAILED (skipped)')

            time.sleep(DELAY_SEC)

    print(f'\nFetch complete. Run with --finalize to write entity labels and produce {OUTPUT_FILE}.')


if __name__ == '__main__':
    main()
