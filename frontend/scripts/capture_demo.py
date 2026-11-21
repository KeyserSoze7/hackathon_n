"""Capture the demo snapshots from a RUNNING backend into frontend/public/demo/.

    python frontend/scripts/capture_demo.py                       # backend on http://localhost:8000
    python frontend/scripts/capture_demo.py http://10.10.38.50:8000

Writes manifest.json plus one file per snapshot (read by src/data/demo.ts). The data is synthetic; the Claude answers and
notices are captured once and replayed. Re-run any time the backend data changes, then rebuild with `npm run build:demo`.
"""
import json, math, pathlib, sys, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')
OUT = pathlib.Path(__file__).resolve().parents[1] / 'public' / 'demo'
OUT.mkdir(parents=True, exist_ok=True)
for old in OUT.glob('*.json'): old.unlink()
q = lambda s: urllib.parse.quote(str(s), safe='')

LOOKUPS = ['Kurla Andheri Road', 'Andheri Subway', 'Hindmata', 'Dadar West', 'Link Road', 'Sion Hospital Road']
QUERIES = [
    'Andheri subway ke bahar khadda wapas aa gaya, paisa kahan gaya?',
    'What happened to the repair money on Kurla Andheri Road?',
    'Hindmata mein paani bhar gaya, kaun zimmedar hai?',
    'Is the road near Sion hospital still under warranty?',
]
STEP = 100_000

def call(method, path, body=None, tries=3, timeout=180):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        try:
            req = urllib.request.Request(BASE + path, data=data, method=method, headers={'content-type': 'application/json'})
            with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (404, 422): return None
            err = e
        except Exception as e: err = e
        time.sleep(1.5 * (i + 1))
    print('  failed:', method, path, err); return None

files, n = {}, 0
def save(key, data):
    global n; n += 1; name = f'f{n:04d}.json'
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8'); files[key] = name

def pool(fn, items, workers=6):
    with ThreadPoolExecutor(workers) as ex: return list(ex.map(fn, items))

print('backend:', BASE)
health = call('GET', '/api/health', tries=1, timeout=10)
if not health: sys.exit('Backend not reachable. Start it (uvicorn backend.main:app --port 8000) or pass its address.')
print('health:', health)

for p in ['/api/city', '/api/wards', '/api/localities', '/api/v3/contractors', '/api/v3/wards']:
    d = call('GET', p)
    if d is None: sys.exit(f'Essential endpoint failed: {p}')
    save(p, d)
wards = [w['ward_code'] for w in json.loads((OUT / files['/api/wards']).read_text(encoding='utf-8'))]
allocw = {w['ward_code']: w for w in json.loads((OUT / files['/api/v3/wards']).read_text(encoding='utf-8'))}
localities = [l['locality'] for l in json.loads((OUT / files['/api/localities']).read_text(encoding='utf-8'))]

road_ids = {'RD0220', 'RD0153'}

# Flagged queues, money trails, next-rupee lists
def ward_pack(w):
    return w, call('GET', f'/api/flagged-queue?limit=50&ward={q(w)}'), call('GET', f'/api/wards/{q(w)}/money-trail'), call('GET', f'/api/v3/next-rupee/{q(w)}')
allq = call('GET', '/api/flagged-queue?limit=50') or []
save('queue:ALL', allq); road_ids.update(i['road_id'] for i in allq[:12])
for w, qu, tr, nx in pool(ward_pack, wards):
    if qu is not None: save(f'queue:{w}', qu); road_ids.update(i['road_id'] for i in qu[:12])
    if tr is not None: save(f'trail:{w}', tr)
    if nx is not None: save(f'next:{w}', nx); road_ids.update(i['road_id'] for i in nx)
print(f'queues/trails/next-rupee for {len(wards)} wards')

# Budget slider: a grid of exact server solves per ward (the demo snaps the slider to the nearest grid point below it)
def alloc_grid(w):
    rec = allocw.get(w, {}).get('recommended_budget_inr', 1_000_000)
    mx = max(2_000_000, math.ceil(rec * 4 / STEP) * STEP)
    budgets = sorted({int(round(i * mx / 24 / STEP) * STEP) for i in range(1, 25)} | {int(rec)})
    out = []
    for b in budgets:
        r = call('POST', '/api/v3/allocate', {'ward_code': w, 'budget_inr': b})
        if r is not None: out.append({'budget': b, 'resp': r})
    return w, out
for w, grid in pool(alloc_grid, wards): save(f'alloc:{w}', grid)
print('budget grids done')

# Browse-all-roads list
roadlist, off = [], 0
while True:
    page = call('GET', f'/api/roads?limit=100&offset={off}') or []
    roadlist += page
    if len(page) < 100: break
    off += 100
save('roadlist', roadlist); print(f'{len(roadlist)} roads listed')

# Lookup and Claude citizen answers
lookups, queries = [], []
for t in LOOKUPS:
    r = call('GET', f'/api/lookup?q={q(t)}')
    if r: lookups.append({'q': t, 'result': r}); road_ids.add(r['matched_road_id'])
for t in QUERIES:
    r = call('POST', '/api/citizen-query', {'text': t, 'language': 'en', 'mode': 'street_check'})
    if r and r.get('lookup'):
        lk = r['lookup']; queries.append({'q': t, 'result': {**r, 'matched_text': lk.get('matched_text'), 'road': lk.get('road')}}); road_ids.add(r.get('matched_road_id') or lk['matched_road_id'])
save('lookups', lookups); save('queries', queries)
print(f'{len(lookups)} lookups, {len(queries)} Claude answers')

# Road receipts and timelines
def road_pack(rid): return rid, call('GET', f'/api/roads/{q(rid)}'), call('GET', f'/api/roads/{q(rid)}/timeline')
for rid, road, tl in pool(road_pack, sorted(road_ids)):
    if road is not None: save(f'road:{rid}', road)
    if tl is not None: save(f'timeline:{rid}', tl)
print(f'{len(road_ids)} road receipts')

# Claude defect notices for the roads at the top of the flagged queue
notice_roads = ['RD0220'] + [i['road_id'] for i in allq[:8] if i['road_id'] != 'RD0220']
def notice(args):
    rid, lang = args; return rid, lang, call('POST', '/api/draft-notice', {'road_id': rid, 'language': lang, 'doc_type': 'defect_notice'}, timeout=240)
notices = {}
for rid, lang, r in pool(notice, [(r, l) for r in dict.fromkeys(notice_roads) for l in ('en', 'mr')], workers=3):
    if r: notices.setdefault(rid, {})[lang] = r
save('notices', notices); print(f'{len(notices)} roads with notices')

# Livability for every locality
for loc, r in zip(localities, pool(lambda l: call('GET', f'/api/livability?locality={q(l)}'), localities)):
    if r is not None: save(f'livability:{loc}', r)

(OUT / 'manifest.json').write_text(json.dumps({'files': files, 'samples': {'queries': [x['q'] for x in queries], 'lookups': [x['q'] for x in lookups]}}, ensure_ascii=False), encoding='utf-8')
size = sum(f.stat().st_size for f in OUT.glob('*.json'))
print(f'\nDone: {len(files)} snapshots, {size / 1e6:.1f} MB in {OUT}')
