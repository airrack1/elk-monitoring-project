import json
import urllib.request

import pytest

from netaudit import agent, web, runner


@pytest.fixture()
def server(tmp_path, monkeypatch):
    # isolate storage to a temp NETAUDIT_HOME
    monkeypatch.setenv("NETAUDIT_HOME", str(tmp_path))
    httpd = web.serve_in_thread(host="127.0.0.1", port=0, token="testtoken")
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base
    httpd.shutdown()


def _post(base, path, body, token="testtoken"):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def _authorized_engagement(base):
    eng = _post(base, "/api/engagements", {"name": "agent-test"})
    eid = eng["id"]
    _post(base, f"/api/engagements/{eid}/scope", {"action": "add", "targets": ["192.168.9.0/24"]})
    _post(base, f"/api/engagements/{eid}/authorize", {"grant": True, "officer": "J", "letter": "/x"})
    tmpl = json.loads(urllib.request.urlopen(
        urllib.request.Request(base + "/api/template", headers={"Authorization": "Bearer testtoken"})
    ).read())
    for it in next(p for p in tmpl["phases"] if p["number"] == 0)["items"]:
        _post(base, f"/api/engagements/{eid}/check", {"item_id": it["id"], "state": "done"})
    return eid


def test_agent_dry_run(server):
    eid = _authorized_engagement(server)
    res = agent.run_remote(server, "testtoken", eid, "host-discovery", "192.168.9.10", execute=False)
    assert res["executed"] is False
    assert "nmap" in res["command"]


def test_agent_blocks_out_of_scope(server):
    eid = _authorized_engagement(server)
    with pytest.raises(runner.PreflightError):
        agent.run_remote(server, "testtoken", eid, "host-discovery", "10.0.0.1", execute=False)


def test_agent_bad_token(server):
    eid = _authorized_engagement(server)
    with pytest.raises(agent.RemoteError):
        agent.run_remote(server, "wrong", eid, "host-discovery", "192.168.9.10")


def test_evidence_content_upload(server):
    eid = _authorized_engagement(server)
    res = _post(server, f"/api/engagements/{eid}/evidence",
                {"kind": "command", "summary": "manual upload", "content": "scan output here"})
    assert res["evidence"]["path"]  # server wrote the content to a file
