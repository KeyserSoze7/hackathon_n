"""Citizen report lifecycle: statuses, allowed transitions, SLA due time and the tracker steps.
Pure functions (no DB) so the rules are unit-tested and shared by the citizen and admin routes.

    reported -> matched_to_contract -> payment_held (DLP surface defect only) -> contractor_notified
             -> resolved -> confirmed_fixed | reopened
    rejected (rejection_reason) / duplicate (duplicate_of) from any open status.
A new report stops at matched_to_contract (or reported if no road matched); officers move it on.
"""
from datetime import datetime, timedelta
from typing import Optional

STATUSES = ("reported", "matched_to_contract", "payment_held", "contractor_notified",
            "resolved", "confirmed_fixed", "reopened", "rejected", "duplicate")
CLOSED = frozenset({"resolved", "confirmed_fixed", "rejected", "duplicate"})
OPEN = frozenset(STATUSES) - CLOSED
RESOLVED = frozenset({"resolved", "confirmed_fixed"})

# Officer/admin transitions (PATCH /api/admin/reports/{id}). payment_held additionally needs a DLP surface defect.
TRANSITIONS = {
    "reported": ("matched_to_contract", "rejected", "duplicate"),
    "matched_to_contract": ("payment_held", "contractor_notified", "resolved", "rejected", "duplicate"),
    "payment_held": ("contractor_notified", "resolved", "rejected", "duplicate"),
    "contractor_notified": ("resolved", "rejected", "duplicate"),
    "reopened": ("payment_held", "contractor_notified", "resolved", "rejected", "duplicate"),
    "resolved": ("reopened",),
    "confirmed_fixed": (),
    "rejected": (),
    "duplicate": (),
}

# Citizen confirmation (POST /api/citizen-reports/{id}/confirm): fixed -> {from status: to status}.
CONFIRM = {True: {"resolved": "confirmed_fixed"},
           False: {"resolved": "reopened", "confirmed_fixed": "reopened"}}

STEPS = (("reported", "Reported"), ("matched_to_contract", "Matched to contract"),
         ("payment_held", "Payment held (DLP)"), ("contractor_notified", "Contractor notified"),
         ("resolved", "Resolved by ward office"), ("confirmed_fixed", "Confirmed fixed by citizen"))
STEP_INDEX = {s: i for i, (s, _) in enumerate(STEPS)}


def allowed_next(status: str, dlp_surface: bool) -> list[str]:
    return [t for t in TRANSITIONS.get(status, ()) if t != "payment_held" or dlp_surface]


def transition_error(frm: str, to: str, dlp_surface: bool) -> Optional[str]:
    """None if frm -> to is allowed for an officer, else a message listing what is allowed."""
    if to == frm:
        return f"report is already {to}"
    nxt = allowed_next(frm, dlp_surface)
    if to in nxt:
        return None
    if to == "payment_held" and to in TRANSITIONS.get(frm, ()):
        return "payment_held is only for a surface defect (pothole / broken paver) on a road under DLP"
    return f"cannot move a {frm} report to {to}; allowed: {', '.join(nxt) or 'none (final status)'}"


def confirm_target(status: str, fixed: bool) -> Optional[str]:
    return CONFIRM[fixed].get(status)


def sla_due_at(created_at: Optional[datetime], sla_hours: Optional[int],
               repair_due_at: Optional[datetime] = None) -> Optional[datetime]:
    """repair_due_at (set by an officer) wins; else created_at + the issue type's typical SLA hours."""
    if repair_due_at is not None:
        return repair_due_at
    if created_at is None or sla_hours is None:
        return None
    return created_at + timedelta(hours=int(sla_hours))


def tracker(status: str, created_at, events: list[dict], dlp_surface: bool,
            status_updated_at=None) -> list[dict]:
    """Tracker steps {step, label, status, at}; step status is done | current | pending | skipped | stopped.

    events: [{"to_status", "at"}] in time order. The payment hold step is `skipped` when the report is not a DLP
    surface defect and was never held. Rejected/duplicate reports keep the steps they reached (`done`) and the
    rest are `stopped`. A reopened report goes back to the furthest pre-resolution step it reached."""
    reached: dict[str, object] = {"reported": created_at}
    for e in events:
        if e.get("to_status") in STEP_INDEX:
            reached[e["to_status"]] = e["at"]  # latest wins
    if status in STEP_INDEX:
        cur = STEP_INDEX[status]
        reached.setdefault(status, status_updated_at or created_at)
    elif status == "reopened":
        cur = max([STEP_INDEX[s] for s in reached if STEP_INDEX[s] < STEP_INDEX["resolved"]], default=0)
    else:  # rejected / duplicate
        cur = None
    out = []
    for i, (step, label) in enumerate(STEPS):
        hold_skipped = step == "payment_held" and "payment_held" not in reached and not dlp_surface
        if cur is None:
            st = "done" if step in reached else "stopped"
        elif hold_skipped and i != cur:
            st = "skipped"
        elif i < cur:
            st = "done" if step in reached or step == "reported" else "skipped"
        elif i == cur:
            st = "done" if step == "confirmed_fixed" else "current"
        else:
            st = "pending"
        if status == "reopened" and step in ("resolved", "confirmed_fixed"):
            st = "pending"
        out.append({"step": step, "label": label, "status": st,
                    "at": reached.get(step) if st in ("done", "current") else None})
    return out
