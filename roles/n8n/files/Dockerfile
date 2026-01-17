FROM node:22-alpine

USER root

# Install system dependencies
RUN apk add --no-cache \
    poppler-utils \
    tini \
    openssl \
    ca-certificates

# Install n8n
RUN npm install -g n8n@2.4.2

# Replicate official entrypoint logic for custom certificates
RUN printf '#!/bin/sh\n\
if [ -d /opt/custom-certificates ]; then\n\
  echo "Trusting custom certificates from /opt/custom-certificates."\n\
  export NODE_OPTIONS="--use-openssl-ca $NODE_OPTIONS"\n\
  export SSL_CERT_DIR=/opt/custom-certificates\n\
  cp /opt/custom-certificates/*.crt /usr/local/share/ca-certificates/ 2>/dev/null || true\n\
  update-ca-certificates\n\
fi\n\
\n\
if [ "$#" -gt 0 ]; then\n\
  exec n8n "$@"\n\
else\n\
  exec n8n\n\
fi\n' > /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

USER node
WORKDIR /home/node

EXPOSE 5678

ENTRYPOINT ["tini", "--", "/docker-entrypoint.sh"]
