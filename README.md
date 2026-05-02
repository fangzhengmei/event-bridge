# event-bridge

A self-hosted **inbound webhook gateway** that receives external events, persists them,
runs an optional in-process transformation script, and forwards the (transformed)
payload to one or many downstream destination URLs with retries and a dead-letter queue.

Single Docker, SQLite (WAL), pure Python. No Redis, no PostgreSQL, no third-party SSO.

## Why this exists

Most internal teams quickly accumulate a long tail of webhook integrations
(Stripe, GitHub, payment providers, monitoring services, partner callbacks, ...).
Each one of them needs roughly the same plumbing: receive, log, optionally re-shape,
and fan-out to one or more internal services.

`event-bridge` is the one small box that owns this plumbing so the rest of your
backend never has to care about webhook authentication, replay, retry, or
fan-out again.

## Feature overview

- Inbound endpoints with random-slug URLs, scoped per user
- Persistent request log (headers, body, query params) in SQLite
- Live web dashboard with WebSocket push of new events
- Per-webhook transformation script (sandboxed via RestrictedPython)
- Multi-destination forwarding with exponential backoff retry
- Dead-letter queue for permanently failed deliveries
- Local username + password authentication (JWT cookie)
- Single-container deployment, data persisted in a mounted volume

## Quick start (Docker)

```bash
docker build -t event-bridge:dev .
docker run --rm -p 8000:8000 -v "$(pwd)/data:/app/data" event-bridge:dev
# open http://localhost:8000
```

The first time the container starts it will create `/app/data/event_bridge.db`,
apply schema, and create an admin account using `ADMIN_USERNAME` /
`ADMIN_PASSWORD` from the environment (defaults to `admin` / `admin123`).

## Quick start (local Python)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python init_db.py
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Configuration

All configuration is environment-driven. See [.env.example](.env.example) for the
full list. The most important variables:

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/event_bridge.db` | SQLite file path |
| `SECRET_KEY` | `change-this-secret-key-in-production` | JWT signing key |
| `ADMIN_USERNAME` | `admin` | Bootstrap admin account on first start |
| `ADMIN_PASSWORD` | `admin123` | Bootstrap admin password (change me!) |
| `APP_PORT` | `8000` | Listen port |
| `WEBHOOK_RETENTION_DAYS` | `30` | Older requests are pruned by retention sweep |
| `FORWARD_MAX_ATTEMPTS` | `5` | Max retry attempts before going to dead-letter |
| `FORWARD_BASE_BACKOFF_SECONDS` | `1.0` | Exponential backoff base |

## API surface (selected)

- `GET  /` — dashboard (HTML, requires login)
- `GET  /login`, `POST /login` — local username/password login
- `GET  /logout`
- `POST /add_webhook` — create an inbound webhook
- `POST /pause`, `POST /delete`, `POST /webhooks/delete_all` — manage webhook
- `GET  /settings/{webhook_id}` — manage destination URLs and transform script
- `POST /{slug}` — public ingest endpoint (no auth, called by external systems)
- `GET  /{slug}` — webhook detail page (HTML)
- `GET  /api/webhook/{slug}/requests?offset=&limit=` — paginated JSON
- `GET  /webhook/request/{request_id}` — single request as JSON
- `WS   /ws` — live event stream
- `GET  /healthz` — liveness probe

## Security

- Authentication: local username/password, bcrypt hashed, signed JWT in
  `HttpOnly`, `SameSite=Lax` cookie.
- The public ingest endpoint `POST /{slug}` is unauthenticated by design
  (it has to be reachable by external senders). Use HMAC verification at the
  application layer if you need stronger guarantees.
- Transformation scripts run inside `RestrictedPython` and only have access
  to a small set of safe builtins plus `json`, `time`, `csv`.
- Set a strong `SECRET_KEY` and rotate `ADMIN_PASSWORD` on first start.

## Data layout

A single mounted volume contains everything stateful:

```
/app/data/
  event_bridge.db          # SQLite, WAL mode
  event_bridge.db-wal
  event_bridge.db-shm
```

Backups: stop the container or `sqlite3 ... ".backup"`, then copy the file.

## License

MIT — see [LICENSE](LICENSE).
