# Architecture

`event-bridge` is intentionally tiny: one FastAPI process, one SQLite file,
one in-process forwarder coroutine. There is no broker and no separate
worker container.

## Process model

```
+----------------------------------+
|  python:3.12-slim container      |
|                                  |
|  +----------------------------+  |
|  |  uvicorn (single worker)   |  |
|  |                            |  |
|  |   FastAPI app (main:app)   |  |
|  |                            |  |
|  |   +- HTTP routers          |  |
|  |   +- WebSocket /ws         |  |
|  |   +- background forwarder  |  |
|  |        (asyncio.create_task)
|  +----------------------------+  |
|                |                 |
|                v                 |
|       /app/data/event_bridge.db  |
+----------------------------------+
```

The whole runtime fits in one Python process. Persistence and queueing are
delegated to SQLite (WAL) and an in-memory `asyncio.Queue` respectively. If
the process dies, in-flight items in the queue are lost — but the request
itself was already persisted before being enqueued, so the dashboard view
of "what arrived" is durable. Forwarding can then be retried by an operator
or by the retention sweep.

## Request lifecycle

```
External sender
      |
      |  POST /{slug}
      v
+-----------------+
|   webhooks.py   |   (FastAPI route)
+-----------------+
      |
      |  1) lookup webhook by slug, ownership check skipped (public ingest)
      |  2) insert into webhook_request (one transaction)
      |  3) push (request_id) onto in-process asyncio.Queue
      v
+--------------------+         +--------------------------+
| forwarder.py loop  |  --->   |  httpx.AsyncClient.post  |
|  (background task) |         |  per destination URL     |
+--------------------+         +--------------------------+
      |
      |  on permanent failure:
      v
   dead_letters table
```

WebSocket clients subscribed to `/ws` receive a small JSON event after step 2
(no Redis pub/sub needed — the route handler calls into a singleton
`ConnectionManager.broadcast`).

## Storage

| Table | Purpose |
|---|---|
| `user` | local username + bcrypt password hash |
| `webhook` | inbound endpoint, owner, optional transform script |
| `destination` | downstream URL belonging to a webhook |
| `webhook_request` | every received request: headers, body, query, timestamp |
| `dead_letter` | permanently failed forward attempts |

SQLite is opened with:

```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 30000;
PRAGMA synchronous = NORMAL;
```

This is more than enough for the typical "thousands of webhooks per hour"
internal use case.

## Why no Redis / RQ / Celery

For a single-instance internal gateway:

- We never need worker fan-out across machines.
- The retry policy (a few attempts with exponential backoff) is small enough
  to live inside the same process.
- Removing Redis cuts the operational surface from 3 containers to 1 and the
  deployment from "compose stack" to "single `docker run`".

If horizontal scale ever becomes a real problem, the contract between the
HTTP route and the forwarder is one function call — swapping in a real
broker is a contained change.

## Why no Google SSO

This is an internal tool that runs behind a VPN or a company SSO
reverse-proxy (Cloudflare Access, Okta gateway, ...). Embedded OAuth made
the dependency surface bigger without adding security in that deployment
model.

For homelab / standalone use, local username + password is plenty.
