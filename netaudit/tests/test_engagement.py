import pytest

from netaudit import runner
from netaudit.models import Engagement
from netaudit.data import checklist_template as tmpl


def make_eng():
    return Engagement.create(name="acme-test", client="Acme")


def test_checklist_initialized():
    eng = make_eng()
    total_items = sum(len(p["items"]) for p in tmpl.PHASES)
    assert len(eng.checklist) == total_items
    assert all(v["state"] == "pending" for v in eng.checklist.values())


def test_phase_progress_counts_na_as_done():
    eng = make_eng()
    items = tmpl.build_phase_items()[6]
    for item_id, _ in items:
        eng.set_item(item_id, "na")
    assert eng.phase_complete(6)


def test_roundtrip_serialization():
    eng = make_eng()
    eng.add_finding("Weak TLS", severity="high", host="10.0.0.5", cvss="7.5")
    eng.set_item("p1.1", "done")
    d = eng.to_dict()
    eng2 = Engagement.from_dict(d)
    assert eng2.checklist["p1.1"]["state"] == "done"
    assert eng2.findings[0].title == "Weak TLS"
    assert eng2.scope.in_scope == eng.scope.in_scope


def test_runner_blocked_without_authorization():
    eng = make_eng()
    eng.scope.in_scope.append("192.168.1.0/24")
    with pytest.raises(runner.PreflightError):
        runner.preflight(eng, "host-discovery", "192.168.1.10")


def _grant_phase0(eng):
    eng.authorization.signed = True
    eng.authorization.authorizing_officer = "Jane Owner"
    eng.authorization.letter_path = "/secure/letter.pdf"
    for item_id, _ in tmpl.build_phase_items()[0]:
        eng.set_item(item_id, "done")


def test_runner_blocked_out_of_scope():
    eng = make_eng()
    _grant_phase0(eng)
    eng.scope.in_scope.append("192.168.1.0/24")
    with pytest.raises(runner.PreflightError):
        runner.preflight(eng, "host-discovery", "10.9.9.9")


def test_runner_allows_in_scope_after_auth():
    eng = make_eng()
    _grant_phase0(eng)
    eng.scope.in_scope.append("192.168.1.0/24")
    argv = runner.preflight(eng, "host-discovery", "192.168.1.10")
    assert argv == ["nmap", "-sn", "192.168.1.10"]


def test_dry_run_does_not_execute():
    eng = make_eng()
    _grant_phase0(eng)
    eng.scope.in_scope.append("192.168.1.0/24")
    res = runner.run(eng, "host-discovery", "192.168.1.10", execute=False)
    assert res["executed"] is False
