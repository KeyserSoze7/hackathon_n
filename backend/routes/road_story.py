"""View 2: Road Story / Rupee Receipt. Road header + work orders + flags, connected timeline, Right-of-Reply,
Claude-drafted defect notices / RTI applications (template fallback)."""
import json
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request
from sqlalchemy import text

from backend import claude_writer
from backend import schemas as s
from backend.database import get_engine, norm_ward, one, rows
from backend.photos import public_url

router = APIRouter(tags=["View 2: Road Story"])
DLP_RULE = ("DLP length is assumed to be 36 months (the dataset only says whether a road is under DLP); "
            "dlp_expires_on = last_resurfaced + 36 months.")


@router.get("/api/roads", response_model=list[s.RoadListItem], summary="Road search / picker")
def roads(q: Optional[str] = Query(None, max_length=200, description="Road name substring or road_id prefix", examples=["Andheri"]),
          ward: Optional[str] = Query(None, examples=["K-W"]),
          limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    """Roads matching q (road_name ILIKE %q% or road_id ILIKE q%), optionally in one ward."""
    like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") if q else None
    return rows("SELECT road_id, road_name, segment_no, ward_code, under_dlp, total_billed_inr, rupees_at_stake, "
                "flagged_bills_count FROM road_audit "
                "WHERE (%(q)s::text IS NULL OR road_name ILIKE '%%' || %(q)s || '%%' OR road_id ILIKE %(q)s || '%%') "
                "AND (%(w)s::text IS NULL OR ward_code = %(w)s) "
                "ORDER BY road_name, segment_no LIMIT %(lim)s OFFSET %(off)s",
                q=like, w=norm_ward(ward), lim=limit, off=offset)


@router.get("/api/roads/{road_id}", response_model=s.RoadReceipt, responses=s.NOT_FOUND, summary="Road receipt: header, work orders, flags + replies")
def road(road_id: str = Path(examples=["RD0058"])):
    """View 2 header card + work orders + flags (with replies)."""
    r = one("SELECT * FROM road_audit WHERE road_id = %(r)s", f"road {road_id}", r=road_id)
    r["work_orders"] = rows(
        "SELECT wo.work_order_id, wo.contractor_id, c.contractor_name, wo.work_type, wo.repair_method, wo.cost_inr, "
        "wo.assigned_at, wo.completed_at, wo.sla_met, wo.reopened_within_30d, wo.engineer_remark, "
        "COALESCE(ra.under_dlp AND wo.completed_at::date <= ra.dlp_expires_on, false) AS under_dlp_at_billing "
        "FROM work_orders wo JOIN contractors c USING (contractor_id) JOIN road_audit ra USING (road_id) "
        "WHERE wo.road_id = %(r)s ORDER BY wo.assigned_at",
        r=road_id)
    r["flags"] = rows(
        "SELECT f.*, COALESCE((SELECT json_agg(rp ORDER BY rp.created_at) FROM flag_replies rp "
        "WHERE rp.flag_id = f.flag_id), '[]') AS replies FROM flags f WHERE f.road_id = %(r)s "
        "ORDER BY f.tier, f.rupees_at_stake DESC", r=road_id)
    r["dlp_rule"] = DLP_RULE
    return r


@router.get("/api/roads/{road_id}/reports", response_model=list[s.RoadReport], responses=s.NOT_FOUND, summary="Citizen reports on a road, newest first")
def road_reports(request: Request, road_id: str = Path(examples=["RD0048"]), limit: int = Query(20, ge=1, le=100)):
    """Each report with its first photo (by position), if any."""
    one("SELECT 1 FROM roads WHERE road_id = %(r)s", f"road {road_id}", r=road_id)
    rs = rows("SELECT cr.id AS report_id, cr.kind, cr.issue_type, cr.created_at, cr.status, "
              "p.photo_id, p.storage, p.storage_path FROM citizen_reports cr LEFT JOIN LATERAL ("
              " SELECT p.* FROM citizen_report_photos crp JOIN photos p USING (photo_id) "
              " WHERE crp.report_id = cr.id ORDER BY crp.position LIMIT 1) p ON true "
              "WHERE cr.road_id = %(r)s ORDER BY cr.created_at DESC, cr.id DESC LIMIT %(lim)s", r=road_id, lim=limit)
    return [{k: x[k] for k in ("report_id", "kind", "issue_type", "created_at", "status")}
            | {"photo_url": public_url(x["storage"], x["storage_path"], x["photo_id"], request) if x["photo_id"] else None}
            for x in rs]


@router.get("/api/roads/{road_id}/timeline", response_model=list[s.TimelineEvent], responses=s.NOT_FOUND, summary="Connected trail: complaints -> work orders -> accidents -> reports")
def road_timeline(road_id: str = Path(examples=["RD0058"])):
    """View 2 connected trail, chronological."""
    one("SELECT 1 FROM roads WHERE road_id = %(r)s", f"road {road_id}", r=road_id)
    return rows("SELECT * FROM road_timeline WHERE road_id = %(r)s ORDER BY event_at, event_type", r=road_id)


@router.get("/api/flags/{flag_id}", response_model=s.FlagWithReplies, responses=s.NOT_FOUND, summary="One flag with its replies")
def flag(flag_id: str = Path(description="<DETECTOR>:<work_order_id>", examples=["DLP_PAID_TWICE:WO25-01994"])):
    f = one("SELECT * FROM flags WHERE flag_id = %(f)s", f"flag {flag_id}", f=flag_id)
    f["replies"] = rows("SELECT * FROM flag_replies WHERE flag_id = %(f)s ORDER BY created_at", f=flag_id)
    return f


@router.post("/api/flags/{flag_id}/replies", status_code=201, response_model=s.Reply, responses=s.NOT_FOUND, summary="Add Right-of-Reply to a flag")
def add_reply(flag_id: str, req: s.ReplyReq):
    """View 2 Right-of-Reply."""
    one("SELECT 1 FROM flags WHERE flag_id = %(f)s", f"flag {flag_id}", f=flag_id)
    with get_engine().begin() as c:
        r = c.execute(text("INSERT INTO flag_replies (flag_id, author_role, author_name, body) "
                           "VALUES (:f, :role, :name, :body) RETURNING id, flag_id, author_role, author_name, body, created_at"),
                      {"f": flag_id, "role": req.author_role, "name": req.author_name, "body": req.body}).mappings().one()
    return dict(r)


# ── Draft defect notice / RTI (Claude, template fallback) ───────────────────
ID_RE = re.compile(r"\b(?:WO25-\d{5}|RD\d{4}|BMC25-\d{6}|ACC\d{4})\b")
LANG_NAME = {"en": "English", "hi": "Hindi (Devanagari script)", "mr": "Marathi (Devanagari script)"}
SYSTEM = (
    "You draft formal civic documents for the Brihanmumbai Municipal Corporation (BMC) road-repair audit. "
    "doc_type 'defect_notice': a formal BMC defect notice to the contractor, issued through the ward Executive Engineer, "
    "asking them to explain or rectify the flagged bill. doc_type 'rti': a Right to Information Act, 2005 application to "
    "the ward's Public Information Officer asking for the measurement book entries, the bills paid, the Defect Liability "
    "Period (DLP) clause of the original contract, and the inspection report for the work order. "
    "Write in the requested language; Hindi and Marathi must be in Devanagari script. Use a neutral civic tone: describe "
    "issues as 'Needs Explanation' or 'Recoverable under DLP'; never use the words fraud, corrupt, scam or theft, or "
    "accuse anyone. Use ONLY the facts given in the JSON. Do not invent or compute any number, date, name or ID. Cite "
    "the row IDs from cited_row_ids inline, e.g. (WO25-01994). "
    "Output format: the first line is 'TITLE: <title>', then one blank line, then the body as plain text. No markdown."
)


def inr(x):
    """Indian digit grouping: 123456 -> ₹1,23,456."""
    n = round(float(x or 0))
    d = str(abs(n))
    if len(d) > 3:
        d = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", d[:-3]) + "," + d[-3:]
    return ("-" if n < 0 else "") + "₹" + d


TEMPLATES = {
    ("defect_notice", "en"): (
        "Defect notice: {method} on {road_name} ({road_id}), work order {wo}",
        "To: {contractor}\nThrough: Executive Engineer (Roads), Ward {ward}, Brihanmumbai Municipal Corporation\n\n"
        "Subject: Defect notice for work order {wo} on {road_name} ({road_id}), Ward {ward}\n\n"
        "The road audit has flagged work order {wo} as \"{status}\".\n\n"
        "Work: {method}, cost {cost}, completed on {completed}.\n"
        "Finding: {rule}\n"
        "Amount at stake: {at_stake}.\n{dlp_line}\n"
        "You are requested to submit a written explanation and, where the work falls within the Defect Liability Period, "
        "to rectify the defect at your own cost, within 15 days of this notice.\n\n"
        "Evidence rows: {evidence}\n\nExecutive Engineer (Roads), Ward {ward}"),
    ("defect_notice", "hi"): (
        "दोष सूचना: {road_name} ({road_id}) पर {method}, कार्य आदेश {wo}",
        "प्रति: {contractor}\nद्वारा: कार्यकारी अभियंता (सड़क), वार्ड {ward}, बृहन्मुंबई महानगरपालिका\n\n"
        "विषय: {road_name} ({road_id}), वार्ड {ward} पर कार्य आदेश {wo} हेतु दोष सूचना\n\n"
        "सड़क ऑडिट में कार्य आदेश {wo} को \"{status}\" के रूप में चिह्नित किया गया है।\n\n"
        "कार्य: {method}, लागत {cost}, पूर्ण होने की तिथि {completed}।\n"
        "निष्कर्ष: {rule}\n"
        "दांव पर राशि: {at_stake}।\n{dlp_line}\n"
        "आपसे अनुरोध है कि इस सूचना के 15 दिनों के भीतर लिखित स्पष्टीकरण प्रस्तुत करें, और यदि कार्य दोष दायित्व अवधि "
        "(DLP) के अंतर्गत आता है तो अपने खर्च पर दोष का सुधार करें।\n\n"
        "साक्ष्य पंक्तियाँ: {evidence}\n\nकार्यकारी अभियंता (सड़क), वार्ड {ward}"),
    ("defect_notice", "mr"): (
        "दोष सूचना: {road_name} ({road_id}) वरील {method}, कार्यादेश {wo}",
        "प्रति: {contractor}\nमार्फत: कार्यकारी अभियंता (रस्ते), वॉर्ड {ward}, बृहन्मुंबई महानगरपालिका\n\n"
        "विषय: {road_name} ({road_id}), वॉर्ड {ward} वरील कार्यादेश {wo} बाबत दोष सूचना\n\n"
        "रस्ते लेखापरीक्षणात कार्यादेश {wo} \"{status}\" म्हणून नोंदवला गेला आहे.\n\n"
        "काम: {method}, खर्च {cost}, पूर्ण झाल्याची तारीख {completed}.\n"
        "निष्कर्ष: {rule}\n"
        "संबंधित रक्कम: {at_stake}.\n{dlp_line}\n"
        "या सूचनेपासून 15 दिवसांच्या आत लेखी स्पष्टीकरण सादर करावे, आणि काम दोष दायित्व कालावधीत (DLP) येत असल्यास "
        "स्वखर्चाने दोष दुरुस्त करावा, ही विनंती.\n\n"
        "पुरावा नोंदी: {evidence}\n\nकार्यकारी अभियंता (रस्ते), वॉर्ड {ward}"),
    ("rti", "en"): (
        "RTI application: work order {wo} on {road_name} ({road_id})",
        "To: The Public Information Officer, Roads Department, Ward {ward}, Brihanmumbai Municipal Corporation\n\n"
        "Subject: Application under the Right to Information Act, 2005\n\n"
        "Regarding work order {wo} ({method}, cost {cost}, completed on {completed}) by {contractor} on {road_name} "
        "({road_id}), Ward {ward}, which the road audit marks as \"{status}\" with {at_stake} at stake.\n"
        "Finding: {rule}\n{dlp_line}\n"
        "Please provide certified copies of:\n"
        "1. The measurement book entries for work order {wo}.\n"
        "2. All bills raised and payments released for work order {wo}.\n"
        "3. The Defect Liability Period clause of the original contract for {road_id}.\n"
        "4. The inspection / quality-check report for work order {wo}.\n\n"
        "Evidence rows: {evidence}\n\nThe prescribed fee is enclosed."),
    ("rti", "hi"): (
        "सूचना का अधिकार आवेदन: {road_name} ({road_id}) पर कार्य आदेश {wo}",
        "प्रति: जन सूचना अधिकारी, सड़क विभाग, वार्ड {ward}, बृहन्मुंबई महानगरपालिका\n\n"
        "विषय: सूचना का अधिकार अधिनियम, 2005 के अंतर्गत आवेदन\n\n"
        "{road_name} ({road_id}), वार्ड {ward} पर {contractor} द्वारा किए गए कार्य आदेश {wo} ({method}, लागत {cost}, "
        "पूर्ण होने की तिथि {completed}) के संबंध में, जिसे सड़क ऑडिट ने \"{status}\" के रूप में चिह्नित किया है और "
        "जिसमें {at_stake} की राशि दांव पर है।\n"
        "निष्कर्ष: {rule}\n{dlp_line}\n"
        "कृपया निम्नलिखित की प्रमाणित प्रतियाँ उपलब्ध कराएँ:\n"
        "1. कार्य आदेश {wo} की माप पुस्तिका (मेजरमेंट बुक) की प्रविष्टियाँ।\n"
        "2. कार्य आदेश {wo} के सभी बिल और जारी किए गए भुगतान।\n"
        "3. {road_id} के मूल अनुबंध का दोष दायित्व अवधि (DLP) खंड।\n"
        "4. कार्य आदेश {wo} की निरीक्षण / गुणवत्ता जाँच रिपोर्ट।\n\n"
        "साक्ष्य पंक्तियाँ: {evidence}\n\nनिर्धारित शुल्क संलग्न है।"),
    ("rti", "mr"): (
        "माहितीचा अधिकार अर्ज: {road_name} ({road_id}) वरील कार्यादेश {wo}",
        "प्रति: जन माहिती अधिकारी, रस्ते विभाग, वॉर्ड {ward}, बृहन्मुंबई महानगरपालिका\n\n"
        "विषय: माहितीचा अधिकार अधिनियम, 2005 अंतर्गत अर्ज\n\n"
        "{road_name} ({road_id}), वॉर्ड {ward} वरील {contractor} यांनी केलेल्या कार्यादेश {wo} ({method}, खर्च {cost}, "
        "पूर्ण झाल्याची तारीख {completed}) बाबत, ज्याची रस्ते लेखापरीक्षणात \"{status}\" म्हणून नोंद आहे आणि "
        "ज्यात {at_stake} रक्कम संबंधित आहे.\n"
        "निष्कर्ष: {rule}\n{dlp_line}\n"
        "कृपया पुढील कागदपत्रांच्या प्रमाणित प्रती द्याव्यात:\n"
        "1. कार्यादेश {wo} च्या मोजमाप पुस्तिकेतील (मेजरमेंट बुक) नोंदी.\n"
        "2. कार्यादेश {wo} ची सर्व देयके आणि अदा केलेली रक्कम.\n"
        "3. {road_id} च्या मूळ करारातील दोष दायित्व कालावधी (DLP) कलम.\n"
        "4. कार्यादेश {wo} चा तपासणी / गुणवत्ता अहवाल.\n\n"
        "पुरावा नोंदी: {evidence}\n\nविहित शुल्क सोबत जोडले आहे."),
}
DLP_LINE = {"en": "The road is under the Defect Liability Period until {d}.",
            "hi": "यह सड़क {d} तक दोष दायित्व अवधि (DLP) के अंतर्गत है।",
            "mr": "हा रस्ता {d} पर्यंत दोष दायित्व कालावधीत (DLP) आहे."}


def template(doc_type, lang, facts):
    f, road, wo = facts["flag"], facts["road"], facts["work_order"]
    dlp = DLP_LINE[lang].format(d=road["dlp_expires_on"]) + "\n" if road["under_dlp"] and road["dlp_expires_on"] else ""
    title, body = TEMPLATES[(doc_type, lang)]
    v = dict(road_name=road["road_name"], road_id=road["road_id"], ward=road["ward_code"], wo=wo["work_order_id"],
             contractor=wo["contractor_name"], method=wo["repair_method"], cost=inr(wo["cost_inr"]),
             completed=(wo["completed_at"] or "-")[:10], at_stake=inr(f["rupees_at_stake"]), rule=f["rule_text"],
             status=f["status_label"], evidence=", ".join(facts["cited_row_ids"]), dlp_line=dlp)
    return title.format(**v), body.format(**v)


def parse_claude(out, allowed):
    """(title, body) if Claude's text has a TITLE line and cites only known IDs, else None."""
    if not out:
        return None
    head, _, body = out.strip().partition("\n")
    title = head.strip().removeprefix("TITLE:").strip() if head.strip().startswith("TITLE:") else ""
    body = body.strip()
    if not title or not body or set(ID_RE.findall(title + "\n" + body)) - allowed:
        return None
    return title, body


@router.post("/api/draft-notice", response_model=s.DraftNotice, responses=s.NOT_FOUND, summary="Draft a defect notice or RTI for a flag (Claude, template fallback)")
def draft_notice(req: s.DraftNoticeReq):
    """Facts come from the DB; Claude only writes prose. Slow/failed/invalid Claude output -> template."""
    if req.flag_id:
        f = one("SELECT * FROM flags WHERE flag_id = %(f)s", f"flag {req.flag_id}", f=req.flag_id)
    else:
        one("SELECT 1 FROM roads WHERE road_id = %(r)s", f"road {req.road_id}", r=req.road_id)
        f = rows("SELECT * FROM flags WHERE road_id = %(r)s ORDER BY (detector = 'DLP_PAID_TWICE') DESC, tier, "
                 "rupees_at_stake DESC LIMIT 1", r=req.road_id)
        if not f:
            raise HTTPException(404, f"road {req.road_id} has no flags")
        f = f[0]
    road = one("SELECT road_id, road_name, ward_code, under_dlp, dlp_expires_on FROM road_audit WHERE road_id = %(r)s",
               f"road {f['road_id']}", r=f["road_id"])
    road["dlp_expires_on"] = (road["dlp_expires_on"] or "")[:10] or None  # rows() gives an ISO timestamp
    wo = one("SELECT wo.work_order_id, c.contractor_name, wo.repair_method, wo.cost_inr, wo.completed_at, wo.engineer_remark, "
             "COALESCE((SELECT array_agg(cw.complaint_id ORDER BY cw.complaint_id) FROM complaint_work_orders cw "
             "WHERE cw.work_order_id = wo.work_order_id), '{}') AS complaint_ids "
             "FROM work_orders wo JOIN contractors c USING (contractor_id) WHERE wo.work_order_id = %(w)s",
             f"work order {f['work_order_id']}", w=f["work_order_id"])
    replies = rows("SELECT author_role, author_name, body, created_at FROM flag_replies WHERE flag_id = %(f)s "
                   "ORDER BY created_at", f=f["flag_id"])
    cited = list(dict.fromkeys([*f["evidence_row_ids"], f["work_order_id"], f["road_id"]]))
    facts = {"doc_type": req.doc_type, "language": req.language,
             "flag": {k: f[k] for k in ("flag_id", "detector", "tier", "status_label", "rupees_at_stake", "rule_text")}
                     | {"rupees_at_stake_formatted": inr(f["rupees_at_stake"])},
             "road": road, "work_order": wo | {"cost_inr_formatted": inr(wo["cost_inr"])},
             "replies": replies, "cited_row_ids": cited}
    facts_json = json.dumps(facts, ensure_ascii=False, indent=1)
    # ponytail: any ID literally present in the facts (incl. ones inside rule_text/replies) counts as allowed
    allowed = set(cited) | set(wo["complaint_ids"]) | set(ID_RE.findall(facts_json))
    prompt = (f"Draft a {req.doc_type} in {LANG_NAME[req.language]} using only these facts:\n{facts_json}")
    parsed = parse_claude(claude_writer.write(SYSTEM, prompt), allowed)
    title, body = parsed or template(req.doc_type, req.language, facts)
    return {"title": title, "body": body, "cited_row_ids": cited, "flag_id": f["flag_id"], "road_id": f["road_id"],
            "language": req.language, "doc_type": req.doc_type, "generated_by": "claude" if parsed else "template"}
