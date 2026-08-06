import json
import urllib.request
import urllib.error

import pytest

from netaudit import web


@pytest.fixture()
def server():
    httpd = web.serve_in_thread(host="127.0.0.1", port=0, token="testtoken")
    port = httpd.server_address[1]
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def call(base, path, method="GET", body=None, token="testtoken"):
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_requires_token(server):
    code, _ = call(server, "/api/engagements", token=None)
    assert code == 401


def test_ping_is_public_for_platform_health_checks(server):
    code, payload = call(server, "/api/ping", token=None)
    assert code == 200
    assert payload == {"ok": True}


def test_create_and_gate_flow(server):
    code, eng = call(server, "/api/engagements", "POST", {"name": "web-test", "client": "Acme"})
    assert code == 201
    eid = eng["id"]

    # add scope
    call(server, f"/api/engagements/{eid}/scope", "POST", {"action": "add", "targets": ["192.168.5.0/24"]})

    # run is blocked before authorization
    code, res = call(server, f"/api/engagements/{eid}/run", "POST",
                     {"runner": "host-discovery", "target": "192.168.5.10"})
    assert code == 400 and "BLOCKED" in res["error"]

    # grant auth + complete phase 0
    call(server, f"/api/engagements/{eid}/authorize", "POST",
         {"grant": True, "officer": "Jane", "letter": "/x.pdf"})
    tmpl_code, tmpl = call(server, "/api/template")
    p0 = next(p for p in tmpl["phases"] if p["number"] == 0)
    for it in p0["items"]:
        call(server, f"/api/engagements/{eid}/check", "POST", {"item_id": it["id"], "state": "done"})

    # dry run now allowed (out-of-scope still blocked)
    code, res = call(server, f"/api/engagements/{eid}/run", "POST",
                     {"runner": "host-discovery", "target": "10.0.0.1", "execute": False})
    assert code == 400  # out of scope
    code, res = call(server, f"/api/engagements/{eid}/run", "POST",
                     {"runner": "host-discovery", "target": "192.168.5.10", "execute": False})
    assert code == 200 and res["executed"] is False


def test_static_ui_served(server):
    req = urllib.request.Request(server + "/")
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode()
    assert "netaudit" in html and "<!DOCTYPE html>" in html

    with urllib.request.urlopen(server + "/academy.html") as resp:
        academy = resp.read().decode()
    assert resp.status == 200
    assert "netaudit Academy" in academy
    assert "safe browser lab" in academy
