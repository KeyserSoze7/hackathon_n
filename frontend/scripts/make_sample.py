"""Throwaway sample-data builder. Reads ../data CSVs, writes src/data/*.json.
Replaced by Supabase exports later. Every number is computed here, never in the UI."""
import json, math, pathlib
import numpy as np, pandas as pd

D = pathlib.Path(__file__).resolve().parents[2] / 'data'
OUT = pathlib.Path(__file__).resolve().parents[1] / 'src' / 'data'
OUT.mkdir(exist_ok=True)
PUB = pathlib.Path(__file__).resolve().parents[1] / 'public' / 'data'  # served as /data/*.json for the standalone HTML

wo = pd.read_csv(D/'work_orders.csv', parse_dates=['assigned_at', 'work_started_at', 'completed_at'])
rd = pd.read_csv(D/'roads.csv', parse_dates=['last_resurfaced'])
wd = pd.read_csv(D/'wards.csv'); rc = pd.read_csv(D/'rate_card.csv')
cm = pd.read_csv(D/'complaints.csv'); ac = pd.read_csv(D/'accidents.csv')
ct = pd.read_csv(D/'contractors.csv'); tr = pd.read_csv(D/'traffic.csv')
fh = pd.read_csv(D/'flood_hotspots.csv'); fc = pd.read_csv(D/'facilities.csv')
lc = pd.read_csv(D/'localities.csv'); rain = pd.read_csv(D/'rainfall_daily.csv', parse_dates=['date'])
cname = dict(zip(ct.contractor_id, ct.contractor_name.str.replace(' (synthetic)', '', regex=False)))
lowlying = dict(zip(wd.ward_code, wd.low_lying_index))

m = wo.merge(rd[['road_id', 'road_name', 'under_dlp', 'last_resurfaced']], on='road_id').merge(rc, on='repair_method')
m['expected'] = np.where(m.unit == 'per sqm', m.area_sqm * m.standard_rate_inr, m.standard_rate_inr)
m['ratio'] = m.cost_inr / m.expected
m['dlp'] = m.under_dlp == 'Y'
m['reop'] = m.reopened_within_30d == 'Y'
m['sla'] = m.sla_met == 'Y'

# ---------- summary (City Pulse) ----------
cpc = cm.groupby('ward_code').size()
wards = []
for _, w in wd.iterrows():
    g = m[m.ward_code == w.ward_code]
    spend = int(g.cost_inr.sum()); rec = int(g[g.dlp].cost_inr.sum())
    n = int(cpc.get(w.ward_code, 0))
    wards.append(dict(ward_code=w.ward_code, ward_name=w.ward_name, budget_inr=int(w.monsoon_repair_budget_inr_2025),
        spend_inr=spend, recoverable_dlp_inr=rec, dlp_share=round(rec / spend, 3) if spend else 0,
        low_lying_index=float(w.low_lying_index), complaints=n, complaints_per_100k=round(n / w.population_est * 1e5, 1),
        flagged_jobs=int(((g.dlp) | (g.ratio > 1.5)).sum()), engineering_crews=int(w.engineering_crews)))
# under-reported: flood-prone (>=0.6) but complaints per 100k in the bottom third of all wards
cut = np.percentile([w['complaints_per_100k'] for w in wards], 34)
for w in wards:
    w['under_reported'] = bool(w['low_lying_index'] >= 0.6 and w['complaints_per_100k'] <= cut)

city = dict(budget_inr=int(wd.monsoon_repair_budget_inr_2025.sum()), spend_inr=int(m.cost_inr.sum()),
    recoverable_dlp_inr=int(m[m.dlp].cost_inr.sum()), dlp_jobs=int(m.dlp.sum()),
    flagged_jobs=int(((m.dlp) | (m.ratio > 1.5)).sum()), reopened_jobs=int(m.reop.sum()), jobs=len(m))

# ---------- per-road detail (Road Receipt) ----------
def road_obj(road_id):
    r = rd[rd.road_id == road_id].iloc[0]; g = m[m.road_id == road_id].sort_values('assigned_at')
    wos, flags = [], []
    for _, a in g.iterrows():
        wos.append(dict(work_order_id=a.work_order_id, contractor_id=a.contractor_id, contractor_name=cname[a.contractor_id],
            repair_method=a.repair_method, cost_inr=int(a.cost_inr), expected_inr=int(a.expected),
            assigned_at=str(a.assigned_at)[:10], completed_at=str(a.completed_at)[:10], sla_met=bool(a.sla), reopened=bool(a.reop),
            complaint_ids=[] if pd.isna(a.linked_complaint_ids) else a.linked_complaint_ids.split('|')))
        if a.dlp:
            flags.append(dict(detector='DLP_PAID_TWICE', tier=1, work_order_id=a.work_order_id, rupees_at_stake=int(a.cost_inr),
                rule_text=f"Road was resurfaced on {str(r.last_resurfaced)[:10]} and is still under its Defect Liability Period, yet BMC was billed.",
                evidence=[a.work_order_id, road_id]))
        if a.ratio > 1.5:
            flags.append(dict(detector='RATE_INFLATION', tier=2, work_order_id=a.work_order_id,
                rupees_at_stake=int(a.cost_inr - a.expected),
                rule_text=f"Billed {a.ratio:.1f} times the rate-card amount for {a.repair_method}.", evidence=[a.work_order_id]))
    flags.sort(key=lambda f: -f['rupees_at_stake'])
    ids = {c for w in wos for c in w['complaint_ids']}
    comps = cm[cm.complaint_id.isin(ids)].sort_values('received_at')
    complaints = [dict(complaint_id=c.complaint_id, received_at=c.received_at, category=c.category_reported, channel=c.channel, status=c.status)
                  for _, c in comps.iterrows()]
    acc = ac[ac.road_id == road_id].sort_values('occurred_at')
    accidents = [dict(accident_id=a.accident_id, occurred_at=a.occurred_at, severity=a.severity, cause=a.probable_cause) for _, a in acc.iterrows()]
    return dict(road_id=road_id, road_name=r.road_name, segment_no=int(r.segment_no), ward_code=r.ward_code, surface=r.surface,
        road_type=r.road_type, length_m=int(r.length_m), last_resurfaced=str(r.last_resurfaced)[:10], under_dlp=bool(r.under_dlp == 'Y'),
        total_billed_inr=int(g.cost_inr.sum()), recoverable_inr=int(g[g.dlp].cost_inr.sum()),
        work_orders=wos, flags=flags, complaints=complaints, accidents=accidents)

roads = {rid: road_obj(rid) for rid in rd.road_id}
dl = m[m.dlp].groupby('road_id').agg(r=('cost_inr', 'sum'), n=('cost_inr', 'size'), re=('reop', 'sum')).sort_values('r', ascending=False)
summary = dict(city=city, wards=wards, queue=[dict(road_id=rid, road_name=roads[rid]['road_name'], ward_code=roads[rid]['ward_code'],
    rupees_at_stake=int(dl.loc[rid, 'r']), jobs=int(dl.loc[rid, 'n']), reopened=int(dl.loc[rid, 're'])) for rid in dl.index[:10]])

# road list for pickers (sorted by what matters)
roadlist = sorted([dict(road_id=r['road_id'], road_name=r['road_name'], segment_no=r['segment_no'], ward_code=r['ward_code'],
    under_dlp=r['under_dlp'], billed=r['total_billed_inr'], recoverable=r['recoverable_inr']) for r in roads.values()],
    key=lambda r: -r['recoverable'])

# ---------- contractor ledger (fair scorecard) ----------
heavy = rain[rain.rainfall_mm >= 64.5].date.dt.normalize().unique()
def heavy_during(a):
    days = pd.date_range(a.assigned_at.normalize(), a.completed_at.normalize())
    return any(d in set(heavy) for d in days)
hs = set(heavy)
m['heavy'] = m.apply(lambda a: any(d in hs for d in pd.date_range(a.assigned_at.normalize(), a.completed_at.normalize())), axis=1)
m['flood_ward'] = m.ward_code.map(lowlying) >= 0.6
m = m.merge(tr[['road_id', 'peak_hour_vehicles']], on='road_id', how='left')
# expected reopen rate per job: citywide rate for same repair method and same flood-proneness tier
exp_rate = m.groupby(['repair_method', 'flood_ward']).reop.mean()
m['exp_reop'] = [exp_rate[(a, b)] for a, b in zip(m.repair_method, m.flood_ward)]
def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))
contractors = []
for cid, g in m.groupby('contractor_id'):
    n = len(g); k = int(g.reop.sum()); lo, hi = wilson(k, n)
    expected = float(g.exp_reop.mean()); slo, shi = wilson(int(g.sla.sum()), n)
    status = 'higher' if expected < lo else 'lower' if expected > hi else 'inline'
    contractors.append(dict(contractor_id=cid, contractor_name=cname[cid], jobs=n, total_billed_inr=int(g.cost_inr.sum()),
        reopen_rate=round(k / n, 3), reopen_ci=[round(lo, 3), round(hi, 3)], expected_reopen_rate=round(expected, 3), reopen_vs_expected=status,
        sla_rate=round(float(g.sla.mean()), 3), sla_ci=[round(slo, 3), round(shi, 3)],
        median_cost_ratio=round(float(g.ratio.median()), 2), jobs_over_1_5x=int((g.ratio > 1.5).sum()),
        warranty_jobs=int(g.dlp.sum()), recoverable_inr=int(g[g.dlp].cost_inr.sum()),
        context=dict(flood_ward_share=round(float(g.flood_ward.mean()), 3), heavy_rain_share=round(float(g.heavy.mean()), 3),
            avg_peak_vehicles=int(g.peak_hour_vehicles.mean()), wards=int(g.ward_code.nunique()))))
contractors.sort(key=lambda c: -c['total_billed_inr'])

# ---------- next-rupee planner ----------
OUT_METHODS = []
for meth, g in m.groupby('repair_method'):
    OUT_METHODS.append(dict(method=meth, jobs=len(g), reopen_rate=round(float(g.reop.mean()), 3), unit=g.unit.iloc[0]))
OUT_METHODS.sort(key=lambda x: x['reopen_rate'])
def hav(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 12742000 * math.asin(math.sqrt(a))
rd['mid_lat'] = (rd.start_lat + rd.end_lat) / 2; rd['mid_lon'] = (rd.start_lon + rd.end_lon) / 2
acc_bad = ac[ac.probable_cause.isin(['Pothole', 'Waterlogged road', 'Uneven road / open chamber'])]
acc_n = acc_bad.groupby('road_id').size(); reop_n = m.groupby('road_id').reop.sum()
hosp = fc[(fc.type == 'Hospital')].groupby('ambulance_entry_road').size()
school = fc[(fc.type == 'School')].groupby('ambulance_entry_road').size()
trf = tr.set_index('road_id')
med_cost = m.groupby('road_id').cost_inr.median()
fallback = float(m.cost_inr.median())
under_rep = {w['ward_code'] for w in wards if w['under_reported']}
rows = []
for _, r in rd.iterrows():
    nflood = int(sum(hav(r.mid_lat, r.mid_lon, h.lat, h.lon) <= 800 for _, h in fh.iterrows()))
    rows.append(dict(road_id=r.road_id, road_name=r.road_name, segment_no=int(r.segment_no), ward_code=r.ward_code, under_dlp=bool(r.under_dlp == 'Y'),
        vehicles=int(trf.loc[r.road_id].peak_hour_vehicles) if r.road_id in trf.index else 0,
        accidents=int(acc_n.get(r.road_id, 0)), flood_spots=nflood, hospitals=int(hosp.get(r.road_id, 0)), schools=int(school.get(r.road_id, 0)),
        failures=int(reop_n.get(r.road_id, 0)), bus=bool(r.bus_route == 'Y'),
        estimated_repair_cost_inr=int(round(float(med_cost.get(r.road_id, fallback)), -3))))
df = pd.DataFrame(rows)
nz = lambda s: s / s.max() if s.max() else s
df['score'] = (25 * nz(df.vehicles) + 20 * nz(df.accidents) + 20 * (df.flood_spots > 0).astype(float) + 15 * (df.hospitals > 0).astype(float)
               + 15 * nz(df.failures) + 5 * df.bus.astype(float) + df.schools.clip(upper=1) * 0)
df['under_reported'] = df.ward_code.isin(under_rep)
df['score'] = (df.score + df.under_reported * 5).round(1)
vq = df.vehicles.quantile(0.75)
def reasons(x):
    out = []
    if x.flood_spots > 0: out.append('FLOOD_SPOT')
    if x.hospitals > 0: out.append('AMBULANCE_ROUTE')
    if x.vehicles >= vq: out.append('HIGH_TRAFFIC')
    if x.accidents >= 1: out.append('ACCIDENT_PRONE')
    if x.failures >= 2: out.append('REPEAT_FAILURE')
    if x.under_reported: out.append('UNDER_REPORTED_WARD')
    return out
df['reason_codes'] = df.apply(reasons, axis=1)
df['cost_to_bmc_inr'] = np.where(df.under_dlp, 0, df.estimated_repair_cost_inr)
df = df.sort_values('score', ascending=False)
planner = dict(methods=OUT_METHODS, roads=json.loads(df.drop(columns=['bus']).to_json(orient='records')))

# ---------- localities for citizen lookup ----------
locs = []
mids = rd[['road_id', 'mid_lat', 'mid_lon', 'ward_code']]
for _, l in lc.iterrows():
    cand = mids[mids.ward_code == l.ward_code]
    if cand.empty: cand = mids
    d = cand.apply(lambda r: hav(l.lat, l.lon, r.mid_lat, r.mid_lon), axis=1)
    near = cand.assign(d=d).sort_values('d').head(3)
    locs.append(dict(locality=l.locality, ward_code=l.ward_code, aliases=[] if pd.isna(l.aliases) else [a.strip() for a in str(l.aliases).split(';') if a.strip()],
        road_ids=list(near.road_id), distance_m=[int(x) for x in near.d]))

# ---------- 1.5 km livability per locality (Moving Here) ----------
wmap = {w['ward_code']: w for w in wards}
fail_by_road = m.groupby('road_id').reop.agg(['sum', 'size'])
hosp_roads = set(fc[fc.type == 'Hospital'].ambulance_entry_road)
live = []
for _, l in lc.iterrows():
    dist_road = rd.apply(lambda r: hav(l.lat, l.lon, r.mid_lat, r.mid_lon), axis=1)
    near = rd[dist_road <= 1500]
    fails = sum(int(fail_by_road.loc[r, 'sum']) for r in near.road_id if r in fail_by_road.index)
    jobs = sum(int(fail_by_road.loc[r, 'size']) for r in near.road_id if r in fail_by_road.index)
    flood = int(sum(hav(l.lat, l.lon, h.lat, h.lon) <= 1500 for _, h in fh.iterrows()))
    hosp = sorted({r for r in near.road_id if r in hosp_roads})
    live.append(dict(locality=l.locality, ward_code=l.ward_code, flood_spots_1500m=flood, roads_1500m=int(len(near)),
        failure_rate_30d_1500m=round(fails / jobs, 3) if jobs else None, jobs_1500m=jobs,
        hospital_access_roads_1500m=len(hosp), ward_warranty_share=wmap[l.ward_code]['dlp_share']))

for name, obj in [('summary', summary), ('roads', roads), ('roadlist', roadlist), ('contractors', contractors), ('planner', planner), ('localities', locs), ('livability', live)]:
    txt = json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
    (OUT / f'{name}.json').write_text(txt, encoding='utf-8')
    PUB.mkdir(parents=True, exist_ok=True)
    (PUB / f'{name}.json').write_text(txt, encoding='utf-8')
print('ok', city, {c['contractor_id']: c['reopen_vs_expected'] for c in contractors}, [r['road_id'] for r in planner['roads'][:5]], sum(w['under_reported'] for w in wards))
