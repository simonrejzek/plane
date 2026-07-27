# Contract license mode

Contract-licensed self-hosted deployments can use the Business edition without
contacting Plane-hosted licensing, update, or telemetry services.

Set these variables in the API, worker, and beat containers:

```env
CONTRACT_LICENSE_ENABLED=1
CONTRACT_LICENSE_EDITION=PLANE_BUSINESS
```

The setting is disabled by default. When enabled, instance registration:

- stores `PLANE_BUSINESS` as the instance edition;
- skips the GitHub release-version lookup; and
- skips the instance telemetry task and PostHog event tracking.

This mode does not disable customer-selected integrations such as SMTP,
OAuth, webhooks, storage, or marketplace providers. It only disables Plane's
own hosted registration/update/telemetry path. Those integrations must be
configured separately according to the deployment's needs.

## Time tracking (worklogs)

Contract deployments can use issue worklogs ported from the commercial tree.
See [time-tracking-worklog.md](./time-tracking-worklog.md) for API and UI
details. Enable **Time tracking** under project Settings → Features.
