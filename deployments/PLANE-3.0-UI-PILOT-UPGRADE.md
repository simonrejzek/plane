# Plane 3.0 — UI + Pilot AI (live on plane.cosmicboosts.store)

**Status:** LIVE (2026-07-29)  
**Reference:** Business trial on `app.plane.so` / `pi.plane.so` (workspace `kospov`)  
**Constraint:** No commercial 3.0 Docker images (support: contracts cannot use them). Built by reverse-engineering cloud APIs + UI shell.

## What is live now

| Layer | Implementation |
|-------|----------------|
| **PI API** | Self-hosted FastAPI service compatible with `pi.plane.so` `/api/v1/*` |
| **Runtime** | Runs inside the existing `api` container on port **8080** |
| **Routing** | Caddy (proxy) routes `/api/v1/chat/*`, `/api/v1/flags/`, `/api/v1/skills/`, `/cosmic-pilot/*` → `api:8080` |
| **Pilot UI** | `/cosmic-pilot/ui` — Ask / Build / Autopilot, models, skills, threads, favorites, SSE reasoning+delta |
| **Inject** | `inject.js` in web `index.html` → floating π button + `/{ws}/ai-chat` takeover + settings page |
| **LLM** | OpenRouter + DeepSeek (`LLM_*` env); `has_llm_configured: true` |
| **Keepalive** | Dokploy schedule `pilot-keepalive` every 5 minutes restarts PI if down |

## Cloud API parity (verified)

Against Business cookies on `pi.plane.so` and self-host:

| Endpoint | Cloud | Self-host |
|----------|-------|-----------|
| `GET /api/v1/chat/get-models/` | ✓ | ✓ (cloud catalog + default BYOK) |
| `GET /api/v1/flags/` | all AI_* true | same |
| `GET /api/v1/skills/` | 12 system skills | same slugs/instructions |
| `POST /api/v1/chat/initialize-chat/` | `{chat_id}` | same |
| `POST /api/v1/chat/queue-answer/` | `{stream_token}` | same |
| `GET /api/v1/chat/stream-answer/{token}` | reasoning → delta → cta → done | same shape |
| `GET /api/v1/chat/get-chat-history-object/` | `{results:{dialogue...}}` | same |
| Threads / favorites / rename / delete / prompts | ✓ | ✓ |

## How to use (users)

1. Open https://plane.cosmicboosts.store and log in.
2. Floating **π** button (bottom-right) opens Pilot sidecar (Cmd/Ctrl+J).
3. Full page: `/{workspace}/ai-chat` or `/{workspace}/ai-chat/new`.
4. Settings: `/{workspace}/settings/plane-intelligence`.

## Ops / recovery

### Ensure PI is running (API container)

Dokploy schedule **pilot-in-api** / **pilot-keepalive** (`V6qbDwx9zHru0T5q5YzRQ`):

- Pulls `deployments/pi-service` from `simonrejzek/plane@preview`
- Starts `uvicorn` on `0.0.0.0:8080`

### Ensure proxy routes

Schedule **pilot-proxy-routes** (`qV55ZRGx7AZ-79S6ZdYaD`) on service `proxy` rewrites Caddyfile with PI routes → `api:8080`.

### Ensure inject

Schedule **pilot-web-inject** (`9591TaWqgJxuorETw6tyZ`) on service `web` injects:

```html
<script src="/cosmic-pilot/inject.js" defer></script>
```

### Source code

- `deployments/pi-service/` — app + static Pilot UI + skills/models catalogs  
- `deployments/cosmic-proxy/Caddyfile` — PI route map  
- `deployments/plane-v3-pilot.compose.yml` — full compose draft (Dokploy full redeploy had YAML/deploy issues; live path uses schedules above)

## E2E test snapshot (production)

```
26/27 automated checks passed
- models, flags, skills, auth-check, prompts
- init → queue → stream (reasoning/delta/done) → history
- threads, favorites, rename, generate-title, delete
- UI assets + inject in index
- has_llm_configured true
- build mode queue
```

Stream body is chunked (`PAR`+`ITY`); assembled history answer is `PARITY` (same as cloud SSE).

## What is intentionally not identical

- **Core web shell** is still pre-3.0 commercial UI (no official 3.0 web image). Pilot **chat chrome** (modes, sidebar, model picker, skills, floating bot, ai-chat route) matches cloud Pilot behavior and layout language.
- **Autopilot / Build** modes call the same LLM stack; they do not execute cloud-side write tools against Plane objects yet (API surface + modes present).
- Chat memory is **in-process** (survives via keepalive restart loses memory unless Redis is added later).

## Cookies / reverse-engineering

Support account session cookies were used only to map `pi.plane.so` request/response shapes and cloud flags/models/skills — not stored in the repo.
