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

## Run it from your phone (web UI)

`netaudit` ships a mobile-first web app and REST API. Because the scope-guarded
runner has to launch tools (`nmap`, etc.) on a host that's actually on the client
network, you run the server on your **on-site testing box** (laptop/NUC/VPS) and use
your **phone's browser as the control surface**.

```bash
# On the testing host, reachable from your phone (same LAN/VPN):
netaudit serve --host 0.0.0.0 --port 8765
```

It prints a URL with an access token, e.g.
`http://localhost:8765/?token=Xy7…`. On your phone, open the same URL but swap
`localhost` for the testing host's LAN/VPN IP (e.g. `http://192.168.1.20:8765/?token=Xy7…`).
"Add to Home Screen" gives you an app-like icon.

From the phone you can do everything the CLI does: create jobs, set the
authorization gate, manage scope, tap through phase checklists, log findings,
trigger scope-guarded scans (dry-run or execute), and view/download the report.

**Access & safety**
- Every API call requires the token (`NETAUDIT_TOKEN`, `--token`, or an
  auto-generated one). The token is the only thing protecting a server that can
  launch tooling — keep the URL secret.
- Prefer a **VPN or SSH tunnel** over exposing the port to untrusted networks:
  `ssh -L 8765:localhost:8765 you@testing-host` then open `http://localhost:8765`
  on the phone — no `0.0.0.0` bind needed.
- All the same gates apply server-side: no run without authorization + a complete
  Phase 0, out-of-scope/excluded targets are refused, exploitation/cracking stay
  manual.

### Access from anywhere (cloud server + on-site agent)

To drive engagements from your phone **anywhere** while still scanning real client
networks, run the canonical server in the cloud and a thin **agent** on-site:

```bash
# on-site box (on the client network):
netaudit agent --server https://your-cloud-host --eng eng-1a2b3c4d host-discovery 192.168.1.50 --execute
```

The agent pulls the engagement from the cloud, re-checks the gates locally
(authorization + Phase 0 + scope), runs the scan on-site, and uploads the captured
output back to the cloud as evidence — so your phone sees everything in one place.
Full instructions, Docker image, and Render/Fly configs are in **[DEPLOY.md](DEPLOY.md)**.

### Hosting the frontend elsewhere (Lovable / custom)

The frontend (`netaudit/web_static/index.html`) is a dependency-free single page
that talks to the REST API, so you can rebuild/restyle it in a tool like Lovable
and point it at your `netaudit serve` backend (set the token, call `/api/...`). But
note: a cloud-hosted server can only run scans against hosts it can actually reach.
For real engagements, keep the *runner* on the on-site box; a cloud instance is fine
as a pure tracking/reporting surface (just don't rely on `run --execute` there).

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
| `serve` | Start the mobile web UI + REST API |
| `agent` | On-site runner for a cloud-hosted engagement (scans locally, uploads evidence) |

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
