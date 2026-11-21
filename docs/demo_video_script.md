# MARG: final 2:00 demo video

**File:** `assets/video/marg_demo.mp4` (1280×720, 30 fps, H.264 + AAC, exactly 2:00).
**Rebuild:**
1. Start `npm run dev` with the API reachable.
2. Run `python frontend/scripts/video_capture.py`. This creates one "FRONTEND TEST" report.
3. Run `python frontend/scripts/video_build.py`.

Every frame is a real screen from the app on live data. Captions are burned in, in English. The music is the brand animation's own track, looped under the video.

| Time | Scene | On screen (caption) |
|---|---|---|
| 0:00 | Brand animation | The MARG milestone forms |
| 0:06 | Title | Every monsoon, Mumbai spends crores fixing the same roads. |
| 0:12 | Positioning | MARG: one tool for the whole money trail. The six ideas listed |
| 0:20 | Phone: Ask | A Hinglish question, answered by Claude in plain language from the records |
| 0:29 | Phone: Report step 1 | Broken again? Report it in four steps |
| 0:35 | Phone: Review | Check it, then send |
| 0:39 | Phone: Tracker | Matched to the contract, then tracked |
| 0:46 | Phone: My reports | Every report, its status, its impact; email and password sign-in |
| 0:53 | Desktop: Road receipt | Kurla Andheri Road: ₹30.5L billed across 35 repair jobs |
| 1:00 | Desktop: Proof trail | Complaint to repair to failure, connected |
| 1:05 | Desktop: Defect notice | One click: a defect notice drafted by Claude, citing work orders |
| 1:13 | Desktop: City audit | ₹13.43 Cr spent, ₹60.3L billed under warranty, 527 bills need explanation |
| 1:21 | Desktop: Flagged bills | The repair auditor, bill by bill |
| 1:26 | Desktop: Contractors | Judged fairly against rain, tides and roads |
| 1:34 | Desktop: Next rupee | Warranty roads cost ₹0; budget goes where it avoids most harm |
| 1:42 | Phone: Ward office | Officers move each report forward; the citizen sees every step |
| 1:49 | Phone: Flags awaiting reply | Every flag answered on the record |
| 1:54 | Close | Where did the money go? Did the fix last? Where should the next rupee go? |

## Google form: choose "Custom", covering all six ideas

| Option | What MARG has | Status |
|---|---|---|
| Ward Money Trail | Budget vs spend per ward, ₹ billed under warranty, ward map, flagged bills per ward | **Partial.** The per-ward split by contractor and the ₹ spent on fixes that failed within 30 days are built in the UI, but they wait on `GET /api/wards/{ward}/money-trail` ("Data coming in"). The city-level failed-fix count (611) is live. |
| Repair Auditor | Five deterministic detectors: warranty (DLP), rate card, overlapping work orders (double billing), rain-day work, repeat bill with no complaint. Evidence rows, right of reply | **Done.** Missed SLAs show per repair and per contractor, but they are not a separate flag type. |
| Contractor Scorecard | Failure and SLA rates against expected for rain, tides, roads and method; ranges; drivers; cost against rate card; volume | **Done** |
| Next Rupee Planner | Per-ward budget slider re-solved on the server, ₹0 warranty bucket, items ranked by harm avoided, recommended durable method | **Done** (per ward) |
| Complaint to Work Order Linker | Complaints linked to work orders on every road timeline; Hinglish and Devanagari lookup; Claude parses free text; new reports carry `duplicate_of` | **Mostly.** Bulk complaint de-duplication is done in the backend pipeline; the UI shows the links, not a de-dup console. |
| Citizen Accountability Bot | "Ask in your own words": Claude answers what happened, with work order, contractor, cost, SLA and warranty. Report tracker and My reports | **Done** |

Suggested custom description: "MARG, a pre-payment audit gate and public rupee receipt for monsoon road repairs. It covers all six ideas in one app: ward money trail, repair auditor, fair contractor scorecard, next-rupee planner, complaint-to-work-order linking, and a citizen accountability bot, plus citizen reporting with a tracker and a ward-office dashboard. Code computes every number; Claude explains, drafts notices and answers citizens."

## Before submitting

- Delete the "FRONTEND TEST" reports (ids 6 and up, including 17 from the final capture).
- The data is synthetic. The photo step previews but does not upload yet. Email and password sign-in and the ward office actions show "Data coming in" until the backend ships `/api/auth/*` and `/api/admin/*`.
