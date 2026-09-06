# GTA Online Weekly Intelligence Companion

A local-first React + Flask companion application that discovers GTA Online weekly-update sources, extracts and normalizes structured data, cross-validates multiple sources, enriches vehicle entities/images, displays results in an animated dashboard, keeps history, supports retrieval-style queries, and exports PDF/JSON/email from the same dataset.

## What changed from the original scraper

- Background job architecture with real stages, SSE progress events and true cancellation checks.
- Multi-source extraction + consensus/confidence scoring.
- Structured weekly JSON is now the source of truth.
- Vehicle entity enrichment with article-image matching and an extensible local vehicle knowledge catalog.
- Retrieval-style **Ask This Week** feature grounded in the latest saved dataset.
- Results and vehicle cards are visible directly in the UI.
- User-selectable export directory, including a Windows-native folder picker when available.
- PDF and JSON exports, optional SMTP email, history snapshots and a redesigned GTA-inspired animated UI.
- Secret password text file removed; app passwords are not persisted by the frontend.

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Backend: `http://localhost:5000`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

## Main API

- `POST /api/runs` — start a background intelligence run
- `GET /api/runs/<id>` — run state/result
- `GET /api/runs/<id>/events` — Server-Sent Events progress stream
- `POST /api/runs/<id>/cancel` — request real cancellation
- `GET /api/runs/<id>/pdf` / `json` — exports
- `GET /api/history` / `latest` — stored snapshots
- `POST /api/knowledge/query` — retrieval-style query against latest weekly data
- `GET/PUT /api/settings` — local configuration
- `POST /api/system/select-output-directory` — local native folder picker (best on Windows desktop sessions)

## Vehicle images / knowledge catalog

The engine first tries metadata in `backend/data/vehicle_catalog.json`, then resolves images from the weekly source article by matching image alt/title/context against extracted vehicle names. If that fails, it performs a cached, title-validated best-effort lookup against a GTA vehicle detail database before falling back to a branded placeholder; it does not silently attach an unverified car image.

The local catalog is deliberately extensible. Add records/aliases/metadata over time without changing the extraction engine.

## Notes

This project is unofficial and is not affiliated with Rockstar Games or Take-Two Interactive. Site layouts can change; the adapter/retry/consensus design is intended to fail gracefully when individual sources change.
