# Architecture

## Production flow

React / Vite → same-origin /api → Flask → PostgreSQL
                                  ↓
                         Vercel Celery queue
                                  ↓
         discover → extract → normalize → enrich → export

The backend service uses pyproject.toml as its entrypoint. Its tool.vercel section declares app:app as the public web application and worker:app as a private subscriber. Each task processes one checkpointable unit, then enqueues the next version.

## Persistence and recovery

Schema version 3 is the shared report format for UI, retrieval, PDF, JSON and email. The gta_records table stores namespaced JSON records. Reads and writes open short-lived PostgreSQL connections; atomic mutations lock the record. Local mode uses equivalent SQLite transactions.

Jobs store parameters without SMTP passwords, monotonic event sequences, progress, checkpoint version, owner token and a lease. Duplicate/stale deliveries cannot repeat an already-checkpointed step. Vercel task acknowledgements happen after execution. Local status requests recover expired unfinished jobs after a process restart.

Cancelling sets a persisted flag. Network calls check cancellation between downloads/chunks, and each phase checks it. An in-flight request may take until its timeout to stop. Queued jobs can be cancelled immediately.

## Network and extraction

Fetches validate public HTTP(S) addresses and redirects, reject private addresses, bound response size, apply request timeouts, and share a per-step cache. Windows uses the system certificate store; TLS verification remains enabled.

Discovery supports PowerUpGaming, GTABase and RockstarINTEL. Structured cards, bounded headings, lists and narrative vehicle passages are normalized. Source week ranges must agree before data is merged; stale and inferred dates are flagged. Per-item source URLs and variants remain available.

Vehicle models are deduplicated before enrichment. A catalog supplies known metadata; article images and title-validated vehicle pages provide best-effort images. Model variants are not intentionally collapsed into a similar catalog vehicle.

## Security and exports

Cloud mode requires a strong shared password and PostgreSQL. HTTP-only, Secure, SameSite=Lax cookies authenticate APIs. Mutations check Origin; CORS is opt-in in cloud mode. API responses are not cached. Credentials stay in Vercel server environment variables.

PDF/JSON endpoints regenerate downloads from the authenticated saved snapshot. Temporary Vercel files are not used as durable storage. Email attempts use a persisted delivery claim: an interrupted/ambiguous attempt is not automatically sent twice.

The app is single-owner: everyone with the shared password has access to the same settings, runs and reports.
