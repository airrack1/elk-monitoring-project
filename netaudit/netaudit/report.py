"""Report + status rendering (Markdown)."""

from __future__ import annotations

from typing import List

from .data import checklist_template as tmpl
from .models import Engagement

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_BAR_WIDTH = 24


def _bar(percent: float) -> str:
    filled = int(round(_BAR_WIDTH * percent / 100.0))
    return "[" + "#" * filled + "-" * (_BAR_WIDTH - filled) + f"] {percent:5.1f}%"


def status(eng: Engagement) -> str:
    lines: List[str] = []
    lines.append(f"Engagement : {eng.name}  ({eng.id})")
    lines.append(f"Client     : {eng.client or '-'}")
    lines.append(f"SOW ref    : {eng.sow_ref or '-'}")
    auth = "GRANTED" if eng.authorization.granted else "NOT GRANTED"
    lines.append(f"Authorized : {auth}")
    lines.append(f"In-scope   : {', '.join(eng.scope.in_scope) or '(none set)'}")
    if eng.scope.exclusions:
        lines.append(f"Exclusions : {', '.join(eng.scope.exclusions)}")
    lines.append("")
    lines.append("Phase progress:")
    for phase in tmpl.PHASES:
        done, total, pct = eng.phase_progress(phase["number"])
        opt = " (optional)" if phase.get("optional") else ""
        lines.append(f"  P{phase['number']:<2} {phase['name'][:34]:<34} {_bar(pct)} {done}/{total}{opt}")
    qa_done = sum(1 for v in eng.qa.values() if v)
    lines.append(f"\nFinal QA   : {qa_done}/{len(eng.qa)} checks complete")
    lines.append(f"Findings   : {len(eng.findings)}  |  Evidence items: {len(eng.evidence)}")
    return "\n".join(lines)


def checklist_view(eng: Engagement, phase_number: int) -> str:
    phase = next((p for p in tmpl.PHASES if p["number"] == phase_number), None)
    if phase is None:
        return f"No such phase: {phase_number}"
    glyph = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "na": "[-]"}
    lines = [f"Phase {phase['number']} — {phase['name']}", f"  {phase['intent']}", ""]
    for item_id, text in tmpl.build_phase_items()[phase_number]:
        st = eng.checklist.get(item_id, {})
        mark = glyph.get(st.get("state", "pending"), "[ ]")
        note = f"  // {st['note']}" if st.get("note") else ""
        lines.append(f"  {mark} {item_id:<7} {text}{note}")
    lines.append("")
    lines.append("Tools: " + ", ".join(phase["tools"]))
    return "\n".join(lines)


def markdown_report(eng: Engagement) -> str:
    md: List[str] = []
    md.append(f"# Network Security Audit Report — {eng.client or eng.name}")
    md.append("")
    md.append(f"- **Engagement:** {eng.name}")
    md.append(f"- **Client:** {eng.client or '_________'}")
    md.append(f"- **SOW ref:** {eng.sow_ref or '_________'}")
    md.append(f"- **Lead Auditor:** {eng.lead_auditor}")
    md.append(f"- **Testing window:** {eng.testing_window or '_________'}")
    md.append(f"- **Authorization:** {'On file' if eng.authorization.granted else 'NOT ON FILE'}"
              + (f" (officer: {eng.authorization.authorizing_officer})" if eng.authorization.authorizing_officer else ""))
    md.append("")

    # Executive summary scaffold
    counts = {s: 0 for s in SEV_ORDER}
    for f in eng.findings:
        if not f.false_positive:
            counts[f.severity] = counts.get(f.severity, 0) + 1
    md.append("## Executive Summary")
    md.append("")
    md.append("> _Write the non-technical, risk-focused summary here._")
    md.append("")
    md.append("| Severity | Count |")
    md.append("|----------|-------|")
    for sev in ["critical", "high", "medium", "low", "info"]:
        md.append(f"| {sev.title()} | {counts.get(sev, 0)} |")
    md.append("")

    # Scope
    md.append("## Scope")
    md.append("")
    md.append("**In scope:** " + (", ".join(eng.scope.in_scope) or "_none recorded_"))
    md.append("")
    md.append("**Explicit exclusions:** " + (", ".join(eng.scope.exclusions) or "_none_"))
    md.append("")

    # Findings
    md.append("## Technical Findings")
    md.append("")
    active = [f for f in eng.findings if not f.false_positive]
    if not active:
        md.append("_No findings recorded yet._")
        md.append("")
    for f in sorted(active, key=lambda x: SEV_ORDER.get(x.severity, 9)):
        md.append(f"### [{f.severity.upper()}] {f.title}")
        md.append("")
        if f.host:
            md.append(f"- **Affected host:** {f.host}")
        if f.cvss:
            md.append(f"- **CVSS:** {f.cvss}")
        if f.phase is not None:
            md.append(f"- **Discovered in phase:** {f.phase}")
        md.append("")
        md.append("**Description**")
        md.append("")
        md.append(f.description or "_TODO_")
        md.append("")
        md.append("**Business impact**")
        md.append("")
        md.append(f.business_impact or "_TODO_")
        md.append("")
        md.append("**Remediation**")
        md.append("")
        md.append(f.remediation or "_TODO_")
        md.append("")
        if f.evidence_refs:
            md.append("**Evidence:** " + ", ".join(f.evidence_refs))
            md.append("")

    # Coverage
    md.append("## Checklist Coverage")
    md.append("")
    md.append("| Phase | Name | Complete |")
    md.append("|-------|------|----------|")
    for phase in tmpl.PHASES:
        done, total, pct = eng.phase_progress(phase["number"])
        md.append(f"| {phase['number']} | {phase['name']} | {done}/{total} ({pct}%) |")
    md.append("")

    # QA gate
    md.append("## Final QA Recheck")
    md.append("")
    for i, text in enumerate(tmpl.FINAL_QA, start=1):
        mark = "x" if eng.qa.get(f"qa.{i}") else " "
        md.append(f"- [{mark}] {text}")
    md.append("")

    # Evidence index
    md.append("## Evidence Index")
    md.append("")
    if eng.evidence:
        md.append("| ID | Kind | Summary | Path |")
        md.append("|----|------|---------|------|")
        for e in eng.evidence:
            md.append(f"| {e.id} | {e.kind} | {e.summary} | {e.path or '-'} |")
    else:
        md.append("_No evidence recorded yet._")
    md.append("")

    return "\n".join(md)
