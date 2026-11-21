"""View 4: Citizen Accessibility Layer. Free-text road lookup, localities + livability, the Claude citizen
reply, and citizen reports with the accountability tracker."""
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text

from backend import claude_writer
from backend import report_lifecycle as lc
from backend import schemas as s
from backend.auth import optional_citizen
from backend.database import get_engine, invalid, norm_ward, one, parse_ts, rows
from backend.photos import public_url

router = APIRouter(tags=["View 4: Citizen Layer"])
ID_RE = re.compile(r"\b(?:WO25-\d{5}|RD\d{4}|BMC25-\d{6}|ACC\d{4})\b")
MID_LAT, MID_LON = "(r.start_lat + r.end_lat) / 2", "(r.start_lon + r.end_lon) / 2"


def candidates(lat, lon):
    """3 nearest roads (by midpoint) to a point, each with its latest work order (by completed_at)."""
    cs = rows(f"SELECT r.road_id, r.road_name, r.ward_code, r.under_dlp, "
              f"approx_m(%(lat)s, %(lon)s, {MID_LAT}, {MID_LON}) AS m, w.work_order_id, w.contractor_id, "
              f"c.contractor_name, w.cost_inr, w.completed_at, w.sla_met, w.reopened_within_30d "
              f"FROM roads r LEFT JOIN LATERAL (SELECT * FROM work_orders wo WHERE wo.road_id = r.road_id "
              f"  ORDER BY wo.completed_at DESC NULLS LAST, wo.work_order_id DESC LIMIT 1) w ON true "
              f"LEFT JOIN contractors c ON c.contractor_id = w.contractor_id "
              f"ORDER BY m, r.road_id LIMIT 3", lat=lat, lon=lon)
    wo_keys = ["work_order_id", "contractor_id", "contractor_name", "cost_inr", "completed_at", "sla_met", "reopened_within_30d"]
    return [{"road_id": c["road_id"], "road_name": c["road_name"], "ward_code": c["ward_code"],
             "under_dlp": c["under_dlp"], "road_distance_m": round(c["m"]),
             "latest_work_order": {k: c[k] for k in wo_keys} if c["work_order_id"] else None} for c in cs]


def resolve(q, language=None):
    """Free text -> lookup dict (road name in the text first, then a locality alias), or None if nothing matches."""
    road = rows(f"SELECT r.road_id, r.road_name, r.ward_code, {MID_LAT} AS lat, {MID_LON} AS lon "
                "FROM roads r WHERE position(lower(r.road_name) in lower(%(q)s)) > 0 "
                "ORDER BY length(r.road_name) DESC, r.segment_no LIMIT 1", q=q)
    alias = rows("SELECT a.alias, n.road_id, n.ward_code, n.locality, n.approx_m, l.lat, l.lon "
                 "FROM locality_aliases a JOIN locality_nearest_road n USING (locality) JOIN localities l USING (locality) "
                 "WHERE position(a.alias in lower(%(q)s)) > 0 ORDER BY length(a.alias) DESC LIMIT 1", q=q)
    if road:
        m = road[0]
        if alias:
            locality = alias[0]["locality"]
        else:  # same-ward locality whose first word is in the text ("Andheri subway" -> Andheri West), else nearest
            near = rows("SELECT locality FROM localities WHERE ward_code = %(w)s "
                        "ORDER BY position(lower(split_part(locality, ' ', 1)) in lower(%(q)s)) = 0, "
                        "approx_m(lat, lon, %(lat)s, %(lon)s) LIMIT 1", w=m["ward_code"], q=q, lat=m["lat"], lon=m["lon"])
            locality = near[0]["locality"] if near else None
        via, matched_text, road_id, distance = "road_name", m["road_name"], m["road_id"], 0
    elif alias:
        m = alias[0]
        via, matched_text, road_id, distance, locality = "locality", m["alias"], m["road_id"], m["approx_m"], m["locality"]
    else:
        return None
    receipt = one("SELECT * FROM road_audit WHERE road_id = %(r)s", "road", r=road_id)
    return {"matched_via": via, "matched_text": matched_text, "matched_locality": locality,
            "ward_code": m["ward_code"], "matched_road_id": road_id, "road_distance_m": distance,
            "warranty_status": "UNDER_DLP" if receipt["under_dlp"] else "OUT_OF_DLP", "road": receipt,
            "language": language, "candidates": candidates(m["lat"], m["lon"])}


@router.get("/api/localities", response_model=list[s.Locality], summary="Localities (with aliases) for the citizen picker")
def localities(ward: Optional[str] = Query(None, description="Ward code, e.g. K-W", examples=["K-W"])):
    if ward:
        return rows("SELECT * FROM locality_list WHERE ward_code = %(w)s ORDER BY locality", w=norm_ward(ward))
    return rows("SELECT * FROM locality_list ORDER BY locality")


@router.get("/api/lookup", response_model=s.Lookup, responses=s.NOT_FOUND, summary="Free-text landmark/road lookup -> road receipt")
def lookup(q: str = Query(min_length=2, max_length=200, description="Free text: road name, locality, alias or Devanagari",
                          examples=["Andheri subway ke bahar wapas khadda ho gaya, paisa kahan gaya?"]),
           language: Optional[s.Language] = Query(None, description="Echoed back (en|hi|mr)")):
    """View 4 deterministic lookup: free text -> road receipt + the 3 nearest roads with their latest work order.
    Tries a road name in the text first ("Andheri subway ke bahar..."), then any locality name/alias/Devanagari.
    Fuzzy/vernacular parsing beyond this is the Claude /api/citizen-query layer's job."""
    found = resolve(q, language)
    if not found:
        raise HTTPException(404, "no road or locality matched; try a road name or area name")
    return found


def livability_for(locality):
    name = rows("SELECT locality FROM locality_aliases WHERE alias = %(a)s "
                "UNION SELECT locality FROM localities WHERE lower(locality) = %(a)s LIMIT 1", a=locality.strip().lower())
    if not name:
        raise HTTPException(404, f"unknown locality {locality}")
    return one("SELECT * FROM locality_livability WHERE locality = %(l)s", "locality", l=name[0]["locality"])


@router.get("/api/livability", response_model=s.Livability, responses=s.NOT_FOUND, summary="'Moving here': livability within 1.5 km of a locality")
def livability(locality: str = Query(min_length=1, max_length=120, description="Locality name or alias (any case, Devanagari ok)",
                                     examples=["Hindmata"])):
    return livability_for(locality)


# ── Citizen query (Claude reply with template fallback) ─────────────────────
LANG_NAME = {"en": "English", "hi": "Hindi (Devanagari script)", "mr": "Marathi (Devanagari script)"}
SYSTEM = ("You write short plain-language answers for Mumbai citizens about road repairs. Use ONLY the facts in the "
          "JSON you are given; never invent numbers, names, dates or IDs. Cite the road ID and work-order ID you rely on. "
          "Neutral, factual tone: never say fraud, corrupt, scam or theft; unexplained items 'need explanation'. "
          "Answer in 3-5 sentences, plain text, no markdown, no headings.")
TASK = {"street_check": "Explain the road's warranty (DLP) status, the latest work order (contractor, cost in rupees, "
                        "completed date, whether the SLA was met, whether it was reopened within 30 days), and what the "
                        "citizen can do: tap 'Still broken' to report it (on a DLP road this auto-holds the contractor's "
                        "payment) or draft an RTI request.",
        "move_in": "Explain what these numbers mean for someone thinking of moving to this locality: flood hotspots, "
                   "repair jobs and their 30-day failure rate, hospital ambulance-access roads within 1.5 km, and the "
                   "ward's DLP leakage rate."}
NO_MATCH = {"en": "I could not find that place. Please name a nearby road or landmark (for example 'Andheri Subway' or 'Hindmata').",
            "hi": "मुझे यह जगह नहीं मिली। कृपया पास की किसी सड़क या लैंडमार्क का नाम बताइए (जैसे 'Andheri Subway' या 'हिंदमाता')।",
            "mr": "मला हे ठिकाण सापडले नाही. कृपया जवळच्या रस्त्याचे किंवा खुणेचे नाव सांगा (उदा. 'Andheri Subway' किंवा 'हिंदमाता')."}
TEMPLATES = {
    ("street_check", "en"): "{road_name} ({road_id}) is {warranty_en}. {wo_en} If it is broken again, tap 'Still broken' to report it, or draft an RTI request for the work-order records.",
    ("street_check", "hi"): "{road_name} ({road_id}) {warranty_hi}। {wo_hi} अगर सड़क फिर से टूटी है तो 'Still broken' दबाकर शिकायत करें, या काम के रिकॉर्ड के लिए RTI आवेदन तैयार करें।",
    ("street_check", "mr"): "{road_name} ({road_id}) {warranty_mr}. {wo_mr} रस्ता पुन्हा खराब झाला असल्यास 'Still broken' दाबून तक्रार करा, किंवा कामाच्या नोंदींसाठी RTI अर्ज तयार करा.",
    ("move_in", "en"): "Within 1.5 km of {locality} ({ward_code}): {flood_hotspots_1500m} flood hotspots, {jobs_1500m} road repair jobs of which {fail}% failed within 30 days, and {hospital_access_roads_1500m} hospital ambulance-access roads. The ward's DLP leakage rate is {leak}%.",
    ("move_in", "hi"): "{locality} ({ward_code}) के 1.5 किमी के भीतर: {flood_hotspots_1500m} जलभराव वाले स्थान, {jobs_1500m} सड़क मरम्मत कार्य जिनमें से {fail}% 30 दिन में फिर खराब हुए, और अस्पताल तक एम्बुलेंस पहुँच वाली {hospital_access_roads_1500m} सड़कें। वार्ड की DLP लीकेज दर {leak}% है।",
    ("move_in", "mr"): "{locality} ({ward_code}) पासून 1.5 किमीच्या आत: {flood_hotspots_1500m} पाणी साचणारी ठिकाणे, {jobs_1500m} रस्ता दुरुस्ती कामे ज्यापैकी {fail}% 30 दिवसांत पुन्हा खराब झाली, आणि रुग्णालयापर्यंत रुग्णवाहिका पोहोचणारे {hospital_access_roads_1500m} रस्ते. वॉर्डचा DLP लीकेज दर {leak}% आहे.",
}


def pct(x):
    return "n/a" if x is None else f"{x * 100:.0f}"


def template(mode, lang, facts):
    if mode == "move_in":
        lv = facts["livability"]
        return TEMPLATES[mode, lang].format(**lv, fail=pct(lv["failure_rate_30d_1500m"]), leak=pct(lv["ward_dlp_leakage_rate"]))
    road, wo = facts["road"], facts["latest_work_order"]
    dlp = road["under_dlp"]
    exp = road.get("dlp_expires_on") or ""
    v = {"road_name": road["road_name"], "road_id": road["road_id"],
         "warranty_en": f"under the contractor's Defect Liability Period (warranty, est. until {exp})" if dlp else "out of its Defect Liability Period (warranty)",
         "warranty_hi": f"ठेकेदार की दोष दायित्व अवधि (DLP वारंटी, अनुमानित {exp} तक) में है" if dlp else "DLP वारंटी अवधि में नहीं है",
         "warranty_mr": f"ठेकेदाराच्या दोष दायित्व कालावधीत (DLP वॉरंटी, अंदाजे {exp} पर्यंत) आहे" if dlp else "DLP वॉरंटी कालावधीत नाही"}
    if wo:
        yn = lambda b, y, n: "?" if b is None else y if b else n  # noqa: E731
        d, cost = (wo["completed_at"] or "")[:10], f"{wo['cost_inr']:,.0f}"
        v["wo_en"] = (f"The latest work order {wo['work_order_id']} by {wo['contractor_name']} cost Rs {cost}, completed {d}; "
                      f"SLA met: {yn(wo['sla_met'], 'yes', 'no')}, reopened within 30 days: {yn(wo['reopened_within_30d'], 'yes', 'no')}.")
        v["wo_hi"] = (f"आखिरी कार्य आदेश {wo['work_order_id']} ({wo['contractor_name']}) की लागत ₹{cost} थी, {d} को पूरा हुआ; "
                      f"SLA पूरा: {yn(wo['sla_met'], 'हाँ', 'नहीं')}, 30 दिन में दोबारा खुला: {yn(wo['reopened_within_30d'], 'हाँ', 'नहीं')}।")
        v["wo_mr"] = (f"शेवटचा कार्यादेश {wo['work_order_id']} ({wo['contractor_name']}) याचा खर्च ₹{cost}, {d} रोजी पूर्ण; "
                      f"SLA पूर्ण: {yn(wo['sla_met'], 'हो', 'नाही')}, 30 दिवसांत पुन्हा उघडला: {yn(wo['reopened_within_30d'], 'हो', 'नाही')}.")
    else:
        v |= {"wo_en": "No work order is recorded for this road.", "wo_hi": "इस सड़क का कोई कार्य आदेश दर्ज नहीं है।",
              "wo_mr": "या रस्त्याचा कोणताही कार्यादेश नोंदलेला नाही."}
    return TEMPLATES[mode, lang].format(**v)


def ids_ok(reply, facts):
    allowed = set(ID_RE.findall(json.dumps(facts, ensure_ascii=False, default=str)))
    return set(ID_RE.findall(reply)) <= allowed


@router.post("/api/citizen-query", response_model=s.CitizenQueryReply, summary="Citizen question -> plain-language answer (Claude, template fallback)")
def citizen_query(req: s.CitizenQueryReq):
    """Resolves the text like /api/lookup, then Claude rewrites the precomputed facts as a 3-5 sentence answer in the
    requested language. Falls back to a template if Claude is slow/unavailable or cites an ID not in the facts."""
    found = resolve(req.text, req.language)
    base = {"mode": req.mode, "language": req.language, "lookup": found}
    if not found:
        return {**base, "matched_locality": None, "matched_road_id": None, "warranty_status": None,
                "plain_language_reply": NO_MATCH[req.language], "generated_by": "template"}
    lv = livability_for(found["matched_locality"]) if req.mode == "move_in" and found["matched_locality"] else None
    if req.mode == "move_in" and lv:
        facts = {"locality": found["matched_locality"], "livability": lv}
    else:  # street_check, or move_in without a resolvable locality
        latest = next((c["latest_work_order"] for c in found["candidates"] if c["road_id"] == found["matched_road_id"]), None)
        if latest is None:
            w = rows("SELECT wo.work_order_id, wo.contractor_id, c.contractor_name, wo.cost_inr, wo.completed_at, wo.sla_met, "
                     "wo.reopened_within_30d FROM work_orders wo JOIN contractors c USING (contractor_id) "
                     "WHERE wo.road_id = %(r)s ORDER BY wo.completed_at DESC NULLS LAST, wo.work_order_id DESC LIMIT 1",
                     r=found["matched_road_id"])
            latest = w[0] if w else None
        facts = {"locality": found["matched_locality"], "warranty_status": found["warranty_status"],
                 "road": found["road"], "latest_work_order": latest}
    mode = "move_in" if "livability" in facts else "street_check"
    reply = claude_writer.write(SYSTEM, f"Citizen asked: {req.text!r}\nTask: {TASK[mode]}\n"
                                        f"Write the answer in {LANG_NAME[req.language]}.\n"
                                        f"FACTS (JSON):\n{json.dumps(facts, ensure_ascii=False, default=str)}", max_tokens=1500)
    by = "claude"
    if not reply or not ids_ok(reply, facts):
        reply, by = template(mode, req.language, facts), "template"
    return {**base, "matched_locality": found["matched_locality"], "matched_road_id": found["matched_road_id"],
            "warranty_status": found["warranty_status"], "plain_language_reply": reply, "generated_by": by,
            "livability": lv}


# ── Citizen reports ─────────────────────────────────────────────────────────
SURFACE = ("pothole", "broken_paver")
SURFACE_WORK = ("Pothole", "Broken paver blocks")
NEAREST_M = 500  # a location only matches a road whose midpoint is within this distance


def is_dlp_surface(r):
    """Road under DLP and a surface defect (pothole/broken paver, or an untyped 'still broken')."""
    surface = r["issue_type"] in SURFACE or (r["issue_type"] is None and r["kind"] == "still_broken")
    return bool(r["road_id"] and r["under_dlp"] and surface)


def check_photo_ids(photo_ids):
    """422 unless every id is unique and was uploaded via POST /api/uploads/photo."""
    if len(set(photo_ids)) != len(photo_ids):
        raise invalid("photo_ids", "photo_ids contains duplicates")
    if photo_ids:
        known = {p["photo_id"] for p in rows("SELECT photo_id FROM photos WHERE photo_id IN %(ids)s", ids=tuple(photo_ids))}
        if missing := [p for p in photo_ids if p not in known]:
            raise invalid("photo_ids", f"unknown photo_ids (upload them first via POST /api/uploads/photo): {', '.join(missing)}")


def first_photo_url(row, request):
    """photo_url for a row carrying storage/storage_path/photo_id of its first photo (or None)."""
    return public_url(row["storage"], row["storage_path"], row["photo_id"], request) if row.get("photo_id") else None


def hold_eligible(r):
    """An officer may put this report in payment_held: DLP surface defect, and not a 'verified fixed' report."""
    return r["kind"] != "verified_fixed" and is_dlp_surface(r)


def find_road(req):
    """road_id (404 if unknown) -> nearest road within 500 m of location -> landmark/text via resolve(). (road_id, locality)."""
    if req.road_id:
        one("SELECT 1 FROM roads WHERE road_id = %(r)s", f"road {req.road_id}", r=req.road_id)
        return req.road_id, None
    if req.location:
        near = rows(f"SELECT r.road_id, approx_m(%(lat)s, %(lon)s, {MID_LAT}, {MID_LON}) AS m FROM roads r "
                    "ORDER BY m, r.road_id LIMIT 1", lat=req.location.lat, lon=req.location.lon)
        if near and near[0]["m"] <= NEAREST_M:
            return near[0]["road_id"], None
    for q in (req.landmark, req.text):
        found = resolve(q) if q and q.strip() else None
        if found:
            return found["matched_road_id"], found["matched_locality"]
    return None, None


ACTOR = {"citizen": "citizen", "admin": "ward_office", "system": "system"}


def add_event(c, report_id, actor_type, event_type, from_status, to_status, note=None, photo_ids=(),
              admin_id=None, meta=None):
    """Append to the report's history inside the caller's transaction (c = connection from get_engine().begin())."""
    c.execute(text("INSERT INTO citizen_report_events (report_id, actor_type, admin_id, event_type, from_status, "
                   "to_status, note, photo_ids, meta) VALUES (:r, :a, CAST(:adm AS uuid), :e, :f, :t, :n, :p, "
                   "CAST(:m AS jsonb))"),
              {"r": report_id, "a": actor_type, "adm": admin_id, "e": event_type, "f": from_status, "t": to_status,
               "n": note, "p": list(photo_ids), "m": json.dumps(meta or {}, default=str)})


def report_events(report_ids):
    """{report_id: [raw event rows, oldest first]} for the given reports (every id present, possibly [])."""
    out = {i: [] for i in report_ids}
    if report_ids:
        for e in rows("SELECT report_id, at, actor_type, event_type, from_status, to_status, note, photo_ids "
                      "FROM citizen_report_events WHERE report_id IN %(ids)s ORDER BY at, id", ids=tuple(report_ids)):
            out[e["report_id"]].append(e)
    return out


def event_out(e):
    """API shape of an event: who acted is citizen / ward_office / system, never an officer's identity."""
    actor = ACTOR[e["actor_type"]]
    return {"at": e["at"], "event_type": e["event_type"], "actor": actor,
            "from_status": e["from_status"], "to_status": e["to_status"], "note": e["note"],
            "photo_ids": list(e["photo_ids"] or []), "status": e["to_status"], "by_role": actor}


def build_report(report_id, request):
    """The full CitizenReport, rebuilt from the DB (shared by POST and GET). Never includes contact_phone."""
    r = one("SELECT cr.*, cr.location_accuracy_m::float8 AS accuracy_m, ra.road_name, ra.ward_code, ra.under_dlp, "
            "ra.dlp_expires_on, w.assistant_commissioner_office AS office, i.sla_hours, lc.contractor_name AS linked_contractor, "
            "(SELECT c2.contractor_name FROM work_orders wo2 JOIN contractors c2 USING (contractor_id) "
            " WHERE wo2.road_id = cr.road_id AND wo2.work_type IN %(sw)s "
            " ORDER BY wo2.completed_at DESC NULLS LAST, wo2.work_order_id DESC LIMIT 1) AS surface_contractor "
            "FROM citizen_reports cr LEFT JOIN road_audit ra ON ra.road_id = cr.road_id "
            "LEFT JOIN wards w ON w.ward_code = ra.ward_code LEFT JOIN issue_sla i ON i.issue_type = cr.issue_type "
            "LEFT JOIN work_orders lw ON lw.work_order_id = cr.linked_work_order_id "
            "LEFT JOIN contractors lc ON lc.contractor_id = lw.contractor_id WHERE cr.id = %(i)s",
            f"report {report_id}", i=report_id, sw=SURFACE_WORK)
    photos = rows("SELECT p.photo_id, p.storage, p.storage_path, p.width, p.height FROM citizen_report_photos crp "
                  "JOIN photos p USING (photo_id) WHERE crp.report_id = %(i)s ORDER BY crp.position", i=report_id)
    evs = report_events([report_id])[report_id]
    road = responsible = None
    if r["road_id"]:
        road = {k: r[k] for k in ("road_id", "road_name", "ward_code", "under_dlp")}
        if is_dlp_surface(r):
            exp = (r["dlp_expires_on"] or "")[:10] or "an unknown date"
            responsible = {"party": "contractor_under_dlp", "name": r["linked_contractor"] or r["surface_contractor"],
                           "ward_office": r["office"],
                           "basis": f"The dataset marks this road under the original contractor's Defect Liability Period "
                                    f"(estimated to run until {exp}), so surface defects are the contractor's to fix at "
                                    "no cost to BMC."}
        else:
            responsible = {"party": "bmc_ward", "name": r["office"], "ward_office": r["office"],
                           "basis": "Not a surface defect on a road under its Defect Liability Period, so the ward "
                                    "office repairs it from BMC funds."}
    loc = None if r["location_lat"] is None else {"lat": r["location_lat"], "lon": r["location_lon"],
                                                  "accuracy_m": r["accuracy_m"], "source": r["location_source"]}
    return {"report_id": r["id"], "kind": r["kind"], "issue_type": r["issue_type"], "status": r["status"], "road": road,
            "duplicate_of": r["duplicate_of"], "linked_work_order_id": r["linked_work_order_id"],
            "responsible": responsible, "sla_hours": r["sla_hours"],
            "photos": [{"photo_id": p["photo_id"], "photo_url": public_url(p["storage"], p["storage_path"], p["photo_id"], request),
                        "width": p["width"], "height": p["height"]} for p in photos],
            "tracker": lc.tracker(r["status"], r["created_at"], evs, hold_eligible(r), r["status_updated_at"]),
            "flag_id": r["flag_id"], "landmark": r["landmark"], "location": loc,
            "input_mode": r["input_mode"], "language": r["language"], "text": r["text"],
            "matched_locality": r["matched_locality"], "created_at": r["created_at"],
            "events": [event_out(e) for e in evs],
            "sla_due_at": lc.sla_due_at(parse_ts(r["created_at"]), r["sla_hours"], parse_ts(r["repair_due_at"])),
            "repair_due_at": r["repair_due_at"], "resolved_at": r["resolved_at"],
            "rejection_reason": r["rejection_reason"], "payment_hold_eligible": hold_eligible(r)}


@router.post("/api/citizen-reports", status_code=201, response_model=s.CitizenReport,
             responses={**s.NOT_FOUND, 401: s.AUTH[401]}, summary="Submit citizen report (server sets tracker status)")
def add_citizen_report(req: s.CitizenReportReq, request: Request,
                       citizen: Optional[dict] = Depends(optional_citizen)):
    """View 4 report. The server resolves the road (road_id -> location within 500 m -> landmark/text), links the latest
    matching work order, detects a duplicate (same road + issue in 7 days) and sets the status: matched_to_contract when
    a road matched, else reported. Officers move it on (payment hold, contractor notice, ...); clients cannot set it.
    With `Authorization: Bearer <citizen token>` the report is saved to that citizen (GET /api/me/reports).
    contact_phone is stored privately and never returned."""
    check_photo_ids(req.photo_ids)
    if req.flag_id and not rows("SELECT 1 FROM flags WHERE flag_id = %(f)s", f=req.flag_id):
        raise invalid("flag_id", f"unknown flag_id {req.flag_id}")
    if req.work_order_id:
        one("SELECT 1 FROM work_orders WHERE work_order_id = %(w)s", f"work order {req.work_order_id}", w=req.work_order_id)
    road_id, locality = find_road(req)
    linked = req.work_order_id
    if not linked and road_id and req.issue_type not in (None, "other"):
        w = rows("SELECT wo.work_order_id FROM work_orders wo JOIN issue_sla i ON i.work_type = wo.work_type "
                 "WHERE wo.road_id = %(r)s AND i.issue_type = %(t)s "
                 "ORDER BY wo.completed_at DESC NULLS LAST, wo.work_order_id DESC LIMIT 1", r=road_id, t=req.issue_type)
        linked = w[0]["work_order_id"] if w else None
    kind = req.kind or ("still_broken" if linked else "new_issue")
    status, flag_id = "reported", req.flag_id
    if road_id:
        status = "matched_to_contract"  # insert stops here; an officer decides on the payment hold
        under_dlp = one("SELECT under_dlp FROM roads WHERE road_id = %(r)s", "road", r=road_id)["under_dlp"]
        if kind != "verified_fixed" and is_dlp_surface({"road_id": road_id, "under_dlp": under_dlp,
                                                         "issue_type": req.issue_type, "kind": kind}):
            if not flag_id:  # DLP surface defect: link the bill the hold would apply to
                f = rows("SELECT flag_id FROM flags WHERE road_id = %(r)s AND detector = 'DLP_PAID_TWICE' "
                         "ORDER BY rupees_at_stake DESC LIMIT 1", r=road_id)
                flag_id = f[0]["flag_id"] if f else None
    loc = req.location
    with get_engine().begin() as c:
        dup = None
        if road_id and req.issue_type:
            dup = c.execute(text("SELECT id FROM citizen_reports WHERE road_id = :r AND issue_type = :t "
                                 "AND created_at >= now() - interval '7 days' ORDER BY created_at, id LIMIT 1"),
                            {"r": road_id, "t": req.issue_type}).scalar()
        report_id = c.execute(text(
            "INSERT INTO citizen_reports (kind, issue_type, input_mode, text, language, matched_locality, road_id, "
            "work_order_id, linked_work_order_id, flag_id, status, duplicate_of, landmark, location_lat, location_lon, "
            "location_accuracy_m, location_source, citizen_id) VALUES (:kind, :issue_type, :input_mode, :text, :language, "
            ":matched_locality, :road_id, :work_order_id, :linked, :flag_id, :status, :dup, :landmark, :lat, :lon, "
            ":acc, :src, CAST(:cid AS uuid)) RETURNING id"),
            {"kind": kind, "issue_type": req.issue_type, "input_mode": req.input_mode, "text": req.text,
             "language": req.language, "matched_locality": req.matched_locality or locality, "road_id": road_id,
             "work_order_id": req.work_order_id, "linked": linked, "flag_id": flag_id, "status": status, "dup": dup,
             "landmark": req.landmark, "lat": loc and loc.lat, "lon": loc and loc.lon,
             "acc": loc and loc.accuracy_m, "src": loc and loc.source,
             "cid": citizen and citizen["citizen_id"]}).scalar_one()
        add_event(c, report_id, "citizen", "created", None, status,
                  meta={"road_matched": bool(road_id), "duplicate_of": dup})
        for pos, pid in enumerate(req.photo_ids, 1):
            c.execute(text("INSERT INTO citizen_report_photos (report_id, photo_id, position) VALUES (:r, :p, :n)"),
                      {"r": report_id, "p": pid, "n": pos})
        if req.contact_phone:
            c.execute(text("INSERT INTO citizen_report_contacts (report_id, contact_phone) VALUES (:r, :p)"),
                      {"r": report_id, "p": req.contact_phone})
    return build_report(report_id, request)


@router.get("/api/citizen-reports/{report_id}", response_model=s.CitizenReport, responses=s.NOT_FOUND, summary="Citizen report status + tracker")
def citizen_report(report_id: int, request: Request):
    """Public status page for a report: tracker, events[] (history), sla_due_at, rejection_reason. No contact data."""
    return build_report(report_id, request)
