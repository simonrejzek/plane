# Plane 3.0 UI + Pilot — approach note (reverted)

**Status:** Custom/self-built Pilot stack was **reverted** on production (2026-07-29).

## Why reverted

Support’s direction is to **copy from the official plane.so product** (real cloud web UI + Pilot code), **not invent** a parallel Pilot UI/API shell.

The previous implementation:

- Reverse-engineered `pi.plane.so` APIs
- Shipped a **new** FastAPI PI service + custom Pilot SPA + inject script

That does **not** match “copy the plane.so website UI/code.”

## Production after revert

- No `/api/v1/chat/*` Pilot service
- No floating π inject
- No `/cosmic-pilot/*` product surface
- Proxy Caddyfile restored to pre-Pilot routes
- Pilot keepalive / inject / proxy-patch schedules removed
- Compose description restored; `pi` service removed from compose file
- Core Plane (instances, auth, GraphQL mobile patches) left intact

## Correct next path (per support)

1. Obtain the **actual** Plane cloud / commercial **web** (and PI) assets that match app.plane.so 3.0 UI — via support-approved channel (account access, licensed images, or exported UI packages).  
2. Deploy **those** artifacts on self-host (not a reimplementation).  
3. Wire auth/cookies/base URLs to the self-hosted API.  
4. Only then re-enable Pilot end-to-end against real UI code.

Do **not** rebuild Pilot UI from scratch again unless support explicitly asks for a custom implementation.
