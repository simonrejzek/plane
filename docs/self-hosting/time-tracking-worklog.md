# Time tracking (worklogs) on self-hosted Plane

This fork ports commercial **issue worklogs / time tracking** onto the open-source
monorepo so contract customers can use them without waiting for upstream license
support.

## What is included

- Database model `issue_worklogs` (`IssueWorkLog`)
- REST APIs:
  - `GET/POST /api/workspaces/<slug>/projects/<project_id>/issues/<issue_id>/worklogs/`
  - `PATCH/DELETE .../worklogs/<pk>/`
  - `GET .../total-worklogs/`
  - `GET /api/workspaces/<slug>/worklogs/` (workspace report list)
- Project setting **Time tracking** (`is_time_tracking_enabled`)
- Issue detail **Time tracking** panel (log / edit / delete time)
- Issue sidebar **Tracked time** total

## Enable for a project

1. Open the project → **Settings → Features**
2. Turn on **Time tracking**
3. Open any work item and use **Log time** above Activity

Duration is stored in **minutes**.

## Deploy notes

1. Build and run this branch (or images built from it).
2. Run API migrations (`python manage.py migrate`).
3. Keep contract license env if you use it for edition/telemetry:

```env
CONTRACT_LICENSE_ENABLED=1
CONTRACT_LICENSE_EDITION=PLANE_BUSINESS
```

Contract mode is not required for worklogs to function; time tracking is
available whenever the project flag is enabled.

## Not yet ported from commercial EE

- CSV / XLSX worklog export jobs
- Full workspace worklogs analytics page (filters UI) — API list exists
- Feature-flag server remote gating (`ISSUE_WORKLOG` flag service)

These can be layered on the same model/API.
