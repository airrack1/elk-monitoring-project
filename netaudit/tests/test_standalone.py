"""Tests for the offline single-file web app (`web_static/standalone.html`).

The page re-implements scope checking, gating and report rendering in
JavaScript so it can run with no server. That duplication is only safe if it
stays behaviourally identical to the Python it mirrors, so these tests:

  1. fail if the generated file is stale relative to the Python template,
  2. verify the embedded data matches the checklist/runner source of truth,
  3. run the JS against Python and require identical answers (needs node).
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from netaudit import report
from netaudit.data import checklist_template as tmpl
from netaudit.models import Engagement
from netaudit.runner import RUNNERS
from netaudit.scope import Scope
from netaudit.tools import build_standalone

STANDALONE = Path(build_standalone.OUT)
NODE = shutil.which("node")


def embedded_data() -> dict:
    html = STANDALONE.read_text(encoding="utf-8")
    m = re.search(r"^const DATA = (\{.*?^\});$", html, re.S | re.M)
    assert m, "could not locate the embedded DATA block"
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_standalone_is_committed():
    assert STANDALONE.is_file(), "run `python -m netaudit.tools.build_standalone`"


def test_standalone_is_up_to_date():
    """Editing the checklist without rebuilding must fail here, not in the field."""
    assert build_standalone.main(["--check"]) == 0


def test_embedded_template_matches_python():
    data = embedded_data()
    assert data["template"]["version"] == tmpl.TEMPLATE_VERSION
    items = tmpl.build_phase_items()
    assert len(data["template"]["phases"]) == len(tmpl.PHASES)
    for phase, src in zip(data["template"]["phases"], tmpl.PHASES):
        assert phase["number"] == src["number"]
        assert phase["name"] == src["name"]
        assert phase["optional"] == src.get("optional", False)
        assert [i["id"] for i in phase["items"]] == [i for i, _ in items[src["number"]]]
        assert [i["text"] for i in phase["items"]] == [t for _, t in items[src["number"]]]
    assert [q["text"] for q in data["template"]["qa"]] == list(tmpl.FINAL_QA)


def test_embedded_runners_match_allowlist():
    """The phone must not offer a runner the CLI wouldn't allow."""
    data = embedded_data()
    assert {r["name"] for r in data["runners"]} == set(RUNNERS)
    for r in data["runners"]:
        spec = RUNNERS[r["name"]]
        assert r["binary"] == spec["binary"]
        assert r["args"] == spec["args"]
        assert r["phase"] == spec["phase"]
    # Host-specific state must not be baked into a file served to a browser.
    assert all("installed" not in r for r in data["runners"])


def test_no_external_resources():
    """The page must work offline / under a strict CSP: nothing fetched."""
    html = STANDALONE.read_text(encoding="utf-8")
    body = re.sub(r'href="data:[^"]*"', "", html)
    assert "http://" not in body.replace("http://www.w3.org", "")
    assert "https://" not in body
    for bad in ("fetch(", "XMLHttpRequest", "WebSocket", "importScripts"):
        assert bad not in body, f"standalone page must not use {bad}"


# --------------------------------------------------------------------------
# behavioural parity with the Python implementation
# --------------------------------------------------------------------------

def _js_core(tmp_path: Path) -> Path:
    """Pull the non-UI half of the page's script out into a CommonJS module."""
    html = STANDALONE.read_text(encoding="utf-8")
    # Start at the data block so the browser-only preamble (which touches
    # `document`) stays out of the node module.
    m = re.search(r"^(const DATA = \{.*?)/\* =+ UI", html, re.S | re.M)
    assert m, "could not locate the core script section"
    core = m.group(1) + (
        "\nmodule.exports={scopeCheck,markdownReport,phaseProgress,"
        "phaseComplete,authGranted,preflight,buildCommand,shellQuote};\n"
    )
    path = tmp_path / "core.js"
    path.write_text(core, encoding="utf-8")
    return path


def _populated_engagement() -> Engagement:
    eng = Engagement.create(name="acme-q2", client="Acme Corp", sow_ref="SOW-2026-014",
                            testing_window="2026-06-14 to 2026-06-20")
    eng.scope.in_scope = ["192.168.10.0/24", "dc01.acme.local", "10.0.0.1-20"]
    eng.scope.exclusions = ["192.168.10.1", "192.168.10.240/28"]
    eng.authorization.signed = True
    eng.authorization.authorizing_officer = "Jane Owner"
    eng.authorization.letter_path = "/secure/acme-auth.pdf"
    for i in range(1, len(tmpl.PHASES[0]["items"]) + 1):
        eng.set_item(f"p0.{i}", "done")
    eng.set_item("p1.1", "done")
    eng.set_item("p1.2", "in_progress")
    eng.set_item("p1.3", "na")
    eng.add_finding("Telnet exposed", severity="high", host="192.168.10.5", cvss="7.3",
                    business_impact="Cleartext admin creds.", remediation="Disable telnet.")
    eng.add_finding("SMB signing not required", severity="critical", host="192.168.10.10")
    eng.add_finding("Banner discloses version", severity="info", host="192.168.10.7")
    eng.add_evidence("command", "nmap -sn sweep", path="/ev/host.txt")
    eng.qa["qa.1"] = True
    return eng


SCOPE_TARGETS = [
    "192.168.10.50", "192.168.10.1", "192.168.10.241", "192.168.11.1",
    "10.0.0.1", "10.0.0.20", "10.0.0.21", "8.8.8.8", "0.0.0.0",
    "dc01.acme.local", "DC01.ACME.LOCAL", "unknown.host",
    # Leading zeros are NOT a valid address for Python's ipaddress module; the
    # JS must agree, or the phone would allow a target the CLI blocks.
    "192.168.010.50", "192.168.10", "999.1.1.1", "",
]


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_js_matches_python(tmp_path):
    eng = _populated_engagement()
    core = _js_core(tmp_path)

    cases = []
    for target in SCOPE_TARGETS:
        res = eng.scope.check(target)
        cases.append({"target": target, "allowed": res.allowed, "reason": res.reason})

    fixture = {
        "scope": eng.scope.to_dict(),
        "cases": cases,
        "engagement": eng.to_dict(),
        "report": report.markdown_report(eng),
        "progress": {str(p["number"]): list(eng.phase_progress(p["number"]))
                     for p in tmpl.PHASES},
    }
    (tmp_path / "fixture.json").write_text(json.dumps(fixture), encoding="utf-8")

    (tmp_path / "run.js").write_text("""
const fs=require("fs"), core=require("./core.js");
const f=JSON.parse(fs.readFileSync(__dirname+"/fixture.json","utf8"));
const problems=[];
for(const c of f.cases){
  const r=core.scopeCheck({scope:f.scope},c.target);
  if(r.allowed!==c.allowed) problems.push(`scope ${JSON.stringify(c.target)}: py=${c.allowed} js=${r.allowed}`);
  else if(r.reason!==c.reason) problems.push(`reason ${JSON.stringify(c.target)}: py=${c.reason} js=${r.reason}`);
}
for(const [n,exp] of Object.entries(f.progress)){
  const got=core.phaseProgress(f.engagement,parseInt(n,10));
  if(JSON.stringify(got)!==JSON.stringify(exp)) problems.push(`progress P${n}: py=${JSON.stringify(exp)} js=${JSON.stringify(got)}`);
}
const md=core.markdownReport(f.engagement);
if(md!==f.report){
  const a=f.report.split("\\n"), b=md.split("\\n");
  for(let i=0;i<Math.max(a.length,b.length);i++)
    if(a[i]!==b[i]){ problems.push(`report line ${i+1}: py=${JSON.stringify(a[i])} js=${JSON.stringify(b[i])}`); break; }
}
console.log(JSON.stringify(problems));
""", encoding="utf-8")

    out = subprocess.run([NODE, str(tmp_path / "run.js")], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    problems = json.loads(out.stdout.strip().splitlines()[-1])
    assert problems == [], "\n".join(problems)


@pytest.mark.skipif(NODE is None, reason="node not available")
def test_js_runner_gating_matches_python(tmp_path):
    """The three blocking conditions must fire in the browser exactly as in the CLI."""
    from netaudit import runner as pyrunner

    core = _js_core(tmp_path)
    eng = _populated_engagement()

    scenarios = {}
    # (a) fully gated-open engagement -> command built
    scenarios["ok"] = eng.to_dict()
    # (b) authorization revoked
    blocked_auth = _populated_engagement()
    blocked_auth.authorization.signed = False
    scenarios["no_auth"] = blocked_auth.to_dict()
    # (c) phase 0 incomplete
    blocked_p0 = _populated_engagement()
    blocked_p0.set_item("p0.1", "pending")
    scenarios["no_p0"] = blocked_p0.to_dict()

    expected = {}
    for key, data in scenarios.items():
        e = Engagement.from_dict(data)
        for target in ("192.168.10.50", "192.168.10.1", "8.8.8.8"):
            try:
                argv = pyrunner.preflight(e, "host-discovery", target)
                expected[f"{key}|{target}"] = {"ok": True, "argv": argv}
            except pyrunner.PreflightError as exc:
                expected[f"{key}|{target}"] = {"ok": False, "error": str(exc)}

    (tmp_path / "gate.json").write_text(
        json.dumps({"scenarios": scenarios, "expected": expected}), encoding="utf-8")
    (tmp_path / "gate.js").write_text("""
const fs=require("fs"), core=require("./core.js");
const f=JSON.parse(fs.readFileSync(__dirname+"/gate.json","utf8"));
const problems=[];
for(const [key,exp] of Object.entries(f.expected)){
  const [scenario,target]=key.split("|");
  let got;
  try{ got={ok:true,argv:core.preflight(f.scenarios[scenario],"host-discovery",target)}; }
  catch(e){ got={ok:false,error:e.message}; }
  if(got.ok!==exp.ok) problems.push(`${key}: py.ok=${exp.ok} js.ok=${got.ok} (${got.error||""})`);
  else if(exp.ok && JSON.stringify(got.argv)!==JSON.stringify(exp.argv))
    problems.push(`${key}: argv py=${JSON.stringify(exp.argv)} js=${JSON.stringify(got.argv)}`);
  else if(!exp.ok && got.error!==exp.error)
    problems.push(`${key}:\\n  py=${exp.error}\\n  js=${got.error}`);
}
console.log(JSON.stringify(problems));
""", encoding="utf-8")

    out = subprocess.run([NODE, str(tmp_path / "gate.js")], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    problems = json.loads(out.stdout.strip().splitlines()[-1])
    assert problems == [], "\n".join(problems)
