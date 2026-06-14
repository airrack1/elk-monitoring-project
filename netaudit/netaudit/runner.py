"""Scope-guarded tool runner.

Design constraints (mirroring the engagement's own rules):
  * Active tooling is BLOCKED until Phase 0 authorization is granted.
  * Every target is checked against engagement scope; exclusions always win.
  * Only a curated allowlist of *discovery / enumeration / read-only config*
    commands can be launched here. Exploitation, password cracking, and auth
    brute-forcing are intentionally NOT automated — they stay manual, operator
    driven steps (Phases 5, 7, 8) so a human owns every intrusive action.
  * Dry-run is the default. Real execution requires an explicit flag.
  * Output is captured to the evidence directory and logged on the engagement.

This is an orchestration convenience, not an autonomous attacker.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .models import Engagement
from .storage import workspace_dir

# name -> spec. {target} is substituted with the validated target.
# Keep these non-destructive. `phase` is informational; `binary` is checked for
# availability. Argument lists avoid shell interpolation entirely.
RUNNERS: Dict[str, dict] = {
    "host-discovery": {
        "phase": 1,
        "binary": "nmap",
        "args": ["-sn", "{target}"],
        "desc": "Live host discovery (ping sweep), no port scan.",
    },
    "tcp-services": {
        "phase": 2,
        "binary": "nmap",
        "args": ["-sV", "-sC", "-T3", "{target}"],
        "desc": "TCP service/version detection with default+safe NSE scripts.",
    },
    "tcp-full": {
        "phase": 2,
        "binary": "nmap",
        "args": ["-p-", "-sV", "-T3", "{target}"],
        "desc": "Full TCP port scan with version detection.",
    },
    "udp-key": {
        "phase": 2,
        "binary": "nmap",
        "args": ["-sU", "-p", "53,123,161,500", "{target}"],
        "desc": "UDP scan of common key ports (DNS/NTP/SNMP/IKE).",
    },
    "smb-enum": {
        "phase": 2,
        "binary": "enum4linux-ng",
        "args": ["-A", "{target}"],
        "desc": "SMB/NetBIOS enumeration (shares, users, sessions).",
    },
    "snmp-enum": {
        "phase": 2,
        "binary": "snmp-check",
        "args": ["{target}"],
        "desc": "SNMP enumeration (default community strings).",
    },
    "tls-audit": {
        "phase": 4,
        "binary": "testssl.sh",
        "args": ["{target}"],
        "desc": "TLS/SSL configuration audit (ciphers, SWEET32, cert, protocols).",
    },
    "tls-scan": {
        "phase": 4,
        "binary": "sslscan",
        "args": ["{target}"],
        "desc": "Quick TLS/SSL cipher and protocol scan.",
    },
    "web-nikto": {
        "phase": 8,
        "binary": "nikto",
        "args": ["-h", "{target}"],
        "desc": "Web server misconfiguration / known-issue scan.",
    },
    "web-nuclei": {
        "phase": 3,
        "binary": "nuclei",
        "args": ["-u", "{target}"],
        "desc": "Template-based vulnerability checks (current CVEs).",
    },
}


@dataclass
class PreflightError(Exception):
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


def evidence_dir(eng: Engagement) -> Path:
    d = workspace_dir() / "evidence" / eng.id
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_runners() -> List[dict]:
    out = []
    for name, spec in sorted(RUNNERS.items(), key=lambda kv: (kv[1]["phase"], kv[0])):
        out.append({"name": name, **spec, "installed": shutil.which(spec["binary"]) is not None})
    return out


def build_command(name: str, target: str) -> List[str]:
    spec = RUNNERS[name]
    return [spec["binary"]] + [a.replace("{target}", target) for a in spec["args"]]


def preflight(eng: Engagement, name: str, target: str) -> List[str]:
    """Validate everything before any command can run. Returns argv or raises."""
    if name not in RUNNERS:
        raise PreflightError(f"Unknown runner '{name}'. See `netaudit run --list`.")

    if not eng.authorization.granted:
        raise PreflightError(
            "BLOCKED: Phase 0 authorization is not recorded as granted. "
            "Record signed authorization + letter before any active tooling."
        )

    if not eng.phase_complete(0):
        raise PreflightError(
            "BLOCKED: Phase 0 checklist is not 100% complete. "
            "Finish pre-engagement items before touching the network."
        )

    result = eng.scope.check(target)
    if not result.allowed:
        raise PreflightError(f"BLOCKED by scope: {result.reason}")

    return build_command(name, target)


def run(
    eng: Engagement,
    name: str,
    target: str,
    execute: bool = False,
    timeout: Optional[int] = 3600,
) -> dict:
    """Preflight, then either dry-run (default) or execute and capture output."""
    argv = preflight(eng, name, target)
    printable = " ".join(shlex.quote(a) for a in argv)

    if not execute:
        eng.log("run.dryrun", f"[{name}] {printable}")
        return {"executed": False, "command": printable, "target": target}

    if shutil.which(argv[0]) is None:
        raise PreflightError(f"Tool '{argv[0]}' is not installed / not on PATH.")

    out_dir = evidence_dir(eng)
    safe_target = target.replace("/", "_").replace(":", "_")
    out_path = out_dir / f"{name}__{safe_target}.txt"

    eng.log("run.exec", f"[{name}] {printable}")
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True,
        )
        output = proc.stdout or ""
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        output = f"[netaudit] command timed out after {timeout}s"
        rc = -1

    header = f"# command: {printable}\n# scope-checked target: {target}\n# return code: {rc}\n\n"
    out_path.write_text(header + output, encoding="utf-8")

    ev = eng.add_evidence(
        "command",
        f"{name} against {target} (rc={rc})",
        path=str(out_path),
    )
    return {
        "executed": True,
        "command": printable,
        "target": target,
        "return_code": rc,
        "evidence_id": ev.id,
        "output_path": str(out_path),
    }
