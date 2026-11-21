"""Citizen/admin auth primitives and the report lifecycle rules (no database)."""
from datetime import datetime, timedelta, timezone

import pytest

from backend import auth
from backend import report_lifecycle as lc

T0 = datetime(2025, 7, 1, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


# ── auth ─────────────────────────────────────────────────────────────────────
def test_password_hash_roundtrip_and_salted():
    h1, h2 = auth.hash_password("correct horse"), auth.hash_password("correct horse")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert auth.verify_password("correct horse", h1)
    assert not auth.verify_password("wrong horse", h1)
    assert not auth.verify_password("x", "garbage") and not auth.verify_password("x", "md5$1$2$3$4$5")


def test_tokens_are_prefixed_random_and_hashed():
    a, b = auth.new_token(auth.CITIZEN_PREFIX), auth.new_token(auth.CITIZEN_PREFIX)
    assert a != b and a.startswith("cit_") and auth.new_token(auth.ADMIN_PREFIX).startswith("adm_")
    assert auth.token_hash(a) == auth.token_hash(a) and len(auth.token_hash(a)) == 64 and auth.token_hash(a) != a


def test_ward_scope_rules():
    admin = {"role": "admin", "ward_codes": []}
    officer = {"role": "ward_officer", "ward_codes": ["K/W"]}
    assert auth.ward_scope(admin) is None and auth.ward_scope(admin, "k-e") == ["K/E"]
    assert auth.ward_scope(officer) == ["K/W"] and auth.ward_scope(officer, "K-W") == ["K/W"]
    with pytest.raises(Exception) as e:
        auth.ward_scope(officer, "A")
    assert e.value.status_code == 403
    auth.require_ward(admin, None)
    with pytest.raises(Exception):
        auth.require_ward(officer, None)  # a report with no ward is admin-only


def test_session_hours_env(monkeypatch):
    monkeypatch.setenv("ADMIN_SESSION_HOURS", "3")
    assert auth.session_hours() == 3
    monkeypatch.setenv("ADMIN_SESSION_HOURS", "abc")
    assert auth.session_hours() == 12


# ── lifecycle ────────────────────────────────────────────────────────────────
def test_open_closed_partition():
    assert lc.OPEN | lc.CLOSED == set(lc.STATUSES) and not lc.OPEN & lc.CLOSED
    assert "reopened" in lc.OPEN and "resolved" in lc.CLOSED


@pytest.mark.parametrize("frm,to,dlp,ok", [
    ("reported", "matched_to_contract", False, True),
    ("reported", "resolved", False, False),
    ("matched_to_contract", "payment_held", True, True),
    ("matched_to_contract", "payment_held", False, False),  # hold only for DLP surface defects
    ("payment_held", "contractor_notified", True, True),
    ("contractor_notified", "resolved", False, True),
    ("contractor_notified", "payment_held", True, False),
    ("resolved", "reopened", False, True),
    ("resolved", "confirmed_fixed", False, False),  # only the citizen confirms
    ("reopened", "contractor_notified", False, True),
    ("confirmed_fixed", "reopened", False, False),
    ("rejected", "matched_to_contract", False, False),
    ("duplicate", "resolved", False, False),
    ("matched_to_contract", "matched_to_contract", False, False),
])
def test_transitions(frm, to, dlp, ok):
    assert (lc.transition_error(frm, to, dlp) is None) is ok


def test_every_open_status_can_be_rejected_or_duplicated():
    for st in lc.OPEN:
        assert {"rejected", "duplicate"} <= set(lc.allowed_next(st, True)), st


def test_transition_error_messages():
    assert "DLP" in lc.transition_error("matched_to_contract", "payment_held", False)
    assert "final status" in lc.transition_error("confirmed_fixed", "resolved", False)


def test_citizen_confirm_targets():
    assert lc.confirm_target("resolved", True) == "confirmed_fixed"
    assert lc.confirm_target("resolved", False) == "reopened"
    assert lc.confirm_target("confirmed_fixed", False) == "reopened"
    assert lc.confirm_target("confirmed_fixed", True) is None
    assert lc.confirm_target("contractor_notified", True) is None


def test_sla_due_at():
    assert lc.sla_due_at(T0, 48) == T0 + timedelta(hours=48)
    due = T0 + timedelta(days=10)
    assert lc.sla_due_at(T0, 48, due) == due  # officer's repair_due_at wins
    assert lc.sla_due_at(T0, None) is None and lc.sla_due_at(None, 24) is None


def _steps(status, events, dlp):
    return {t["step"]: t["status"] for t in lc.tracker(status, T0, events, dlp)}


def test_tracker_new_report():
    st = _steps("matched_to_contract", [{"to_status": "matched_to_contract", "at": T0}], True)
    assert st == {"reported": "done", "matched_to_contract": "current", "payment_held": "pending",
                  "contractor_notified": "pending", "resolved": "pending", "confirmed_fixed": "pending"}


def test_tracker_skips_hold_when_not_dlp_and_shows_timestamps():
    ev = [{"to_status": "matched_to_contract", "at": T0}, {"to_status": "contractor_notified", "at": T0 + timedelta(hours=2)}]
    out = lc.tracker("contractor_notified", T0, ev, False)
    by = {t["step"]: t for t in out}
    assert by["payment_held"]["status"] == "skipped" and by["payment_held"]["at"] is None
    assert by["contractor_notified"]["status"] == "current" and by["contractor_notified"]["at"] == T0 + timedelta(hours=2)
    assert [t["step"] for t in out] == [s for s, _ in lc.STEPS]


def test_tracker_confirmed_fixed_all_done():
    ev = [{"to_status": s, "at": T0} for s in ("matched_to_contract", "payment_held", "contractor_notified",
                                                "resolved", "confirmed_fixed")]
    assert set(_steps("confirmed_fixed", ev, True).values()) == {"done"}


def test_tracker_reopened_goes_back_before_resolution():
    ev = [{"to_status": s, "at": T0} for s in ("matched_to_contract", "contractor_notified", "resolved", "reopened")]
    st = _steps("reopened", ev, False)
    assert st["contractor_notified"] == "current" and st["resolved"] == "pending" and st["confirmed_fixed"] == "pending"


def test_tracker_rejected_stops_remaining_steps():
    ev = [{"to_status": "matched_to_contract", "at": T0}, {"to_status": "rejected", "at": T0}]
    st = _steps("rejected", ev, False)
    assert st["reported"] == st["matched_to_contract"] == "done"
    assert {st[k] for k in ("payment_held", "contractor_notified", "resolved", "confirmed_fixed")} == {"stopped"}
