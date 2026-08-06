"""Mobile-friendly web server for netaudit.

`netaudit serve` exposes a JSON REST API plus a self-contained, phone-first
single-page UI so an auditor can drive an engagement from a browser on their
phone. The server reuses the same core (models, storage, scope, runner, report)
as the CLI, so the gating guarantees are identical: authorization + scope are
enforced server-side, the runner stays dry-run unless explicitly executed, and
exploitation/cracking are still not automated.

IMPORTANT: this server can trigger discovery tooling, so it requires an access
token on every API call. A token is generated on startup if you don't supply
one (NETAUDIT_TOKEN). Run it on the on-site testing host that actually sits on
the client network; the phone is just the control surface.

Zero third-party dependencies — built on http.server.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import report, runner, storage
from .data import checklist_template as tmpl
from .models import Engagement

STATIC_DIR = Path(__file__).parent / "web_static"


def _template_payload() -> dict:
    return {
        "version": tmpl.TEMPLATE_VERSION,
        "phases": [
            {
                "number": p["number"],
                "name": p["name"],
                "intent": p["intent"],
                "optional": p.get("optional", False),
                "tools": p["tools"],
                "items": [{"id": iid, "text": txt} for iid, txt in items],
            }
            for p, items in (
                (p, tmpl.build_phase_items()[p["number"]]) for p in tmpl.PHASES
            )
        ],
        "qa": [{"id": f"qa.{i}", "text": t} for i, t in enumerate(tmpl.FINAL_QA, 1)],
    }


def _engagement_payload(eng: Engagement) -> dict:
    d = eng.to_dict()
    d["progress"] = {
        str(p["number"]): dict(zip(("done", "total", "percent"), eng.phase_progress(p["number"])))
        for p in tmpl.PHASES
    }
    d["authorization"]["granted"] = eng.authorization.granted
    return d


class Handler(BaseHTTPRequestHandler):
    server_version = "netaudit/0.1"
    token = ""  # set by serve()

    # -- helpers --------------------------------------------------------
    def _send(self, code: int, payload, content_type="application/json"):
        body = json.dumps(payload).encode() if content_type == "application/json" else payload
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code, msg):
        self._send(code, {"error": msg})

    def _authed(self, query) -> bool:
        hdr = self.headers.get("Authorization", "")
        if hdr.startswith("Bearer ") and secrets.compare_digest(hdr[7:], self.token):
            return True
        tok = (query.get("token", [None]) or [None])[0]
        return bool(tok and secrets.compare_digest(tok, self.token))

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}

    def log_message(self, *a):  # quieter logs
        pass

    # -- routing --------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if not path.startswith("/api/"):
            return self._serve_static(path)
        if not self._authed(query):
            return self._err(401, "missing or invalid token")
        try:
            self._route_get(path, query)
        except FileNotFoundError as exc:
            self._err(404, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self._err(500, str(exc))

    def do_POST(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if not self._authed(query):
            return self._err(401, "missing or invalid token")
        try:
            self._route_post(path, self._body())
        except FileNotFoundError as exc:
            self._err(404, str(exc))
        except (ValueError, runner.PreflightError) as exc:
            self._err(400, str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self._err(500, str(exc))

    def _route_get(self, path, query):
        parts = path.strip("/").split("/")  # ['api', ...]
        if path == "/api/ping":
            return self._send(200, {"ok": True})
        if path == "/api/template":
            return self._send(200, _template_payload())
        if path == "/api/runners":
            return self._send(200, {"runners": runner.list_runners()})
        if path == "/api/tools":
            import shutil
            return self._send(200, {
                "groups": {g: [{"name": t, "installed": shutil.which(t) is not None} for t in ts]
                           for g, ts in tmpl.TOOL_INVENTORY.items()}
            })
        if path == "/api/engagements":
            return self._send(200, {"engagements": storage.list_all()})
        # /api/engagements/<id>...
        if len(parts) >= 3 and parts[1] == "engagements":
            eng = storage.load(parts[2])
            if len(parts) == 3:
                return self._send(200, _engagement_payload(eng))
            if parts[3] == "report":
                return self._send(200, report.markdown_report(eng), content_type="text/markdown")
            if parts[3] == "scope" and len(parts) >= 5 and parts[4] == "check":
                target = (query.get("target", [""]) or [""])[0]
                res = eng.scope.check(target)
                return self._send(200, {"allowed": res.allowed, "reason": res.reason})
        self._err(404, "not found")

    def _route_post(self, path, body):
        parts = path.strip("/").split("/")
        if path == "/api/engagements":
            eng = Engagement.create(
                name=body["name"], client=body.get("client", ""), sow_ref=body.get("sow", ""),
                lead_auditor=body.get("auditor", "Aaryon"), testing_window=body.get("window", ""),
            )
            storage.save(eng)
            return self._send(201, _engagement_payload(eng))

        if len(parts) >= 4 and parts[1] == "engagements":
            eng = storage.load(parts[2])
            action = parts[3]

            if action == "authorize":
                a = eng.authorization
                if "officer" in body: a.authorizing_officer = body["officer"]
                if "date" in body: a.signed_date = body["date"]
                if "letter" in body: a.letter_path = body["letter"]
                if "note" in body: a.notes = body["note"]
                if "grant" in body: a.signed = bool(body["grant"])
                eng.log("authorization.update", f"granted={a.granted}")
                storage.save(eng)
                return self._send(200, _engagement_payload(eng))

            if action == "scope":
                act, targets = body.get("action"), body.get("targets", [])
                if act == "add":
                    for t in targets:
                        if t and t not in eng.scope.in_scope: eng.scope.in_scope.append(t)
                elif act == "exclude":
                    for t in targets:
                        if t and t not in eng.scope.exclusions: eng.scope.exclusions.append(t)
                elif act == "remove":
                    eng.scope.in_scope = [t for t in eng.scope.in_scope if t not in targets]
                    eng.scope.exclusions = [t for t in eng.scope.exclusions if t not in targets]
                else:
                    raise ValueError("scope action must be add|exclude|remove")
                eng.log("scope.update", f"{act}: {', '.join(targets)}")
                storage.save(eng)
                return self._send(200, _engagement_payload(eng))

            if action == "check":
                eng.set_item(body["item_id"], body["state"], note=body.get("note", ""))
                storage.save(eng)
                return self._send(200, _engagement_payload(eng))

            if action == "qa":
                eng.qa[body["qa_id"]] = bool(body["value"])
                eng.log("qa.update", f"{body['qa_id']}={body['value']}")
                storage.save(eng)
                return self._send(200, _engagement_payload(eng))

            if action == "findings":
                f = eng.add_finding(
                    body["title"], severity=body.get("severity", "info"), host=body.get("host", ""),
                    phase=body.get("phase"), description=body.get("description", ""),
                    cvss=body.get("cvss", ""), business_impact=body.get("business_impact", ""),
                    remediation=body.get("remediation", ""),
                )
                storage.save(eng)
                return self._send(201, {"finding": f.to_dict(), "engagement": _engagement_payload(eng)})

            if action == "evidence":
                path = body.get("path", "")
                content = body.get("content")
                if content is not None:
                    # An agent (or the UI) uploaded captured output; persist it
                    # to this server's evidence directory and link it.
                    import re
                    from .runner import evidence_dir
                    base = re.sub(r"[^A-Za-z0-9_.-]", "_", body.get("filename") or body["summary"])[:60]
                    out = evidence_dir(eng) / (base or "evidence")
                    out.write_text(content, encoding="utf-8")
                    path = str(out)
                e = eng.add_evidence(body.get("kind", "note"), body["summary"],
                                     path=path, item_id=body.get("item_id", ""))
                storage.save(eng)
                return self._send(201, {"evidence": e.to_dict()})

            if action == "run":
                result = runner.run(eng, body["runner"], body["target"],
                                    execute=bool(body.get("execute", False)),
                                    timeout=int(body.get("timeout", 3600)))
                storage.save(eng)
                return self._send(200, result)

        self._err(404, "not found")

    # -- static UI ------------------------------------------------------
    def _serve_static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (STATIC_DIR / rel).resolve()
        if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve() / rel:
            # path traversal guard
            if not str(target).startswith(str(STATIC_DIR.resolve())):
                return self._err(403, "forbidden")
        if not target.is_file():
            return self._err(404, "not found")
        ctype = {
            ".html": "text/html", ".js": "application/javascript",
            ".css": "text/css", ".svg": "image/svg+xml",
        }.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), content_type=ctype)


def serve(host="127.0.0.1", port=8765, token=None):
    token = token or os.environ.get("NETAUDIT_TOKEN") or secrets.token_urlsafe(18)
    Handler.token = token
    httpd = ThreadingHTTPServer((host, port), Handler)
    shown_host = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    url = f"http://{shown_host}:{port}/?token={token}"
    print("netaudit web UI running.")
    print(f"  Local URL : {url}")
    print(f"  Offline   : http://{shown_host}:{port}/standalone.html  (no token, no API,")
    print("              runs entirely in the browser — save it for offline use)")
    if host == "0.0.0.0":
        print("  Phone     : replace 'localhost' with this machine's LAN/VPN IP, keep the token.")
        print("  WARNING   : bound to 0.0.0.0 (all interfaces). Token is the only thing")
        print("              protecting the scope-guarded runner. Keep the URL secret;")
        print("              prefer a VPN/SSH tunnel over exposing this to untrusted networks.")
    print(f"  Token     : {token}")
    print("  Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        httpd.shutdown()
    return httpd


# allow running a server in a daemon thread (used by tests)
def serve_in_thread(host="127.0.0.1", port=0, token="testtoken"):
    Handler.token = token
    httpd = ThreadingHTTPServer((host, port), Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
