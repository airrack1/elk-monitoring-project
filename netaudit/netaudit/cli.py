"""netaudit command-line interface.

Run `netaudit --help` or `python -m netaudit --help`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, report, runner, storage
from .data import checklist_template as tmpl
from .models import Engagement
from .scope import Scope

# ---------------------------------------------------------------------------
# "current engagement" convenience pointer
# ---------------------------------------------------------------------------

def _current_file() -> Path:
    return storage.workspace_dir() / "current"


def _set_current(eng_id: str) -> None:
    f = _current_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(eng_id, encoding="utf-8")


def _resolve(arg_engagement: str | None) -> Engagement:
    target = arg_engagement
    if not target and _current_file().exists():
        target = _current_file().read_text(encoding="utf-8").strip()
    if not target:
        raise SystemExit("No engagement selected. Pass -e <id|name> or run `netaudit use <id>`.")
    return storage.load(target)


def _ok(msg: str) -> None:
    print(msg)


# ---------------------------------------------------------------------------
# command handlers
# ---------------------------------------------------------------------------

def cmd_new(args) -> None:
    eng = Engagement.create(
        name=args.name,
        client=args.client or "",
        sow_ref=args.sow or "",
        lead_auditor=args.auditor or "Aaryon",
        testing_window=args.window or "",
    )
    storage.save(eng)
    _set_current(eng.id)
    _ok(f"Created engagement {eng.id} ('{eng.name}') and set as current.")
    _ok("Next: record authorization (`netaudit authorize ...`) and scope (`netaudit scope add ...`).")


def cmd_list(args) -> None:
    rows = storage.list_all()
    if not rows:
        _ok("No engagements yet. Create one with `netaudit new <name>`.")
        return
    for d in rows:
        auth = "AUTH" if (d.get("authorization", {}) or {}).get("signed") else "----"
        _ok(f"{d['id']}  [{auth}]  {d['name']}  (client: {d.get('client') or '-'})")


def cmd_use(args) -> None:
    eng = storage.load(args.engagement)
    _set_current(eng.id)
    _ok(f"Current engagement -> {eng.id} ('{eng.name}')")


def cmd_status(args) -> None:
    eng = _resolve(args.engagement)
    _ok(report.status(eng))


def cmd_authorize(args) -> None:
    eng = _resolve(args.engagement)
    a = eng.authorization
    if args.officer:
        a.authorizing_officer = args.officer
    if args.date:
        a.signed_date = args.date
    if args.letter:
        a.letter_path = args.letter
    if args.note:
        a.notes = args.note
    if args.grant:
        a.signed = True
    if args.revoke:
        a.signed = False
    eng.log("authorization.update", f"granted={a.granted}")
    storage.save(eng)
    state = "GRANTED" if a.granted else "NOT granted (need signed + officer + letter path)"
    _ok(f"Authorization: {state}")
    if not a.granted:
        missing = []
        if not a.signed:
            missing.append("--grant (signed)")
        if not a.authorizing_officer:
            missing.append("--officer")
        if not a.letter_path:
            missing.append("--letter")
        _ok("Missing: " + ", ".join(missing))


def cmd_scope(args) -> None:
    eng = _resolve(args.engagement)
    if args.scope_action == "show":
        _ok("In-scope:   " + (", ".join(eng.scope.in_scope) or "(none)"))
        _ok("Exclusions: " + (", ".join(eng.scope.exclusions) or "(none)"))
        return
    if args.scope_action == "add":
        for t in args.targets:
            if t not in eng.scope.in_scope:
                eng.scope.in_scope.append(t)
        eng.log("scope.add", ", ".join(args.targets))
        storage.save(eng)
        _ok(f"Added {len(args.targets)} target(s) to in-scope.")
        return
    if args.scope_action == "exclude":
        for t in args.targets:
            if t not in eng.scope.exclusions:
                eng.scope.exclusions.append(t)
        eng.log("scope.exclude", ", ".join(args.targets))
        storage.save(eng)
        _ok(f"Added {len(args.targets)} exclusion(s).")
        return
    if args.scope_action == "check":
        res = eng.scope.check(args.targets[0])
        _ok(("ALLOWED: " if res.allowed else "BLOCKED: ") + res.reason)
        return


def cmd_phase(args) -> None:
    eng = _resolve(args.engagement)
    _ok(report.checklist_view(eng, args.number))


def cmd_check(args) -> None:
    eng = _resolve(args.engagement)
    eng.set_item(args.item_id, args.state, note=args.note or "")
    storage.save(eng)
    _ok(f"{args.item_id} -> {args.state}")


def cmd_finding(args) -> None:
    eng = _resolve(args.engagement)
    if args.finding_action == "list":
        if not eng.findings:
            _ok("No findings.")
        for f in eng.findings:
            fp = " (FP)" if f.false_positive else ""
            _ok(f"{f.id}  [{f.severity.upper():<8}] {f.title}{fp}  host={f.host or '-'} cvss={f.cvss or '-'}")
        return
    if args.finding_action == "add":
        f = eng.add_finding(
            args.title,
            severity=args.severity,
            host=args.host or "",
            phase=args.phase,
            description=args.desc or "",
            cvss=args.cvss or "",
            business_impact=args.impact or "",
            remediation=args.remediation or "",
        )
        storage.save(eng)
        _ok(f"Added finding {f.id} [{f.severity}] {f.title}")


def cmd_evidence(args) -> None:
    eng = _resolve(args.engagement)
    if args.evidence_action == "list":
        if not eng.evidence:
            _ok("No evidence.")
        for e in eng.evidence:
            _ok(f"{e.id}  {e.kind:<10} {e.summary}  path={e.path or '-'}")
        return
    if args.evidence_action == "add":
        e = eng.add_evidence(args.kind, args.summary, path=args.path or "", item_id=args.item or "")
        storage.save(eng)
        _ok(f"Added evidence {e.id}")


def cmd_qa(args) -> None:
    eng = _resolve(args.engagement)
    if args.qa_action == "show":
        for i, text in enumerate(tmpl.FINAL_QA, start=1):
            mark = "x" if eng.qa.get(f"qa.{i}") else " "
            _ok(f"[{mark}] qa.{i}  {text}")
        return
    if args.qa_action == "set":
        eng.qa[args.qa_id] = (args.value == "true")
        eng.log("qa.update", f"{args.qa_id}={args.value}")
        storage.save(eng)
        _ok(f"{args.qa_id} -> {args.value}")


def cmd_tools(args) -> None:
    import shutil
    _ok("Master tool inventory (installed check via PATH):\n")
    for group, tools in tmpl.TOOL_INVENTORY.items():
        _ok(group + ":")
        for t in tools:
            present = shutil.which(t) is not None
            _ok(f"  [{'OK ' if present else 'MISS'}] {t}")
        _ok("")


def cmd_run(args) -> None:
    if args.list:
        _ok("Scope-guarded runners (discovery / enumeration / read-only only):\n")
        for r in runner.list_runners():
            inst = "OK  " if r["installed"] else "MISS"
            _ok(f"  [{inst}] {r['name']:<14} P{r['phase']}  {r['desc']}")
        _ok("\nExploitation / cracking / brute-force are intentionally manual (not here).")
        return
    if not args.runner or not args.target:
        raise SystemExit("Usage: netaudit run <runner> <target> [--execute]  (or --list)")
    eng = _resolve(args.engagement)
    try:
        result = runner.run(eng, args.runner, args.target, execute=args.execute, timeout=args.timeout)
    except runner.PreflightError as exc:
        storage.save(eng)  # persist the dry-run/block log entry
        raise SystemExit(str(exc))
    storage.save(eng)
    if result["executed"]:
        _ok(f"Ran: {result['command']}")
        _ok(f"  rc={result['return_code']}  evidence={result['evidence_id']}")
        _ok(f"  output: {result['output_path']}")
    else:
        _ok("DRY RUN (no command executed). Add --execute to run for real.")
        _ok(f"  would run: {result['command']}")


def cmd_report(args) -> None:
    eng = _resolve(args.engagement)
    md = report.markdown_report(eng)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        _ok(f"Wrote report to {args.out}")
    else:
        _ok(md)


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="netaudit",
        description="Scope-aware engagement workflow automation for network security audits.",
    )
    p.add_argument("--version", action="version", version=f"netaudit {__version__}")
    p.add_argument("-e", "--engagement", help="Engagement id or name (defaults to current).")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("new", help="Create a new engagement.")
    sp.add_argument("name")
    sp.add_argument("--client")
    sp.add_argument("--sow")
    sp.add_argument("--auditor")
    sp.add_argument("--window", help="Testing window text.")
    sp.set_defaults(func=cmd_new)

    sp = sub.add_parser("list", help="List engagements.")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("use", help="Set the current engagement.")
    sp.add_argument("engagement")
    sp.set_defaults(func=cmd_use)

    sp = sub.add_parser("status", help="Show engagement status / progress.")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("authorize", help="Record Phase 0 authorization.")
    sp.add_argument("--grant", action="store_true", help="Mark signed authorization in place.")
    sp.add_argument("--revoke", action="store_true")
    sp.add_argument("--officer", help="Authorizing officer/owner name.")
    sp.add_argument("--date")
    sp.add_argument("--letter", help="Path to offline get-out-of-jail letter.")
    sp.add_argument("--note")
    sp.set_defaults(func=cmd_authorize)

    sp = sub.add_parser("scope", help="Manage engagement scope.")
    sp.add_argument("scope_action", choices=["show", "add", "exclude", "check"])
    sp.add_argument("targets", nargs="*", help="IPs / CIDRs / ranges / hostnames.")
    sp.set_defaults(func=cmd_scope)

    sp = sub.add_parser("phase", help="Show a phase checklist.")
    sp.add_argument("number", type=int)
    sp.set_defaults(func=cmd_phase)

    sp = sub.add_parser("check", help="Set a checklist item state.")
    sp.add_argument("item_id")
    sp.add_argument("state", choices=["pending", "in_progress", "done", "na"])
    sp.add_argument("--note")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("finding", help="Manage findings.")
    sp.add_argument("finding_action", choices=["add", "list"])
    sp.add_argument("--title")
    sp.add_argument("--severity", choices=["critical", "high", "medium", "low", "info"], default="info")
    sp.add_argument("--host")
    sp.add_argument("--phase", type=int)
    sp.add_argument("--desc")
    sp.add_argument("--cvss")
    sp.add_argument("--impact")
    sp.add_argument("--remediation")
    sp.set_defaults(func=lambda a: _finding_dispatch(a))

    sp = sub.add_parser("evidence", help="Manage evidence log.")
    sp.add_argument("evidence_action", choices=["add", "list"])
    sp.add_argument("--kind", choices=["command", "file", "note", "screenshot"], default="note")
    sp.add_argument("--summary")
    sp.add_argument("--path")
    sp.add_argument("--item")
    sp.set_defaults(func=lambda a: _evidence_dispatch(a))

    sp = sub.add_parser("qa", help="Final QA recheck gate.")
    sp.add_argument("qa_action", choices=["show", "set"])
    sp.add_argument("qa_id", nargs="?")
    sp.add_argument("value", nargs="?", choices=["true", "false"])
    sp.set_defaults(func=cmd_qa)

    sp = sub.add_parser("tools", help="Check master tool inventory install status.")
    sp.set_defaults(func=cmd_tools)

    sp = sub.add_parser("run", help="Scope-guarded discovery/enumeration runner.")
    sp.add_argument("runner", nargs="?", help="Runner name (see --list).")
    sp.add_argument("target", nargs="?", help="In-scope target.")
    sp.add_argument("--list", action="store_true", help="List available runners.")
    sp.add_argument("--execute", action="store_true", help="Actually run (default: dry-run).")
    sp.add_argument("--timeout", type=int, default=3600)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("report", help="Generate a Markdown report.")
    sp.add_argument("--out", help="Write to file instead of stdout.")
    sp.set_defaults(func=cmd_report)

    return p


def _finding_dispatch(a):
    if a.finding_action == "add" and not a.title:
        raise SystemExit("`finding add` requires --title")
    return cmd_finding(a)


def _evidence_dispatch(a):
    if a.evidence_action == "add" and not a.summary:
        raise SystemExit("`evidence add` requires --summary")
    return cmd_evidence(a)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
