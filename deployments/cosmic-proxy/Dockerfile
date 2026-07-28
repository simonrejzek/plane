# Caddy with replace-response so we can inject Pilot into Plane web HTML
FROM caddy:2.8-builder-alpine AS builder
RUN xcaddy build --with github.com/caddyserver/replace-response

FROM caddy:2.8-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
