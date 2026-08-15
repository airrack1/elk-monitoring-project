# NIGHTRANGE

NIGHTRANGE is a self-contained, browser-based cyber range. It includes simulated networking, offensive-security, backend, and frontend labs; a Kali-style terminal; guided objectives; progression, profiles, studies, badges, and an attack-defense arena.

## Run locally

```powershell
python -m http.server 4173
```

Open <http://127.0.0.1:4173/>.

## Verify

```powershell
npm test
```

## Publish updates

Push to `main` or `claude/web-app-iphone-browser-5w9pv9`. GitHub Actions validates the standalone app and publishes the latest commit to GitHub Pages.

The public site is independent of Claude. Visitors see only NIGHTRANGE and cannot see the owner's Claude account or email.

