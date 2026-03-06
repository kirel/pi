FROM caddy:builder AS builder

RUN xcaddy build \
    --with github.com/dulli/caddy-wol@latest \
    --with github.com/abiosoft/caddy-exec \
    --with github.com/caddy-dns/regfish

FROM caddy:latest

RUN apk --no-cache add curl
RUN apk --no-cache add awake

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
