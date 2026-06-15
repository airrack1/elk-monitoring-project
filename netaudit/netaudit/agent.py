"""On-site agent.

When the canonical netaudit server lives in the cloud (so you can manage the
engagement from your phone anywhere), the scans themselves still have to run on a
machine that's actually on the client's network. This agent bridges the two:

  1. Fetch the engagement (scope + authorization + checklist) from the cloud.
  2. Re-run the SAME local preflight as the CLI (authorization granted, Phase 0
     complete, target in scope) — the gates are enforced here too, not trusted.
  3. Run the scope-guarded command locally and capture its output.
  4. Push the captured output back to the cloud as an evidence item.

Nothing is trusted from the network: the agent independently re-checks scope and
authorization before it will execute anything, and it still defaults to dry-run.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import runner
from .models import Engagement


class RemoteError(Exception):
    pass


def _api(base: str, token: str, path: str, method: str = "GET", body=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read() or b"{}"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except json.JSONDecodeError:
            pass
        raise RemoteError(f"server {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise RemoteError(f"cannot reach {base}: {exc.reason}") from None


def fetch_engagement(base: str, token: str, eng_id: str) -> Engagement:
    data = _api(base, token, f"/api/engagements/{eng_id}")
    return Engagement.from_dict(data)


def run_remote(base, token, eng_id, runner_name, target, execute=False, timeout=3600) -> dict:
    """Run a scan locally for a cloud-hosted engagement and upload the result."""
    eng = fetch_engagement(base, token, eng_id)

    # Local, independent preflight — raises PreflightError if blocked.
    result = runner.run(eng, runner_name, target, execute=execute, timeout=timeout)

    if execute and result.get("executed"):
        with open(result["output_path"], "r", encoding="utf-8") as fh:
            content = fh.read()
        up = _api(
            base, token, f"/api/engagements/{eng_id}/evidence", "POST",
            {
                "kind": "command",
                "summary": f"{runner_name} against {target} (rc={result['return_code']})",
                "filename": f"{runner_name}__{target.replace('/', '_').replace(':', '_')}.txt",
                "content": content,
            },
        )
        result["uploaded_evidence"] = (up.get("evidence") or {}).get("id")
        result["server"] = base
    return result
