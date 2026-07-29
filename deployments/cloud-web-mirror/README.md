# Cloud web mirror (exact app.plane.so UI)

This package serves the **real commercial Plane web SPA assets** (downloaded from app.plane.so), not a hand-rolled Pilot UI.

## Runtime wiring

| Cloud default | Self-host |
| --- | --- |
| `https://api.plane.so` | same-origin `/api/*` → CE API |
| `https://pi.plane.so` | same-origin `/api/v1/*` → **plane-pi** (DeepSeek / OpenRouter) |
| Feature flags / plan | bootstrap `fetch` shim forces PI + Business chrome |

**Inference never uses Plane cloud PI.** Only the UI bundles were copied (with your session, offline). Live AI goes through your existing PI env (`LLM_*`).

## Build steps (CI / local)

```bash
python3 scripts/patch_assets.py
python3 scripts/build_index.py
docker build -t ttl.sh/cosmicboosts-plane-web:cloud-mirror-v1 .
```

## Refresh UI from cloud

1. Log into app.plane.so, download `/assets/*` referenced by the AI SPA manifest.
2. Replace `public/assets/` and `public/index.source.html`.
3. Re-run patch + index scripts and rebuild the image.
