# netaudit Academy

The Academy is a single-file, mobile-first learning surface served by the
existing netaudit server at `/academy.html`. The server and generated offline
phone UIs both link to it.

It includes frontend, backend, Linux, cloud, and defensive-security study
boxes; detailed forums; browser-contained Linux-style terminals; local learner
profiles and badges; optional CISA KEV context; and adaptive incident rooms.
Learner names organize browser-local progress and are not authentication.

All terminal commands and incident responses are simulations. Learner input is
never sent to a shell, the real netaudit runner, or an external target. The
real runner's authorization, Phase 0, and scope gates remain unchanged.

Run locally from `netaudit/`:

```bash
netaudit serve --host 127.0.0.1
```

Then open the printed Academy URL. Academy progress uses a versioned local
storage record with a visible memory-only fallback when browser storage is
unavailable. Each simulated incident type is capped at two deployments per
profile.

Validation:

```bash
python -m pytest -q
python -m pytest -q tests/test_academy.py
node tests/browser_smoke.js netaudit/web_static/academy.html
python -m netaudit.tools.build_standalone --check
```
