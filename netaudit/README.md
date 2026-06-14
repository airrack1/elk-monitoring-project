# netaudit

**Engagement workflow automation for the NetSec Assessments network security audit checklist.**

`netaudit` turns the audit checklist into a tracked, gated, auditable workflow. It
manages engagements end-to-end — authorization, scope, per-item progress, findings,
evidence, and report generation — and includes a **scope-guarded runner** that will
only launch discovery/enumeration tooling against assets you have recorded as
in-scope, and only after Phase 0 authorization is complete.

It is an *orchestration and tracking* tool, not an autonomous attacker. Exploitation,
password cracking, and auth brute-forcing are deliberately left as manual operator
steps so a human owns every intrusive action — exactly as the checklist requires.

> Use only within signed, authorized scope. — *NetSec Assessments LLC*

---

## Why this exists

The checklist's Phase 0 rule is: *"Do not touch a single packet until this phase is
100% complete."* `netaudit` enforces that mechanically:

- **Authorization gate** — active tooling is blocked until a signed authorization,
  authorizing officer, and an offline get-out-of-jail letter path are all recorded.
- **Scope gate** — every target is checked against in-scope ranges; explicit
  exclusions always win. Out-of-scope targets are refused.
- **Dry-run by default** — the runner prints the exact command and refuses to execute
  unless you pass `--execute`.
- **Everything logged** — each action lands in an append-only activity log, and tool
  output is captured to the evidence directory for the report's reproduction steps.

---

## Install

```bash
cd netaudit
pip install -e .          # exposes the `netaudit` command
# or run without installing:
python -m netaudit --help
```

Python 3.8+. Zero third-party runtime dependencies. Engagement data lives under
`~/.netaudit` (override with `NETAUDIT_HOME`).

## Quick start

```bash
# 1. Create an engagement (becomes "current")
netaudit new acme-q2 --client "Acme Corp" --sow SOW-2026-014

# 2. Define scope
netaudit scope add 192.168.10.0/24 dc01.acme.local
netaudit scope exclude 192.168.10.1          # e.g. the client's prod gateway
netaudit scope check 8.8.8.8                 # -> BLOCKED, out of scope

# 3. Record Phase 0 authorization (gates everything below)
netaudit authorize --grant --officer "Jane Owner" --letter ~/secure/acme-auth.pdf

# 4. Work the checklist
netaudit phase 1                              # view a phase's items
netaudit check p1.2 done --note "nmap -sn across all /24s"
netaudit status                               # progress bars per phase

# 5. Scope-guarded discovery (dry-run first, then --execute)
netaudit run --list
netaudit run host-discovery 192.168.10.50     # dry run: prints the command
netaudit run host-discovery 192.168.10.50 --execute

# 6. Record findings + generate the report
netaudit finding add --title "Telnet exposed" --severity high --host 192.168.10.5 --cvss 7.3
netaudit report --out acme-q2-report.md
```

## Commands

| Command | Purpose |
|---------|---------|
| `new`, `list`, `use`, `status` | Engagement lifecycle and the "current" pointer |
| `authorize` | Record / revoke Phase 0 authorization (the master gate) |
| `scope add\|exclude\|show\|check` | Manage and test scope |
| `phase <n>` | View a phase checklist (states: `[ ] [~] [x] [-]`) |
| `check <item> <state>` | Set item state (`pending`/`in_progress`/`done`/`na`) |
| `finding add\|list` | Track findings (severity, host, CVSS, impact, remediation) |
| `evidence add\|list` | Append to the evidence log |
| `qa show\|set` | Final QA recheck gate |
| `tools` | Check the master tool inventory against your `$PATH` |
| `run` | Scope-guarded discovery/enumeration runner |
| `report` | Generate a Markdown report |

## What the runner will (and won't) do

**Included** (read-only / discovery / enumeration): `nmap` host discovery, TCP/UDP
service detection, `enum4linux-ng`, `snmp-check`, `testssl.sh`, `sslscan`, `nikto`,
`nuclei`.

**Deliberately excluded** (stay manual): exploitation frameworks, password cracking,
auth brute-forcing, wireless handshake attacks. The checklist treats these as
operator-driven, documented actions and so does this tool.

The runner refuses to run if: authorization isn't granted, Phase 0 isn't complete, the
target is out of scope or excluded, or the requested runner isn't in the allowlist.

## Data layout

```
$NETAUDIT_HOME/                 (default: ~/.netaudit)
  current                       # id of the current engagement
  engagements/<id>.json         # one self-contained, diff-able record per engagement
  evidence/<id>/                # captured tool output
```

## Development

```bash
pip install -e ".[dev]"
PYTHONPATH=. python -m pytest -q
```

The master checklist is encoded in `netaudit/data/checklist_template.py` — edit there
to evolve phases or items; item ids stay stable so existing engagements keep tracking.
