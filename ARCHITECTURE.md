# Architecture

## Data flow

```text
React Dashboard
  │ POST /api/runs
  ▼
Job Manager ── SSE events ───────────────► React live pipeline/logs
  │
  ▼
Weekly Intelligence Engine
  ├─ Discover: PowerUpGaming / GTABase / RockstarINTEL / manual URL
  ├─ Extract: structural article parser + retries
  ├─ Normalize: category/entity normalization
  ├─ Verify: multi-source consensus + confidence
  ├─ Enrich: vehicle catalog + source image matching + cached fallback
  ├─ Persist: history snapshot
  └─ Export: JSON / PDF / optional SMTP email
             │
             ├────────► UI result sections + vehicle gallery
             └────────► Retrieval Intelligence (Ask This Week)
```

## Source of truth

The normalized weekly dataset (`schema_version: 2`) is the source of truth. The UI, PDF, JSON export, history and retrieval engine all consume that dataset. PDF generation is no longer the primary output path.

## Cancellation

The browser calls `POST /api/runs/<id>/cancel`. The worker owns a cancellation flag and checks it between discovery, source extraction, normalization, enrichment and export stages. Closing the browser request alone is not treated as cancellation.

## Confidence

Normalized items track source count, source URLs, source variants, confidence and `verified`. Two or more agreeing sources are marked cross-source verified. A single manual source receives a reasonable confidence floor but is not falsely marked multi-source verified.

## Extending vehicle knowledge

Add canonical names, aliases, manufacturer/class/store metadata and optional page slugs to `backend/data/vehicle_catalog.json`. No extractor changes are required.
