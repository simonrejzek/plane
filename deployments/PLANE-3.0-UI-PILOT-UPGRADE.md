# Plane 3.0 — UI + Pilot AI upgrade (CosmicBoosts)

**Scope (owner direction):** primarily the **3.0 web UI** and **Pilot AI (Plane Intelligence)**.  
**Reference:** authenticated Business trial on `app.plane.so` (workspace `kospov`, plan BUSINESS).  
**Date:** 2026-07-29

## Reference findings from app.plane.so (Business cookies)

### Cloud instance
- Edition: `PLANE_CLOUD`, `min_desktop_version: 3.0.0`
- Workspace: `kospov` · plan **BUSINESS** · trial
- Workspace features of note:
  - `is_pi_enabled: true` ← Pilot / Plane Intelligence UI gate
  - `is_wiki_enabled: true`
  - hierarchy / work-item-types / releases largely off on this trial

### Pilot AI (Plane Intelligence) architecture
Pilot is **not** the old `POST /api/workspaces/{slug}/ai-assistant/` endpoint  
(that returns **410** *"moved to Plane Intelligence"*).

| Layer | Cloud | Role |
|-------|--------|------|
| Web UI | `app.plane.so` | Routes: `/settings/plane-intelligence`, sidecar `pi-chat` |
| Main API | `api.plane.so` | Workspace features, auth, core PM |
| **PI service** | **`pi.plane.so`** | Chat / models / skills / PQL AI |

Verified PI endpoints (session cookie auth works):

```
GET  https://pi.plane.so/api/v1/chat/get-models/
GET  https://pi.plane.so/api/v1/chat/get-user-threads/?workspace_slug=kospov
GET  https://pi.plane.so/api/v1/chat/get-recent-user-threads/
GET  https://pi.plane.so/api/v1/chat/get-favorite-chats/
GET  https://pi.plane.so/api/v1/chat/start/auth-check/?workspace_slug=kospov
GET  https://pi.plane.so/api/v1/flags/?workspace_slug=kospov
GET  https://pi.plane.so/api/v1/skills/?workspace_slug=kospov
```

Cloud PI flags (from `/api/v1/flags/`):

- `AI_CHAT`, `AI_DEDUPE`, `AI_CONVERSE`, `AI_FILE_UPLOADS`
- `AI_PAGES_BLOCKS`, `AI_PAGES_SUMMARY`, `AI_PAGES_EDIT`
- `AI_LABEL_PREDICTION`, `AI_MCP_CONNECTORS`, `AI_TEXT_TO_PQL`
- `AI_AUTOPILOT`, `AI_SKILLS`

Models available on cloud PI (examples): GPT-5.x, Claude Sonnet 4.x/5, GLM, Kimi, DeepSeek V4.

### 3.0 UI surface (from cloud SPA)
- Settings nav key: `plane-intelligence` → `/settings/plane-intelligence`
- Chat sidecar type: `pi-chat` (also project-scoped `ai-chat` loaders)
- Desktop handoff: `/api/desktop/handoff/*` (min desktop 3.0.0)
- Payment/product flags include: `SHARED_DASHBOARDS`, `PRIVATE_DASHBOARDS`, `PQL`, `AGENT_SIDECAR`, `CURSOR_INTEGRATION`, etc.

## Current self-hosted (plane.cosmicboosts.store)

| Component | Current |
|-----------|---------|
| API image | `plane-latest-api:cosmic-worklog-v1.5.3c` + GraphQL patches |
| Web image | `plane-latest-web:cosmic-worklog-v1.4` (**pre-3.0 UI**) |
| Space/Admin/Live | `makeplane/plane-*:v1.3.1` |
| Edition spoof | `PLANE_BUSINESS` / version `1.12.0` |
| LLM env | OpenRouter + DeepSeek (`LLM_*` set in Dokploy) |
| `has_llm_configured` | was **false** (env not synced into `InstanceConfiguration`) |
| PI service | **missing** (no `pi.plane.so` equivalent container) |

Mobile GraphQL patches live on `fork/preview` @ `1d4006c`.

## What “UI + Pilot” requires (cannot fake with env alone)

1. **Commercial 3.0 web image** (new shell, plane-intelligence settings, pi-chat sidecar).  
2. **Matching commercial 3.0 API** (DB migrations; workspace features schema for `is_pi_enabled`, etc.).  
3. **PI / intelligence service** (the `pi.plane.so` equivalent in commercial compose).  
4. **BYOK** wired into PI (`LLM_*` / provider settings — already partially present).  
5. Re-apply / re-verify **mobile GraphQL auth patches** after API image upgrade.

Official upgrade warnings still apply: long migrations, **full backup**, **no rollback**.

## Implementation phases

### Phase A — Unblock AI config on current stack (done / in progress)
- Sync `LLM_API_KEY` (+ provider/model/base) into `InstanceConfiguration` so `has_llm_configured` becomes true.
- Ensure contract flags keep `PI_CHAT` / `PI_CHAT_MOBILE` on (already in `contract_license.py`).
- Enable `is_pi_enabled` if the feature model exists on this schema.

### Phase B — Staging commercial 3.0 stack
- Obtain commercial **v3.0.0** images (Prime registry / license). Public Docker Hub CE tags are not 3.0 commercial.
- Compose services: `api`, `web`, `worker`, `pi` (or intelligence), `live`, `admin`, `space`, DB, redis, mq, minio.
- Point PI at OpenRouter/DeepSeek same as current `LLM_*`.
- Run migrator against a **restored backup clone**, not production first.

### Phase C — Feature parity checks
- Web: new shell loads; `/settings/plane-intelligence` works.
- Pilot: models list + initialize chat + thread history.
- Mobile: login + stickies + issue mutations still work with rebased GraphQL patches.

### Phase D — Production cutover
- Backup → deploy → smoke → keep previous compose revision for emergency restore of volumes.

## Immediate next actions
1. Confirm Phase A (`has_llm_configured` + PI feature rows).  
2. Locate commercial 3.0 image pull credentials (Prime / private registry).  
3. Draft `plane-v3-ui-pilot.staging.compose.yml` once images are available.
