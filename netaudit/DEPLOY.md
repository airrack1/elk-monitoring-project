# Deploying netaudit (cloud + on-site)

This is the **both** setup: one canonical netaudit server in the cloud (reachable
from your phone anywhere), plus an on-site **agent** that runs the actual scans on
the client's network and pushes evidence back up to the cloud.

```
   Phone (anywhere) ── HTTPS ──►  Cloud netaudit server  ◄── HTTPS ── On-site agent
   manage engagement,             (source of truth:           runs nmap/testssl/etc.
   findings, reports              engagements + evidence)      ON the client LAN,
                                                               uploads results
```

Why split it: a cloud box can't reach a client's internal `192.168.x.x` hosts, so
scanning must happen on-site. But you still want to drive everything from your phone,
so the *records* live in the cloud and the on-site machine is just a runner.

---

## Part A — Stand up the cloud server

> ⚠️ This server can launch security tooling. On a public host the **token is the
> only thing protecting it.** Always set a long random `NETAUDIT_TOKEN`, always use
> the platform's HTTPS, and never paste the token URL anywhere public.

### Option 1: Render (simplest)
1. Push this repo to GitHub.
2. render.com → **New → Blueprint** → pick this repo (it reads `render.yaml`).
3. In the service's **Environment**, set `NETAUDIT_TOKEN` to a long random secret:
   `python -c "import secrets; print(secrets.token_urlsafe(24))"`
4. Deploy. Your URL is `https://netaudit-xxxx.onrender.com`.
   (The `starter` plan + 1 GB disk keeps engagement data across restarts.)

### Option 2: Fly.io
```bash
fly launch --no-deploy
fly volume create netaudit_data --size 1
fly secrets set NETAUDIT_TOKEN=$(python -c "import secrets;print(secrets.token_urlsafe(24))")
fly deploy
```

### Option 3: any Docker host / VPS
```bash
docker build -t netaudit .
docker run -d -p 443:8765 \
  -e NETAUDIT_TOKEN="<long-random-secret>" \
  -v netaudit_data:/data --name netaudit netaudit
```
Put it behind a TLS reverse proxy (Caddy/Traefik) so it's HTTPS, not plain HTTP.

### Use it from your phone
Open `https://<your-host>/?token=<NETAUDIT_TOKEN>` and **Add to Home Screen**.
You now have the full UI anywhere: jobs, authorization gate, scope, checklists,
findings, reports. (The `Run` tab's *Execute* won't reach client networks from the
cloud — that's the agent's job, below.)

---

## Part B — Run scans on-site with the agent

On the laptop/NUC that's plugged into the client network:

```bash
pip install -e .          # from this repo

# point it at your cloud server + the engagement id shown in the UI
export NETAUDIT_TOKEN="<the same secret>"

# preview first (dry-run, default):
netaudit agent --server https://<your-host> --eng eng-1a2b3c4d host-discovery 192.168.1.50

# then run for real; output is captured and uploaded to the cloud as evidence:
netaudit agent --server https://<your-host> --eng eng-1a2b3c4d host-discovery 192.168.1.50 --execute
```

The agent **re-checks the gates locally** before doing anything: it pulls the
engagement from the cloud and refuses to run unless authorization is granted, Phase 0
is 100% complete, and the target is in scope (exclusions still win). Then the evidence
shows up in the cloud UI's report, viewable from your phone.

> Tip: combine with Tailscale if you'd rather not expose the server publicly at all —
> put the cloud box and your phone on the same tailnet and use its private hostname as
> `--server`. You get anywhere-access without a public endpoint.

---

## Data & backups
Everything lives under `NETAUDIT_HOME` (`/data` in the container):
`engagements/*.json` and `evidence/<id>/`. Back up that volume per your evidence
retention policy. The JSON is plain and diff-able.
