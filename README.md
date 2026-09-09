# GTA Intelligence

React + Flask app for discovering GTA Online weekly articles, comparing sources, enriching vehicle information, searching saved reports, and exporting PDF/JSON. Optional SMTP email uses the same report.

## Run locally

Requirements: Python 3.12 or 3.13, Node.js 22+, and npm.

From PowerShell at the repository root:

```powershell
py -m pip install -r backend/requirements.txt
py backend/app.py
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open the URL printed by Vite (normally http://localhost:5173). The frontend proxies /api to Flask on port 5000. Alternatively run start_app.ps1, which creates a virtual environment and starts both services in hidden windows with logs in backend/runtime.

Local data uses SQLite at backend/runtime/state.sqlite3. Reports have per-run export directories; existing legacy JSON history remains readable. Do not delete runtime data to update the app.

## Vercel deployment

Deploy the **repository root**, not just frontend. Root vercel.json defines the Vite frontend and Python API as Vercel Services. The Python entrypoint must be **pyproject.toml**: this makes Vercel build the Flask app plus the private Celery queue subscriber. Using app:app directly omits the subscriber in Services mode.

1. Sign in with Vercel CLI 59+ and run vercel link at the repository root.
2. Create a Neon PostgreSQL database through the Vercel Marketplace and connect it to the project. The current free plan can be selected explicitly; do not enable a paid plan unintentionally.
3. Configure DATABASE_URL, GTA_APP_PASSWORD (at least 14 characters), and GTA_SESSION_SECRET as server-side secrets for Production and Preview. Use separate databases for preview/production when preview tests should not affect production history.
4. The connected Omars64/GTA-Analysis-Program repository deploys main automatically through Vercel's Git integration. The GitHub Actions workflow runs backend tests and the frontend build on pushes and pull requests. These checks run independently of Vercel deployment; configure required checks in branch protection if you need to prevent merging failing changes. For a manual deployment, run vercel deploy --prod.
5. Verify /api/health returns status ok, sign in, run a scan, refresh during the run, and download both exports from History.

No VITE_API_BASE_URL is needed for this same-origin deployment. Never put database or SMTP secrets in VITE_* variables. The app refuses to serve protected APIs if cloud storage or its password is missing.

The generated .env.gta-access.local is a private, gitignored password recovery file. Store it securely; do not share or commit it. scripts/configure_vercel_access.py can generate initial access credentials and send them to the linked Vercel project through stdin without printing their values.

### Optional email

Set SMTP_SERVER, SMTP_PORT (587 STARTTLS or 465 implicit TLS), SMTP_USERNAME, SMTP_PASSWORD, EMAIL_FROM, and optionally EMAIL_TO in Vercel. Redeploy after changing environment variables. Gmail requires an app password rather than the normal account password. Enable “Email PDF” explicitly when running a scan.

Hosted mode never accepts SMTP credentials from the browser. If email is unconfigured, the app disables the email checkbox; PDF/JSON downloads remain available. A failed delivery does not discard the report. Ambiguous email attempts are not automatically resent, to avoid duplicates.

### What persists

Settings includes a GTA logo number (default 5, displayed as V) and 1–10 source URLs. The default listings discover weekly articles from RockstarINTEL, GTABase and PowerUpGaming. The dashboard's additional article URL supplements these sources.

The dashboard and archive open saved reports inline. Use Edit report to correct individual fields and record a change note. Corrections preserve original evidence, increment the revision, clear source-verification for changed rows, and regenerate exports from the saved data. This is a manual editor, not an AI rewriting service. Email PDF sends the saved revision to the recipients you enter; repeated requests with the same delivery ID do not resend it.

PostgreSQL stores jobs, progress events, checkpoints, settings, history, and resolved image URLs. Vercel Queues runs bounded steps with database leases and retries after interrupted delivery. A closed browser does not stop a scan. SSE reconnects automatically, with five-second status polling as fallback.

PDFs are regenerated from saved data when downloaded, rather than stored on Vercel's temporary filesystem. Hosted apps cannot choose folders on your computer: use browser downloads. The Windows folder picker remains available locally.

### Verification

```powershell
py -m unittest discover -s tests -v
cd frontend
npm run build
```

scripts/verify_live.py exercises the real hosted flow with the private recovery file. It never sends email; it verifies authentication, scanning, persistence, queries, downloads, and a fresh session. Verification exports stay under the ignored backend/runtime/verification directory.

## Limitations and interpretation

- “Verified” means matching item names/categories were found in multiple sources; it is not independent confirmation of every price, restriction, or reward. Consult linked source articles and recorded variants.
- Source layouts, availability, and image hotlink policies can change. Failures and stale/estimated weeks are shown explicitly. Images have a placeholder fallback.
- “Ask this week” is retrieval from the selected report, not a general-purpose AI chat or an external paid model.
- This is a private single-owner application, not a multi-user SaaS with per-user data isolation.
- render.yaml is an optional persistent-server alternative; it is not required for the all-Vercel deployment.

This is an unofficial fan project, not affiliated with Rockstar Games or Take-Two Interactive.
