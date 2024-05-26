FROM caddy:builder AS builder

RUN xcaddy build \
    --with github.com/dulli/caddy-wol \
    --with github.com/abiosoft/caddy-exec

FROM caddy:latest

RUN apk --no-cache add curl

COPY --from=builder /usr/bin/caddy /usr/bin/caddy